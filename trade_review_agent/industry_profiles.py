from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IndustryProfile:
    code: str
    name: str
    theme: str
    core_driver: str
    node: str
    sector_symbol: str
    chain_nodes: tuple[tuple[str, str, str], ...]
    barriers: tuple[str, ...]
    profit_levers: tuple[str, ...]
    peers: tuple[str, ...]
    industry_judgment: str = ""
    company_judgment: str = ""
    financial_validation: tuple[str, ...] = field(default_factory=tuple)
    expectation_gap: str = ""
    valuation_odds: str = ""
    catalysts: tuple[str, ...] = field(default_factory=tuple)
    disconfirming_signals: tuple[str, ...] = field(default_factory=tuple)
    position_sizing: str = ""
    one_sentence_thesis: str = ""
    rerating_anchor: str = ""
    market_position: str = ""
    peer_ranking: tuple[str, ...] = field(default_factory=tuple)
    best_expression: str = ""
    trading_implication: str = ""
    evidence: tuple[str, ...] = field(default_factory=tuple)
    wang_investor_report: str = ""
    public_equity_report: str = ""


DEFAULT_PROFILE = IndustryProfile(
    code="",
    name="个股",
    theme="AI 产业研究待生成",
    core_driver="市场主线待识别",
    node="产业链节点待识别",
    sector_symbol="sh000300",
    chain_nodes=(
        ("core", "需求驱动", "待识别"),
        ("upstream", "上游约束", "待识别"),
        ("stock", "目标公司", "待识别"),
        ("downstream", "下游应用", "待识别"),
        ("peer", "同链公司", "待识别"),
    ),
    barriers=("AI 产业研究生成失败，请检查 OpenAI 配置、代理或刷新缓存。",),
    profit_levers=("盈利弹性待生成",),
    peers=(),
    industry_judgment="产业判断待生成。",
    company_judgment="公司判断待生成。",
    financial_validation=("收入结构", "毛利率", "订单/产能利用率"),
    expectation_gap="预期差待验证。",
    valuation_odds="估值赔率待验证。",
    catalysts=("订单/客户验证", "财报兑现", "行业景气变化"),
    disconfirming_signals=("逻辑未被财报验证", "竞争加剧", "估值透支"),
    position_sizing="仓位应根据波动、流动性和反证点控制。",
    one_sentence_thesis="产业链研究待生成。",
    rerating_anchor="重估锚待识别。",
    market_position="交易位置待判断。",
    peer_ranking=(),
    best_expression="同赛道最佳表达待判断。",
    trading_implication="买点和持仓策略待生成。",
    evidence=(),
    wang_investor_report="",
    public_equity_report="",
)


def get_profile(code: str, fallback_name: str = "") -> IndustryProfile:
    from .industry_agent import get_ai_industry_profile

    try:
        return get_ai_industry_profile(code=code, name=fallback_name)
    except Exception as exc:
        return _fallback_profile(code, fallback_name, exc)


def _fallback_profile(code: str, fallback_name: str, exc: Exception) -> IndustryProfile:
    return IndustryProfile(
        code=code,
        name=fallback_name or code or DEFAULT_PROFILE.name,
        theme=DEFAULT_PROFILE.theme,
        core_driver=DEFAULT_PROFILE.core_driver,
        node=DEFAULT_PROFILE.node,
        sector_symbol=DEFAULT_PROFILE.sector_symbol,
        chain_nodes=DEFAULT_PROFILE.chain_nodes,
        barriers=(f"AI 产业研究生成失败：{exc}",),
        profit_levers=DEFAULT_PROFILE.profit_levers,
        peers=DEFAULT_PROFILE.peers,
        industry_judgment=DEFAULT_PROFILE.industry_judgment,
        company_judgment=DEFAULT_PROFILE.company_judgment,
        financial_validation=DEFAULT_PROFILE.financial_validation,
        expectation_gap=DEFAULT_PROFILE.expectation_gap,
        valuation_odds=DEFAULT_PROFILE.valuation_odds,
        catalysts=DEFAULT_PROFILE.catalysts,
        disconfirming_signals=DEFAULT_PROFILE.disconfirming_signals,
        position_sizing=DEFAULT_PROFILE.position_sizing,
        one_sentence_thesis=DEFAULT_PROFILE.one_sentence_thesis,
        rerating_anchor=DEFAULT_PROFILE.rerating_anchor,
        market_position=DEFAULT_PROFILE.market_position,
        peer_ranking=DEFAULT_PROFILE.peer_ranking,
        best_expression=DEFAULT_PROFILE.best_expression,
        trading_implication=DEFAULT_PROFILE.trading_implication,
        evidence=DEFAULT_PROFILE.evidence,
        wang_investor_report=DEFAULT_PROFILE.wang_investor_report,
        public_equity_report=DEFAULT_PROFILE.public_equity_report,
    )
