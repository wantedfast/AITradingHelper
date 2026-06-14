from __future__ import annotations

import html
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from trade_review_agent.review.final_wang_agent import run_final_wang_agent


@dataclass(frozen=True)
class SimpleWangReportResult:
    output: Path
    title: str
    rating: str
    score: int
    trade_type: str
    requested_research_model_tier: str = "standard"
    research_model_tier: str = "standard"
    wang_model: str = "final_wang_agent"


def build_minimal_wang_context(trades: str | Path | list[dict[str, Any]] | pd.DataFrame) -> dict[str, Any]:
    rows = _trade_rows(trades)
    if not rows:
        raise ValueError("No trade facts found for Final WANG Agent")

    buys = [row for row in rows if str(row.get("side") or "").lower() == "buy"]
    primary = buys[0] if buys else rows[0]
    code = _clean_code(primary.get("code"))
    name = str(primary.get("name") or code).strip()
    if not code:
        raise ValueError("OCR result missing stock code")
    if not name:
        name = code

    normalized_trades = [_minimal_trade(row) for row in rows]
    buy_date = str(primary.get("trade_date") or normalized_trades[0].get("trade_date") or "").strip()
    return {
        "company": {
            "code": code,
            "name": name,
            "market": str(primary.get("market") or "A-share").strip() or "A-share",
        },
        "trade": {
            "buy_date": buy_date,
            "trades": normalized_trades,
        },
    }


def run_simple_wang_review(
    trades_path: str | Path,
    output_dir: str | Path,
    *,
    requested_research_model_tier: str = "standard",
) -> list[SimpleWangReportResult]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    context = build_minimal_wang_context(trades_path)
    context["_run_id"] = output_dir.name
    context["_run_dir"] = str(output_dir)
    agent_result = run_final_wang_agent(context)
    output_html = output_dir / _report_filename(context)
    render_simple_wang_report(agent_result, output_html, context=context)

    presenter_path = output_html.with_suffix(".presenter.json")
    debug_path = output_html.with_suffix(".debug.json")
    index_path = output_dir / "index.html"
    research_presenter_path = output_dir / "research_presenter_data.json"
    research_debug_path = output_dir / "research_debug_data.json"

    research_presenter_path.write_bytes(presenter_path.read_bytes())
    research_debug_path.write_bytes(debug_path.read_bytes())
    index_path.write_bytes(output_html.read_bytes())

    presenter = json.loads(presenter_path.read_text(encoding="utf-8"))
    final_answer = presenter.get("final_answer") if isinstance(presenter, dict) else {}
    score = int(final_answer.get("score") or 0) if isinstance(final_answer, dict) else 0
    return [
        SimpleWangReportResult(
            output=output_html,
            title=_report_title(context),
            rating="",
            score=score,
            trade_type="simple_wang_agent",
            requested_research_model_tier=requested_research_model_tier,
            research_model_tier="final_wang_agent",
            wang_model=str(((agent_result.get("research_metrics") or {}).get("model")) or "final_wang_agent")
            if isinstance(agent_result, dict)
            else "final_wang_agent",
        )
    ]


def render_simple_wang_report(
    agent_result: dict[str, Any],
    output_html: str | Path,
    *,
    context: dict[str, Any] | None = None,
) -> Path:
    output_html = Path(output_html)
    output_html.parent.mkdir(parents=True, exist_ok=True)
    context = context or {}
    presenter = _presenter_payload(agent_result, context)

    output_html.with_suffix(".presenter.json").write_text(json.dumps(presenter, ensure_ascii=False, indent=2), encoding="utf-8")
    output_html.with_suffix(".debug.json").write_text(
        json.dumps(
            {
                "pipeline": "simple_wang_agent_only",
                "context": context,
                "agent_result": agent_result,
                "removed_legacy_pipeline": "not_called",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_html.write_text(_html_report(presenter), encoding="utf-8")
    return output_html


def _trade_rows(trades: str | Path | list[dict[str, Any]] | pd.DataFrame) -> list[dict[str, Any]]:
    if isinstance(trades, pd.DataFrame):
        frame = trades
    elif isinstance(trades, (str, Path)):
        frame = pd.read_csv(trades, encoding="utf-8-sig")
    else:
        frame = pd.DataFrame(trades)
    if frame.empty:
        return []
    rows = []
    for row in frame.to_dict("records"):
        clean = {str(key): _jsonable(value) for key, value in row.items()}
        rows.append(clean)
    rows.sort(key=lambda item: (str(item.get("trade_date") or ""), str(item.get("trade_time") or ""), str(item.get("side") or "")))
    return rows


def _minimal_trade(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "side": _side(row.get("side")),
        "trade_date": str(row.get("trade_date") or "").strip(),
        "trade_time": str(row.get("trade_time") or "").strip(),
        "price": _number(row.get("price")),
        "quantity": _number(row.get("quantity")),
        "amount": _number(row.get("amount")),
        "fee": _number(row.get("fee")),
    }


def _presenter_payload(agent_result: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    payload = dict(agent_result or {})
    company = context.get("company") if isinstance(context.get("company"), dict) else {}
    trade = context.get("trade") if isinstance(context.get("trade"), dict) else {}
    payload["company"] = company
    payload["trade"] = trade
    payload["pipeline"] = "simple_wang_agent_only"
    payload["final_answer"] = payload.get("ai_final_answer") or payload.get("final_answer") or {}
    payload.setdefault("technical_timing", {})
    payload.setdefault("market_theme", {})
    payload.setdefault("industry_chain", {})
    payload.setdefault("peer_comparison", {})
    return payload


def _html_report(presenter: dict[str, Any]) -> str:
    company = presenter.get("company") if isinstance(presenter.get("company"), dict) else {}
    final = presenter.get("final_answer") if isinstance(presenter.get("final_answer"), dict) else {}
    answer = str(presenter.get("coach_answer") or final.get("verdict") or "")
    title = html.escape(_report_title({"company": company}))
    verdict = html.escape(str(final.get("verdict") or ""))
    score = html.escape(str(final.get("score") or "-"))
    sections_html = _sections_to_html(presenter, answer)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} AI 复盘报告</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #172033; background: #f6f7f9; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 40px 20px 64px; }}
    header {{ border-bottom: 1px solid #d8dde8; padding-bottom: 24px; margin-bottom: 24px; }}
    .eyebrow {{ color: #60708a; font-size: 13px; letter-spacing: .04em; text-transform: uppercase; }}
    h1 {{ margin: 8px 0 12px; font-size: 34px; line-height: 1.2; }}
    .score {{ display: inline-flex; gap: 8px; align-items: baseline; padding: 8px 12px; background: #172033; color: white; border-radius: 6px; }}
    .verdict {{ font-size: 18px; line-height: 1.7; color: #2d3748; }}
    section {{ background: white; border: 1px solid #dfe3eb; border-radius: 8px; padding: 24px; margin-top: 18px; }}
    h2 {{ margin: 0 0 12px; font-size: 22px; }}
    pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; font: 15px/1.8 ui-sans-serif, system-ui, sans-serif; }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="eyebrow">Final WANG Agent</div>
      <h1>{title}</h1>
      <div class="score"><span>AI 评分</span><strong>{score}</strong></div>
      <p class="verdict">{verdict}</p>
    </header>
    {sections_html}
  </main>
</body>
</html>
"""


def _report_filename(context: dict[str, Any]) -> str:
    company = context.get("company") if isinstance(context.get("company"), dict) else {}
    trade = context.get("trade") if isinstance(context.get("trade"), dict) else {}
    name = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", str(company.get("name") or company.get("code") or "wang_report")).strip("_")
    date = re.sub(r"[^\d-]+", "", str(trade.get("buy_date") or ""))
    return f"{name}_{date or 'trade'}_wang.html"


def _report_title(context: dict[str, Any]) -> str:
    company = context.get("company") if isinstance(context.get("company"), dict) else {}
    name = str(company.get("name") or "").strip()
    code = str(company.get("code") or "").strip()
    return f"{name} {code}".strip() or "AI 复盘报告"


def _clean_code(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits.zfill(6)[-6:] if digits else ""


def _side(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"buy", "b"} or "买" in text:
        return "buy"
    if text in {"sell", "s"} or "卖" in text:
        return "sell"
    return text


def _number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number) or math.isinf(number):
        return 0.0
    return number


def _jsonable(value: Any) -> Any:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return ""
    return value


def _plain_text_to_html(text: str) -> str:
    return html.escape(text or "")


def _sections_to_html(presenter: dict[str, Any], answer: str) -> str:
    sections = presenter.get("display_sections")
    if not isinstance(sections, list):
        summary = presenter.get("presenter_summary") if isinstance(presenter.get("presenter_summary"), dict) else {}
        sections = summary.get("display_sections") if isinstance(summary.get("display_sections"), list) else []
    rows: list[str] = []
    for item in sections:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or "").strip()
        if not title or not content:
            continue
        rows.append(f"<section><h2>{html.escape(title)}</h2><pre>{_plain_text_to_html(content)}</pre></section>")
    if rows:
        return "\n    ".join(rows)
    return f"<section><pre>{_plain_text_to_html(answer)}</pre></section>"
