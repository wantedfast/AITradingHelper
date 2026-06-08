from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .data_provider import MarketDataProvider
from .execution_structurer import structure_trade_execution_payload
from .industry_profiles import IndustryProfile
from .trade_execution_agent import analyze_trade_execution
from .trade_execution_data import build_trade_execution_data_context
from .trade_rounds import TradeRound


def build_trade_execution_chain(
    *,
    provider: MarketDataProvider,
    profile: IndustryProfile,
    trade_round: TradeRound,
    output: str | Path,
) -> dict[str, Any]:
    """Run the independent execution chain and persist its debug artifacts."""

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    data_context = build_trade_execution_data_context(provider=provider, profile=profile, trade_round=trade_round)
    agent_output = analyze_trade_execution(data_context)
    final_payload = structure_trade_execution_payload(
        trade_facts=data_context.get("trade_facts"),
        execution_analysis=agent_output,
        data_source_status=data_context.get("data_source_status"),
    )
    _write_json(output.with_suffix(".execution_data_context.json"), data_context)
    _write_json(output.with_suffix(".trade_execution_agent_output.json"), agent_output)
    _write_json(output.with_suffix(".trade_execution.json"), final_payload)
    return final_payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
