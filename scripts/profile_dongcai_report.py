from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trade_review_agent.config import load_env
from trade_review_agent.schema import Trade
from trade_review_agent.trade_rounds import TradeRound


OUTPUT = ROOT / "outputs" / "profile_dongcai_20260609" / "601208_20260609_r1.html"
PROFILE_JSON = OUTPUT.with_suffix(".profile.json")


class Profiler:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.llm_calls: list[dict[str, Any]] = []

    @contextmanager
    def stage(self, name: str, **extra: Any):
        started = time.perf_counter()
        event: dict[str, Any] = {"stage": name, **extra}
        try:
            yield event
            event["status"] = event.get("status") or "ok"
        except Exception as exc:
            event["status"] = "error"
            event["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            event["seconds"] = round(time.perf_counter() - started, 4)
            self.events.append(event)
            print(json.dumps({"stage": name, "seconds": event["seconds"], "status": event.get("status")}, ensure_ascii=False), flush=True)


def main() -> None:
    load_env(ROOT / ".env")
    if not _key_configured():
        raise RuntimeError("OPENAI_API_KEY is not configured in .env")

    profiler = Profiler()
    _install_runtime_probes(profiler)

    from trade_review_agent.visual_report import build_round_html

    trades = (
        Trade(
            code="601208",
            name="东材科技",
            trade_date=date(2026, 6, 9),
            side="buy",
            price=58.710,
            quantity=100,
            amount=5871.00,
            fee=1.06,
        ),
        Trade(
            code="601208",
            name="东材科技",
            trade_date=date(2026, 6, 9),
            side="buy",
            price=59.620,
            quantity=100,
            amount=5962.00,
            fee=1.06,
        ),
    )
    trade_round = TradeRound(code="601208", name="东材科技", round_id=1, trades=trades)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    total_started = time.perf_counter()
    error = ""
    result = None
    try:
        result = build_round_html(
            trade_round=trade_round,
            output=OUTPUT,
            cache_db=ROOT / "work" / "real_trade_review_cache.sqlite",
            benchmark_symbol="sh000300",
            research_model_tier=os.getenv("PROFILE_RESEARCH_MODEL_TIER", "standard"),
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    total_seconds = round(time.perf_counter() - total_started, 4)

    artifacts = _read_artifacts(OUTPUT)
    payload = {
        "case": {
            "code": "601208",
            "name": "东材科技",
            "trade_date": "2026-06-09",
            "trades": [trade.__dict__ | {"trade_date": trade.trade_date.isoformat()} for trade in trades],
        },
        "status": "ok" if not error else "error",
        "error": error,
        "total_seconds": total_seconds,
        "output": str(result.output if result else OUTPUT),
        "events": profiler.events,
        "llm_calls": profiler.llm_calls,
        "artifact_timings": artifacts.get("timings"),
        "artifact_metrics": artifacts.get("metrics"),
        "agent_errors": artifacts.get("agent_errors"),
        "summary": _summarize(profiler, artifacts, total_seconds),
    }
    PROFILE_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2), flush=True)
    print(str(PROFILE_JSON), flush=True)
    if error:
        raise RuntimeError(error)


def _install_runtime_probes(profiler: Profiler) -> None:
    import trade_review_agent.financial_data_provider as financial_provider
    import trade_review_agent.presenter_agent as presenter_agent
    import trade_review_agent.trade_execution_chain as trade_execution_chain
    import trade_review_agent.valuation_data_provider as valuation_provider
    import trade_review_agent.visual_report as visual_report
    import trade_review_agent.workbench_agents as workbench_agents
    import trade_review_agent.workbench_context as workbench_context
    import trade_review_agent.workbench_news as workbench_news

    original_json_agent = workbench_agents._call_json_agent
    original_text_agent = workbench_agents._call_text_agent

    def profiled_json_agent(system_prompt: str, user_prompt: str, **kwargs: Any) -> dict[str, Any]:
        return _profile_llm_call(
            profiler,
            original_json_agent,
            "json",
            system_prompt,
            user_prompt,
            kwargs,
        )

    def profiled_text_agent(system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        return _profile_llm_call(
            profiler,
            original_text_agent,
            "text",
            system_prompt,
            user_prompt,
            kwargs,
        )

    for module in (workbench_agents, workbench_news, visual_report, presenter_agent, trade_execution_chain):
        if hasattr(module, "_call_json_agent"):
            module._call_json_agent = profiled_json_agent
    workbench_agents._call_text_agent = profiled_text_agent

    original_market_catalyst = workbench_context.build_market_catalyst_context
    original_financial_get = financial_provider.FinancialDataProvider.get_financials
    original_valuation = valuation_provider.fetch_valuation_snapshot

    def profiled_market_catalyst(code: str, name: str) -> dict[str, Any]:
        with profiler.stage("market_catalyst_context", code=code, stock_name=name):
            return original_market_catalyst(code, name)

    def profiled_financial_get(self: Any, code: str) -> dict[str, Any]:
        with profiler.stage("financial_provider", code=code) as event:
            result = original_financial_get(self, code)
            event["provider"] = result.get("provider")
            event["data_status"] = result.get("status")
            event["available_fields"] = [
                field
                for field in financial_provider.FINANCIAL_FIELDS
                if result.get(field) is not None
            ]
            event["errors"] = result.get("errors", [])[:3]
            return result

    def profiled_valuation(code: str, **kwargs: Any) -> dict[str, Any]:
        with profiler.stage("valuation_provider", code=code) as event:
            result = original_valuation(code, **kwargs)
            event["provider"] = result.get("provider")
            event["data_status"] = result.get("status")
            event["available_fields"] = [
                field
                for field in valuation_provider.VALUATION_FIELDS
                if result.get(field) is not None
            ]
            event["errors"] = result.get("errors", [])[:3]
            return result

    financial_provider.FinancialDataProvider.get_financials = profiled_financial_get
    valuation_provider.fetch_valuation_snapshot = profiled_valuation
    workbench_context.build_market_catalyst_context = profiled_market_catalyst
    workbench_context.fetch_valuation_snapshot = profiled_valuation


def _profile_llm_call(
    profiler: Profiler,
    original: Callable[..., Any],
    mode: str,
    system_prompt: str,
    user_prompt: str,
    kwargs: dict[str, Any],
) -> Any:
    stage = _classify_llm_stage(system_prompt, user_prompt)
    started = time.perf_counter()
    call: dict[str, Any] = {
        "stage": stage,
        "mode": mode,
        "model": kwargs.get("model_override") or os.getenv("OPENAI_MODEL") or "",
        "allow_web": bool(kwargs.get("allow_web")),
        "max_output_tokens": kwargs.get("max_output_tokens"),
        "estimated_input_tokens": _estimate_tokens(system_prompt) + _estimate_tokens(user_prompt),
    }
    try:
        result = original(system_prompt, user_prompt, **kwargs)
        call["status"] = "ok"
        if isinstance(result, dict):
            call["api_usage"] = result.get("_api_usage")
            if result.get("_agent_error"):
                call["status"] = "agent_error"
                call["error"] = str(result.get("_agent_error"))[:500]
        return result
    except Exception as exc:
        call["status"] = "exception"
        call["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        call["seconds"] = round(time.perf_counter() - started, 4)
        profiler.llm_calls.append(call)
        print(
            json.dumps(
                {
                    "llm": stage,
                    "seconds": call["seconds"],
                    "status": call.get("status"),
                    "usage": call.get("api_usage"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


def _classify_llm_stage(system_prompt: str, user_prompt: str) -> str:
    text = f"{system_prompt}\n{user_prompt}"
    if "market catalyst scout" in text:
        return "market_catalyst_llm_web"
    if "YingHang V3 Better Opportunity Agent" in text:
        return "v3_better_opportunity"
    if "YingHang V3 Trade Coach" in text:
        return "v3_trade_coach"
    if "WANG industry-chain" in text:
        return "wang_industry_agent"
    if "Public Equity" in text:
        return "public_equity_agent"
    if "交易执行" in text:
        return "trade_execution_llm"
    if "Presenter" in text or "Structurer Agent" in text:
        return "presenter_agent"
    return "unknown_llm_call"


def _read_artifacts(output: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, path in {
        "timings": output.with_suffix(".timings.json"),
        "workbench": output.with_suffix(".workbench.json"),
        "execution_llm": output.with_suffix(".trade_execution_llm_output.json"),
        "presenter": output.with_suffix(".presenter.json"),
    }.items():
        try:
            result[name] = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            result[name] = None
    workbench = result.get("workbench") if isinstance(result.get("workbench"), dict) else {}
    layers = workbench.get("research_layers") if isinstance(workbench.get("research_layers"), dict) else {}
    metrics = {}
    for key, value in {
        "wang": layers.get("wang_industry"),
        "public_equity": layers.get("public_equity"),
    }.items():
        if isinstance(value, dict):
            metrics[key] = value.get("research_metrics")
    execution = result.get("execution_llm")
    if isinstance(execution, dict):
        metrics["trade_execution_llm"] = execution.get("research_metrics")
    result["metrics"] = metrics
    result["agent_errors"] = workbench.get("agent_errors") if isinstance(workbench, dict) else None
    return result


def _summarize(profiler: Profiler, artifacts: dict[str, Any], total_seconds: float) -> dict[str, Any]:
    llm_seconds = round(sum(float(item.get("seconds") or 0) for item in profiler.llm_calls), 4)
    actual_tokens = 0
    for item in profiler.llm_calls:
        usage = item.get("api_usage")
        if isinstance(usage, dict):
            actual_tokens += int(usage.get("total_tokens") or 0)
    slow_events = sorted(
        [
            {"stage": item.get("stage"), "seconds": item.get("seconds"), "status": item.get("status")}
            for item in profiler.events
        ]
        + [
            {"stage": item.get("stage"), "seconds": item.get("seconds"), "status": item.get("status")}
            for item in profiler.llm_calls
        ],
        key=lambda item: float(item.get("seconds") or 0),
        reverse=True,
    )[:10]
    return {
        "total_seconds": total_seconds,
        "llm_wall_seconds_sum": llm_seconds,
        "actual_total_tokens_observed": actual_tokens or None,
        "llm_call_count": len(profiler.llm_calls),
        "slowest": slow_events,
        "artifact_timings": artifacts.get("timings"),
        "agent_errors": artifacts.get("agent_errors"),
    }


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(str(text)) / 3))


def _key_configured() -> bool:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return bool(key and key != "your-openai-api-key-here")


if __name__ == "__main__":
    main()
