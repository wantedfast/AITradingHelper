from __future__ import annotations

from importlib import import_module
from typing import Any, Callable, Protocol

import pandas as pd


class ValuationWebSearchFallback(Protocol):
    """Reserved extension point; the production pipeline does not invoke it."""

    def __call__(self, *, code: str, missing_fields: list[str]) -> dict[str, Any]: ...


AkshareLoader = Callable[[], Any]
TencentFetcher = Callable[[str], dict[str, Any]]

VALUATION_FIELDS = ("pe_ttm", "pb", "ps", "ev_ebitda", "pe_percentile", "pb_percentile", "ps_percentile")


def fetch_valuation_snapshot(
    code: str,
    *,
    akshare_loader: AkshareLoader | None = None,
    tencent_fetcher: TencentFetcher | None = None,
    web_search_fallback: ValuationWebSearchFallback | None = None,
    minimum_history: int = 20,
) -> dict[str, Any]:
    """Fetch verifiable valuation metrics without inventing unavailable values."""
    normalized = _normalize_code(code)
    values = {field: None for field in VALUATION_FIELDS}
    errors: list[str] = []
    providers_attempted: list[str] = []
    as_of = ""
    observations: dict[str, int] = {}
    field_providers: dict[str, str] = {}

    try:
        ak = (akshare_loader or _load_akshare)()
        providers_attempted.append("akshare.stock_value_em")
        history = ak.stock_value_em(symbol=normalized)
        parsed, parsed_as_of, parsed_observations = _parse_stock_value_history(
            history,
            minimum_history=minimum_history,
        )
        values.update(parsed)
        field_providers.update(
            {field: "akshare.stock_value_em" for field, value in parsed.items() if value is not None}
        )
        as_of = parsed_as_of
        observations.update(parsed_observations)

        if values["ev_ebitda"] is None:
            providers_attempted.append("akshare.stock_zh_valuation_comparison_em")
            comparison = ak.stock_zh_valuation_comparison_em(symbol=_eastmoney_symbol(normalized))
            values["ev_ebitda"] = _parse_ev_ebitda(comparison, normalized)
            if values["ev_ebitda"] is not None:
                field_providers["ev_ebitda"] = "akshare.stock_zh_valuation_comparison_em"
    except Exception as exc:
        errors.append(f"AKShare unavailable: {exc}")

    if tencent_fetcher is not None and _missing_core_values(values):
        providers_attempted.append("tencent_finance")
        try:
            tencent_values = tencent_fetcher(normalized)
            for field in ("pe_ttm", "pb", "ps", "ev_ebitda"):
                if values[field] is None:
                    values[field] = _finite_number(tencent_values.get(field))
                    if values[field] is not None:
                        field_providers[field] = "tencent_finance"
            as_of = as_of or str(tencent_values.get("as_of") or "")
        except Exception as exc:
            errors.append(f"Tencent Finance unavailable: {exc}")

    # Intentionally unused. It exists so a later, explicitly enabled search
    # adapter can be added without turning narrative search results into facts.
    _ = web_search_fallback

    populated = [field for field, value in values.items() if value is not None]
    return {
        **values,
        "status": "available" if populated else "unavailable",
        "provider": " + ".join(sorted(set(field_providers.values()))) if populated else None,
        "providers_attempted": providers_attempted,
        "as_of": as_of or None,
        "observations": observations,
        "missing_fields": [field for field in VALUATION_FIELDS if values[field] is None],
        "errors": errors,
        "web_search_fallback": {
            "configured": web_search_fallback is not None,
            "invoked": False,
        },
        "source_trace": {
            field: {
                "source": "provider" if values[field] is not None else "missing",
                "provider": field_providers.get(field),
                "as_of": as_of or None,
            }
            for field in VALUATION_FIELDS
        },
    }


def _load_akshare() -> Any:
    return import_module("akshare")


def _parse_stock_value_history(
    frame: Any,
    *,
    minimum_history: int,
) -> tuple[dict[str, float | None], str, dict[str, int]]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("stock_value_em returned no rows")
    data = frame.copy()
    date_column = _first_column(data, ("数据日期", "date", "日期"))
    if date_column:
        data[date_column] = pd.to_datetime(data[date_column], errors="coerce")
        data = data.sort_values(date_column)
    latest = data.iloc[-1]
    mappings = {
        "pe_ttm": ("PE(TTM)", "市盈率(TTM)", "pe_ttm"),
        "pb": ("市净率", "PB", "pb"),
        "ps": ("市销率", "PS", "ps"),
    }
    values: dict[str, float | None] = {}
    observations: dict[str, int] = {}
    for field, candidates in mappings.items():
        column = _first_column(data, candidates)
        values[field] = _finite_number(latest.get(column)) if column else None
        series = pd.to_numeric(data[column], errors="coerce").dropna() if column else pd.Series(dtype=float)
        observations[field] = int(series.size)
        values[f"{field.split('_')[0]}_percentile" if field != "pe_ttm" else "pe_percentile"] = (
            _percentile_rank(series, values[field]) if series.size >= minimum_history else None
        )
    values["ev_ebitda"] = None
    as_of = ""
    if date_column and pd.notna(latest.get(date_column)):
        as_of = pd.Timestamp(latest[date_column]).date().isoformat()
    return values, as_of, observations


def _parse_ev_ebitda(frame: Any, code: str) -> float | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    code_column = _first_column(frame, ("代码", "SECURITY_CODE", "code"))
    value_column = _first_column(frame, ("EV/EBITDA-24A", "EV/EBITDA", "ev_ebitda"))
    if not code_column or not value_column:
        return None
    matches = frame[frame[code_column].astype(str).str.zfill(6) == code]
    if matches.empty:
        return None
    return _finite_number(matches.iloc[0].get(value_column))


def _percentile_rank(series: pd.Series, current: float | None) -> float | None:
    if current is None or series.empty:
        return None
    finite = pd.to_numeric(series, errors="coerce").dropna()
    if finite.empty:
        return None
    return round(float((finite <= current).mean() * 100), 2)


def _missing_core_values(values: dict[str, Any]) -> bool:
    return all(values.get(field) is None for field in ("pe_ttm", "pb", "ps", "ev_ebitda"))


def _normalize_code(code: str) -> str:
    digits = "".join(character for character in str(code) if character.isdigit())
    if not digits:
        raise ValueError("A-share code is required")
    return digits[-6:].zfill(6)


def _eastmoney_symbol(code: str) -> str:
    return f"SH{code}" if code.startswith(("5", "6", "9")) else f"SZ{code}"


def _first_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    return next((column for column in candidates if column in frame.columns), None)


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number) or number in (float("inf"), float("-inf")):
        return None
    return round(number, 4)
