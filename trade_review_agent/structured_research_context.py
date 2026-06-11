from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
import os
from typing import Any, Callable

import pandas as pd

from .alerts import fetch_realtime_quote


def build_structured_research_context(code: str, name: str = "") -> dict[str, Any]:
    """Build fast, structured context for Workbench agents.

    AKShare provides news, announcements, concepts, business scope, and
    financial statements. Tencent Finance is used as a fast market-data fallback
    so missing AKShare research data does not block report generation.
    """
    code = _clean_code(code)
    name = str(name or code).strip()
    fetched = _fetch_structured_inputs(code)
    source_status = {key: _source_status(value) for key, value in fetched.items()}

    news = fetched.get("akshare_stock_news_em", {}).get("records", [])
    notices = fetched.get("akshare_notice", {}).get("records", [])
    hot = fetched.get("akshare_hot_keyword", {}).get("records", [])
    business = fetched.get("akshare_business_intro_ths", {}).get("records", [])
    financial = fetched.get("akshare_financial_abstract_ths", {}).get("records", [])
    income = fetched.get("akshare_income_ths", {}).get("records", [])
    cashflow = fetched.get("akshare_cashflow_ths", {}).get("records", [])
    balance = fetched.get("akshare_balance_ths", {}).get("records", [])
    quote = fetched.get("tencent_realtime_quote", {}).get("data") or {}

    news_titles = _first_texts(news, "新闻标题", 10)
    notice_titles = _first_texts(notices, "公告标题", 8)
    hot_names = _first_texts(hot, "概念名称", 8)
    business_intro = business[0] if business else {}

    evidence = news_titles[:6] + hot_names[:6] + notice_titles[:4]
    unknowns = _missing_unknowns(news, notices, hot, business, financial, income, cashflow, balance)
    if not unknowns:
        unknowns = [
            "热点主题与公司实际收入、利润、订单和客户的对应关系仍需公告或研报验证",
            "市场短线异动是否能转化为可持续基本面改善仍需验证",
        ]
    market_catalyst = {
        "market_hype_reason": _market_hype_reason(news_titles, hot_names, quote),
        "recent_catalysts": news_titles[:6] + notice_titles[:4],
        "traded_business_line": _traded_business_line(business_intro, hot_names),
        "what_market_is_pricing": _what_market_is_pricing(hot_names, business_intro),
        "evidence_quality": _evidence_quality(news, notices, business, financial),
        "unknowns": unknowns[:8],
        "evidence": evidence[:12],
        "source_queries": [],
        "source_status": source_status,
    }
    return {
        "market_catalyst": market_catalyst,
        "market_event_context": {
            "data_sources": [
                "AkShare 东方财富新闻",
                "AkShare 公告",
                "AkShare 东方财富热词",
                "AkShare 同花顺主营/财务",
                "Tencent Finance realtime quote fallback",
            ],
            "source_status": source_status,
            "tencent_quote": quote,
            "hot_keywords": hot[:8],
            "news_headlines": news_titles,
            "news_records": news[:6],
            "announcements": notices[:8],
        },
        "industry_chain_context": {
            "business_scope": {
                "main_business": business_intro.get("主营业务", ""),
                "product_types": business_intro.get("产品类型", ""),
                "product_names": business_intro.get("产品名称", ""),
                "operation_scope": business_intro.get("经营范围", ""),
            },
            "theme_mapping": {
                "hot_keywords": hot[:8],
                "inferred_chain_node": _infer_chain_node(business_intro, hot_names),
                "possible_profit_pool": _profit_pool_hints(hot_names),
                "peer_reference": _peer_reference(hot_names),
            },
            "event_evidence": {
                "news_headlines": news_titles[:10],
                "announcements": notices[:8],
                "tencent_quote": quote,
            },
        },
        "public_equity_context": {
            "business_intro": business_intro,
            "financial_snapshot": _extract_latest(
                financial,
                ["报告期", "净利润", "净利润同比增长率", "扣非净利润", "营业总收入", "营业总收入同比增长率", "销售毛利率", "资产负债率"],
                5,
            ),
            "income_statement": _extract_latest(
                income,
                ["报告期", "*净利润", "*营业总收入", "*扣除非经常性损益后的净利润", "研发费用", "财务费用", "营业利润"],
                4,
            ),
            "cashflow_statement": _extract_latest(
                cashflow,
                ["报告期", "*经营活动产生的现金流量净额", "*投资活动产生的现金流量净额", "*筹资活动产生的现金流量净额", "*期末现金及现金等价物余额"],
                4,
            ),
            "balance_sheet": _extract_latest(
                balance,
                ["报告期", "*资产合计", "*负债合计", "短期借款", "应收账款", "存货", "商誉", "归属于母公司所有者权益合计"],
                4,
            ),
            "financial_questions": _financial_questions(financial, income, cashflow, balance),
            "announcement_focus": notice_titles[:8],
            "source_status": source_status,
        },
    }


def _fetch_structured_inputs(code: str) -> dict[str, dict[str, Any]]:
    symbol = _ak_hot_symbol(code)
    jobs: list[tuple[str, Callable[[], Any]]] = [
        ("akshare_stock_news_em", lambda: _ak().stock_news_em(symbol=code)),
        (
            "akshare_notice",
            lambda: _ak().stock_individual_notice_report(
                security=code,
                begin_date=_notice_begin_date(),
                end_date=_notice_end_date(),
            ),
        ),
        ("akshare_hot_keyword", lambda: _ak().stock_hot_keyword_em(symbol=symbol)),
        ("akshare_business_intro_ths", lambda: _ak().stock_zyjs_ths(symbol=code)),
        ("akshare_financial_abstract_ths", lambda: _ak().stock_financial_abstract_ths(symbol=code, indicator="按报告期")),
        ("akshare_income_ths", lambda: _ak().stock_financial_benefit_ths(symbol=code, indicator="按报告期")),
        ("akshare_cashflow_ths", lambda: _ak().stock_financial_cash_ths(symbol=code, indicator="按报告期")),
        ("akshare_balance_ths", lambda: _ak().stock_financial_debt_ths(symbol=code, indicator="按报告期")),
        ("tencent_realtime_quote", lambda: fetch_realtime_quote(code)),
    ]
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = {executor.submit(_timed, label, fn): label for label, fn in jobs}
        for future in as_completed(futures):
            label, seconds, data, error = future.result()
            item: dict[str, Any] = {"seconds": seconds, "error": error}
            if isinstance(data, pd.DataFrame):
                item["shape"] = list(data.shape)
                item["columns"] = [str(col) for col in data.columns]
                item["records"] = _records(data, 10)
            elif data is not None:
                item["data"] = _object_to_dict(data)
            results[label] = item
    return results


def _timed(label: str, fn: Callable[[], Any]) -> tuple[str, float, Any, str | None]:
    import time

    started = time.perf_counter()
    try:
        data = fn()
        return label, round(time.perf_counter() - started, 3), data, None
    except Exception as exc:
        return label, round(time.perf_counter() - started, 3), None, f"{type(exc).__name__}: {exc}"


def _ak() -> Any:
    import akshare as ak

    return ak


def _notice_begin_date() -> str:
    try:
        days = int(os.getenv("WORKBENCH_NOTICE_LOOKBACK_DAYS", "120").strip())
    except Exception:
        days = 120
    return (date.today() - timedelta(days=max(1, days))).strftime("%Y%m%d")


def _notice_end_date() -> str:
    return date.today().strftime("%Y%m%d")


def _records(df: Any, limit: int = 8) -> list[dict[str, str]]:
    if df is None or not hasattr(df, "empty") or df.empty:
        return []
    source = df.copy()
    if "报告期" in source.columns:
        source = source.sort_values("报告期", ascending=False)
    out = source.head(limit).copy()
    for col in out.columns:
        out[col] = out[col].map(_clean_value)
    return out.to_dict(orient="records")


def _extract_latest(rows: list[dict[str, str]], keys: list[str], limit: int = 3) -> list[dict[str, str]]:
    extracted: list[dict[str, str]] = []
    for row in rows[:limit]:
        item = {key: _clean_value(row.get(key)) for key in keys if _clean_value(row.get(key))}
        if item:
            extracted.append(item)
    return extracted


def _first_texts(rows: list[dict[str, str]], key: str, limit: int = 8) -> list[str]:
    return [_clean_value(row.get(key)) for row in rows[:limit] if _clean_value(row.get(key))]


def _source_status(item: dict[str, Any]) -> str:
    if item.get("error"):
        return "error"
    if item.get("records") or item.get("data"):
        return "ok"
    return "empty"


def _market_hype_reason(news_titles: list[str], hot_names: list[str], quote: dict[str, Any]) -> str:
    pieces: list[str] = []
    if news_titles:
        pieces.append("近期新闻/异动线索包括：" + "；".join(news_titles[:4]))
    if hot_names:
        pieces.append("热词集中在：" + "、".join(hot_names[:5]))
    if quote:
        pieces.append(f"腾讯实时行情显示现价 {quote.get('price')}，涨跌幅 {quote.get('pct_chg')}%。")
    return " ".join(pieces) or "最近炒作原因待验证"


def _traded_business_line(business: dict[str, str], hot_names: list[str]) -> str:
    products = _clean_value(business.get("产品名称") or business.get("产品类型") or business.get("主营业务"))
    hot = "、".join(hot_names[:4])
    if products and hot:
        return f"{products}；市场热词：{hot}"
    return products or hot or "待验证"


def _what_market_is_pricing(hot_names: list[str], business: dict[str, str]) -> str:
    hot = "、".join(hot_names[:5])
    main_business = _clean_value(business.get("主营业务"))
    if hot and main_business:
        return f"市场可能在定价 {hot} 等主题对公司 {main_business} 的业绩弹性。"
    if hot:
        return f"市场可能在定价 {hot} 等主题弹性，但公司业务匹配度仍需验证。"
    return "市场定价主线待验证"


def _evidence_quality(news: list[dict[str, str]], notices: list[dict[str, str]], business: list[dict[str, str]], financial: list[dict[str, str]]) -> str:
    score = sum(bool(item) for item in (news, notices, business, financial))
    if score >= 3:
        return "medium"
    return "low"


def _missing_unknowns(*groups: list[dict[str, str]]) -> list[str]:
    labels = [
        "新闻/异动数据缺失或为空",
        "公告数据缺失或为空",
        "热词/概念数据缺失或为空",
        "主营业务数据缺失或为空",
        "财务摘要数据缺失或为空",
        "利润表数据缺失或为空",
        "现金流量表数据缺失或为空",
        "资产负债表数据缺失或为空",
    ]
    return [label for label, group in zip(labels, groups) if not group]


def _infer_chain_node(business: dict[str, str], hot_names: list[str]) -> str:
    text = " ".join([business.get("主营业务", ""), business.get("产品类型", ""), business.get("产品名称", ""), " ".join(hot_names)])
    if "光" in text and ("模块" in text or "通信" in text):
        return "需区分公司实际处在高速光模块核心环节，还是光纤光缆/通信设备等成熟制造环节。"
    if "新能源" in text:
        return "需验证新能源业务收入和利润占比，以及是否为当前股价交易主线。"
    return "产业链位置待验证。"


def _profit_pool_hints(hot_names: list[str]) -> list[str]:
    text = " ".join(hot_names)
    if "光" in text:
        return [
            "高速光模块、光芯片、激光器、DSP 等环节通常具备更高利润弹性",
            "光纤光缆和通信电缆更偏成熟制造，利润率和估值弹性通常低于高速光模块核心环节",
            "需要用主营构成、客户、订单和毛利率验证公司是否真的享受高利润池",
        ]
    return [
        "先判断市场交易的主题是否对应公司实际收入和利润来源",
        "再用毛利率、费用率、现金流和订单信息验证估值弹性",
    ]


def _peer_reference(hot_names: list[str]) -> list[str]:
    text = " ".join(hot_names)
    if "光" in text:
        return [
            "高速光模块链：中际旭创、新易盛、天孚通信",
            "光纤光缆/通信设备链：中天科技、亨通光电、烽火通信",
        ]
    return []


def _financial_questions(
    financial: list[dict[str, str]],
    income: list[dict[str, str]],
    cashflow: list[dict[str, str]],
    balance: list[dict[str, str]],
) -> list[str]:
    questions = []
    if financial:
        questions.append("收入增速、利润增速、毛利率和资产负债率是否支持当前题材估值。")
    if income:
        questions.append("净利润、扣非净利润、研发费用、财务费用和营业利润是否能验证业务线景气。")
    if cashflow:
        questions.append("经营现金流是否与利润匹配，投资/筹资现金流是否带来资产负债压力。")
    if balance:
        questions.append("短期借款、应收账款、存货和商誉是否限制估值赔率。")
    return questions or ["财务数据缺失，Public Equity 判断需要降低证据质量。"]


def _object_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {"value": str(value)}


def _clean_value(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text in {"False", "nan", "NaT", "None"} else text


def _clean_code(code: str) -> str:
    digits = "".join(ch for ch in str(code or "") if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else str(code or "").strip()


def _ak_hot_symbol(code: str) -> str:
    digits = _clean_code(code)
    return f"SH{digits}" if digits.startswith(("6", "5", "9")) else f"SZ{digits}"
