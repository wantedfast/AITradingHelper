from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


UNKNOWN_FAMILY = "unknown"

FAMILY_KPIS: dict[str, tuple[str, ...]] = {
    "manufacturing": (
        "revenue_growth",
        "gross_margin",
        "capacity_utilization",
        "order_backlog",
        "inventory_turnover",
    ),
    "financials": (
        "net_interest_margin",
        "nonperforming_loan_ratio",
        "capital_adequacy_ratio",
        "return_on_equity",
        "provision_coverage_ratio",
    ),
    "software_internet": (
        "annual_recurring_revenue",
        "revenue_growth",
        "gross_margin",
        "customer_retention",
        "sales_efficiency",
    ),
    "healthcare": (
        "pipeline_stage",
        "clinical_milestones",
        "regulatory_status",
        "product_revenue",
        "research_and_development_intensity",
    ),
    "consumer": (
        "same_store_sales_growth",
        "revenue_growth",
        "gross_margin",
        "inventory_turnover",
        "channel_growth",
    ),
    "resources_utilities": (
        "commodity_price_exposure",
        "production_volume",
        "unit_cost",
        "reserve_or_capacity",
        "capital_expenditure",
    ),
    UNKNOWN_FAMILY: (),
}

_FAMILY_TERMS: dict[str, tuple[str, ...]] = {
    "manufacturing": (
        "制造",
        "工业",
        "机械",
        "设备",
        "汽车零部件",
        "半导体设备",
        "电子制造",
        "manufacturing",
        "industrial",
        "machinery",
    ),
    "financials": (
        "银行",
        "保险",
        "证券",
        "券商",
        "金融",
        "banking",
        "insurance",
        "brokerage",
        "financial services",
    ),
    "software_internet": (
        "软件",
        "互联网",
        "云计算",
        "saas",
        "游戏",
        "software",
        "internet",
        "cloud computing",
    ),
    "healthcare": (
        "医药",
        "医疗",
        "生物科技",
        "创新药",
        "医疗器械",
        "pharmaceutical",
        "biotechnology",
        "healthcare",
        "medical device",
    ),
    "consumer": (
        "消费",
        "零售",
        "食品饮料",
        "家电",
        "服装",
        "consumer",
        "retail",
        "food and beverage",
        "apparel",
    ),
    "resources_utilities": (
        "资源",
        "公用事业",
        "电力",
        "煤炭",
        "石油",
        "天然气",
        "有色金属",
        "矿业",
        "utilities",
        "power generation",
        "coal",
        "oil and gas",
        "mining",
    ),
}

_METADATA_FIELDS = (
    "sector",
    "industry",
    "industry_name",
    "sector_name",
    "theme",
)

_KPI_PATHS: dict[str, tuple[str, ...]] = {
    "revenue_growth": ("financials.revenue_growth", "financial_data.revenue_growth"),
    "gross_margin": ("financials.gross_margin", "financial_data.gross_margin"),
    "capacity_utilization": ("operations.capacity_utilization", "kpis.capacity_utilization"),
    "order_backlog": ("operations.order_backlog", "kpis.order_backlog"),
    "inventory_turnover": ("financials.inventory_turnover", "kpis.inventory_turnover"),
    "net_interest_margin": ("financials.net_interest_margin", "kpis.net_interest_margin"),
    "nonperforming_loan_ratio": (
        "financials.nonperforming_loan_ratio",
        "kpis.nonperforming_loan_ratio",
    ),
    "capital_adequacy_ratio": ("financials.capital_adequacy_ratio", "kpis.capital_adequacy_ratio"),
    "return_on_equity": ("financials.return_on_equity", "kpis.return_on_equity"),
    "provision_coverage_ratio": (
        "financials.provision_coverage_ratio",
        "kpis.provision_coverage_ratio",
    ),
    "annual_recurring_revenue": (
        "operations.annual_recurring_revenue",
        "kpis.annual_recurring_revenue",
    ),
    "customer_retention": ("operations.customer_retention", "kpis.customer_retention"),
    "sales_efficiency": ("operations.sales_efficiency", "kpis.sales_efficiency"),
    "pipeline_stage": ("operations.pipeline_stage", "kpis.pipeline_stage"),
    "clinical_milestones": ("operations.clinical_milestones", "kpis.clinical_milestones"),
    "regulatory_status": ("operations.regulatory_status", "kpis.regulatory_status"),
    "product_revenue": ("financials.product_revenue", "kpis.product_revenue"),
    "research_and_development_intensity": (
        "financials.research_and_development_intensity",
        "kpis.research_and_development_intensity",
    ),
    "same_store_sales_growth": (
        "operations.same_store_sales_growth",
        "kpis.same_store_sales_growth",
    ),
    "channel_growth": ("operations.channel_growth", "kpis.channel_growth"),
    "commodity_price_exposure": (
        "operations.commodity_price_exposure",
        "kpis.commodity_price_exposure",
    ),
    "production_volume": ("operations.production_volume", "kpis.production_volume"),
    "unit_cost": ("operations.unit_cost", "kpis.unit_cost"),
    "reserve_or_capacity": ("operations.reserve_or_capacity", "kpis.reserve_or_capacity"),
    "capital_expenditure": ("financials.capital_expenditure", "kpis.capital_expenditure"),
}


def build_industry_coverage(
    *,
    company: dict[str, Any] | None = None,
    profile: Any = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify an industry family only from explicit industry metadata."""
    context = context if isinstance(context, dict) else {}
    candidates = _metadata_candidates(company, profile, context)
    matches: dict[str, list[str]] = {}
    for path, value in candidates:
        families = _families_for_text(value)
        for family in families:
            matches.setdefault(family, []).append(f"{path}={value}")

    if len(matches) == 1:
        family = next(iter(matches))
        evidence = matches[family]
        confidence = 0.9 if any(item.startswith(("company.sector=", "profile.sector=")) for item in evidence) else 0.75
        source = "; ".join(evidence)
    elif len(matches) > 1:
        family = UNKNOWN_FAMILY
        confidence = 0.0
        source = "conflicting explicit metadata: " + "; ".join(
            evidence for values in matches.values() for evidence in values
        )
    else:
        family = UNKNOWN_FAMILY
        confidence = 0.0
        source = "no explicit sector/theme/profile metadata matched"

    required = list(FAMILY_KPIS[family])
    available = [kpi for kpi in required if _kpi_available(context, kpi)]
    return {
        "family": family,
        "required_kpis": required,
        "available_kpis": available,
        "missing_kpis": [kpi for kpi in required if kpi not in available],
        "confidence": confidence,
        "source": source,
    }


def _metadata_candidates(
    company: dict[str, Any] | None,
    profile: Any,
    context: dict[str, Any],
) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    objects = (
        ("company", company if isinstance(company, dict) else context.get("company")),
        ("profile", _object_dict(profile)),
        ("context", context),
    )
    for prefix, value in objects:
        if not isinstance(value, dict):
            continue
        for field in _METADATA_FIELDS:
            text = str(value.get(field) or "").strip()
            if text and not _is_placeholder(text):
                result.append((f"{prefix}.{field}", text))
    return result


def _object_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    if is_dataclass(value):
        return asdict(value)
    return {
        field: getattr(value, field)
        for field in _METADATA_FIELDS
        if hasattr(value, field)
    }


def _families_for_text(value: str) -> set[str]:
    normalized = value.casefold()
    return {
        family
        for family, terms in _FAMILY_TERMS.items()
        if any(term.casefold() in normalized for term in terms)
    }


def _kpi_available(context: dict[str, Any], kpi: str) -> bool:
    return any(_has_value(_read_path(context, path)) for path in _KPI_PATHS.get(kpi, ()))


def _read_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _has_value(value: Any) -> bool:
    if value in (None, "", [], {}):
        return False
    if isinstance(value, str):
        normalized = value.strip().casefold()
        return normalized not in {
            "missing",
            "unknown",
            "pending",
            "pending fetch",
            "pending verification",
            "待验证",
            "待确认",
            "尚未生成",
        }
    return True


def _is_placeholder(value: str) -> bool:
    normalized = value.casefold()
    return any(
        marker in normalized
        for marker in ("待生成", "待识别", "待验证", "pending", "unknown", "missing")
    )
