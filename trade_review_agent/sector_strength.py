from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SectorSignal:
    name: str
    score: int
    state: str
    pct_chg: float
    relative_to_benchmark: float
    volume_ratio: float
    fund_flow_status: str
    warning: str
    buy_effect: str
    sell_effect: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_sector_signal(profile, sector_day: dict[str, float], benchmark_day: dict[str, float]) -> SectorSignal:
    """Score sector/theme strength for trade review.

    V1 intentionally uses stable market facts that are already in the report
    pipeline: sector/ETF daily change, relative strength vs benchmark, and
    volume ratio. Fund-flow ranking can be added as evidence later, but should
    not block report generation when third-party endpoints are unstable.
    """

    name = _sector_name(profile)
    pct = _num(sector_day.get("pct"))
    benchmark_pct = _num(benchmark_day.get("pct"))
    relative = pct - benchmark_pct
    volume_ratio = _num(sector_day.get("vol_ratio"), 1.0)

    score = 50
    score += _clip(relative * 8, -24, 24)
    score += _clip(pct * 4, -18, 18)
    score += _clip((volume_ratio - 1.0) * 18, -10, 14)
    score = int(max(0, min(100, round(score))))

    state = _state(score, pct, relative, volume_ratio)
    fund_flow_status = _fund_flow_proxy(state, relative, volume_ratio)
    warning = _warning(state, name)
    buy_effect = _buy_effect(state)
    sell_effect = _sell_effect(state)
    return SectorSignal(
        name=name,
        score=score,
        state=state,
        pct_chg=pct,
        relative_to_benchmark=relative,
        volume_ratio=volume_ratio,
        fund_flow_status=fund_flow_status,
        warning=warning,
        buy_effect=buy_effect,
        sell_effect=sell_effect,
    )


def _sector_name(profile) -> str:
    theme = str(getattr(profile, "theme", "") or "").strip()
    node = str(getattr(profile, "node", "") or "").strip()
    symbol = str(getattr(profile, "sector_symbol", "") or "").strip()
    if theme and "待" not in theme:
        return theme[:28]
    if node and "待" not in node:
        return node[:28]
    return symbol or "板块/主题"


def _state(score: int, pct: float, relative: float, volume_ratio: float) -> str:
    if score >= 78 and relative >= 2 and pct > 0:
        return "主攻"
    if score >= 65 and relative > 0:
        return "强势轮动"
    if 45 <= score < 65:
        return "分歧"
    if score < 45 and relative < 0:
        return "走弱"
    if score < 35 and pct < 0 and relative < -1:
        return "退潮"
    if volume_ratio < 0.75 and pct <= 0:
        return "缩量走弱"
    return "分歧"


def _fund_flow_proxy(state: str, relative: float, volume_ratio: float) -> str:
    if state in {"主攻", "强势轮动"} and volume_ratio >= 1.15:
        return "疑似资金流入/放量共振"
    if state in {"走弱", "退潮"} and relative < 0:
        return "疑似资金流出/弱于指数"
    if volume_ratio < 0.8:
        return "缩量，资金承接不足"
    return "资金状态待确认"


def _warning(state: str, name: str) -> str:
    if state == "主攻":
        return f"{name}处于主攻状态，个股买点容错率提高，但追高仍需看量价。"
    if state == "强势轮动":
        return f"{name}强于指数，但更像轮动，买点要控制仓位。"
    if state == "分歧":
        return f"{name}处于分歧，个股需要自己走强确认，不能只靠题材。"
    if state == "退潮":
        return f"{name}出现退潮信号，盈利仓应优先收紧卖出规则。"
    return f"{name}走弱，买点降级，卖点应更纪律化。"


def _buy_effect(state: str) -> str:
    return {
        "主攻": "买点加分：板块主攻，允许右侧跟随，但要防止情绪高点追买。",
        "强势轮动": "买点小幅加分：板块强于指数，但需确认持续性。",
        "分歧": "买点中性：个股必须强于板块，否则只是弱反抽。",
        "走弱": "买点降级：板块弱，除非个股显著逆势，否则不宜重仓。",
        "退潮": "买点大幅降级：题材退潮日，买入更像试错。",
        "缩量走弱": "买点降级：板块缩量，资金承接不足。",
    }.get(state, "买点中性：等待板块方向确认。")


def _sell_effect(state: str) -> str:
    return {
        "主攻": "卖点放宽：板块仍强时，可以用5日线/前低作为移动止盈。",
        "强势轮动": "卖点正常：板块仍有承接，但个股转弱要减仓。",
        "分歧": "卖点收紧：板块分歧时，个股跌破关键位应先降仓位。",
        "走弱": "卖点提前：板块弱于指数时，不必等个股完全破位。",
        "退潮": "卖点优先：板块退潮时，盈利仓先保护利润。",
        "缩量走弱": "卖点收紧：缩量走弱说明承接不足。",
    }.get(state, "卖点正常：按预案执行。")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
