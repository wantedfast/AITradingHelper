from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

import pandas as pd


FINANCIAL_FIELDS = (
    "revenue",
    "revenue_growth",
    "net_profit",
    "profit_growth",
    "gross_margin",
    "operating_cash_flow",
    "free_cash_flow",
    "total_liabilities",
    "debt_to_assets",
    "roe",
)

_INTERNAL_FIELDS = ("total_assets", "operating_cost", "capital_expenditure")
_PERCENT_FIELDS = {"revenue_growth", "profit_growth", "gross_margin", "debt_to_assets", "roe"}
_CACHE_TABLE = "financial_fundamentals"


class WebSearchFinancialFallback(Protocol):
    """Reserved protocol for a future evidence-bearing web search adapter.

    FinancialDataProvider deliberately does not call this protocol. A future
    integration must normalize searched facts through the same field-level
    provenance contract before enabling it.
    """

    def fetch(self, code: str) -> Mapping[str, Any]: ...


FrameFetcher = Callable[[str], Mapping[str, pd.DataFrame]]


class FinancialDataProvider:
    """Fault-tolerant A-share financial statement adapter.

    AkShare is the default financial source. The repository's Tencent endpoint
    only provides quotes/K-lines, so no Tencent financial fetcher is installed
    by default. An independently verified Tencent adapter can be injected later.
    """

    def __init__(
        self,
        cache_db: str | Path,
        *,
        offline: bool = False,
        cache_ttl: timedelta = timedelta(hours=24),
        akshare_fetcher: FrameFetcher | None = None,
        tencent_fetcher: FrameFetcher | None = None,
        web_search_fallback: WebSearchFinancialFallback | None = None,
    ) -> None:
        self.cache_db = Path(cache_db)
        self.offline = offline
        self.cache_ttl = cache_ttl
        self.akshare_fetcher = akshare_fetcher or _fetch_akshare_financial_frames
        self.tencent_fetcher = tencent_fetcher
        self.web_search_fallback = web_search_fallback
        if str(self.cache_db) != ":memory:":
            self.cache_db.parent.mkdir(parents=True, exist_ok=True)

    def get_financials(self, code: str) -> dict[str, Any]:
        symbol = _a_share_code(code)
        cached = self._read_cache(symbol)
        if self.offline:
            if cached is not None:
                return _mark_cached(cached, stale=False)
            return _empty_result(
                symbol,
                errors=["offline mode: no cached financial data"],
                web_search_available=self.web_search_fallback is not None,
            )
        if cached is not None and self._cache_is_fresh(cached):
            return _mark_cached(cached, stale=False)

        attempts: list[dict[str, str]] = []
        errors: list[str] = []
        for provider, fetcher in self._provider_chain():
            try:
                frames = fetcher(symbol)
                result = normalize_financial_frames(symbol, frames, provider=provider)
            except Exception as exc:
                message = f"{provider} financial fetch failed: {type(exc).__name__}: {exc}"
                errors.append(message)
                attempts.append({"provider": provider, "status": "error", "detail": message})
                continue

            if result["status"] != "missing":
                attempts.append({"provider": provider, "status": result["status"], "detail": "financial fields returned"})
                result["errors"] = errors + list(result["errors"])
                result["provider_attempts"] = attempts + self._skipped_attempts()
                result["web_search_fallback"] = self._web_search_status()
                self._write_cache(symbol, result)
                return result

            message = f"{provider} returned no supported financial fields"
            errors.extend(result["errors"])
            errors.append(message)
            attempts.append({"provider": provider, "status": "missing", "detail": message})

        attempts.extend(self._skipped_attempts())
        if cached is not None:
            fallback = _mark_cached(cached, stale=True)
            fallback["errors"] = errors + list(fallback.get("errors", []))
            fallback["provider_attempts"] = attempts
            fallback["web_search_fallback"] = self._web_search_status()
            return fallback

        result = _empty_result(
            symbol,
            errors=errors,
            web_search_available=self.web_search_fallback is not None,
        )
        result["provider_attempts"] = attempts
        return result

    def _provider_chain(self) -> list[tuple[str, FrameFetcher]]:
        providers: list[tuple[str, FrameFetcher]] = [("akshare", self.akshare_fetcher)]
        if self.tencent_fetcher is not None:
            providers.append(("tencent_finance", self.tencent_fetcher))
        return providers

    def _skipped_attempts(self) -> list[dict[str, str]]:
        if self.tencent_fetcher is not None:
            return []
        return [
            {
                "provider": "tencent_finance",
                "status": "skipped",
                "detail": "existing Tencent integration exposes quotes/K-lines, not verified financial statements",
            }
        ]

    def _web_search_status(self) -> dict[str, Any]:
        return {
            "available": self.web_search_fallback is not None,
            "invoked": False,
            "status": "reserved_not_called",
        }

    def _cache_is_fresh(self, payload: Mapping[str, Any]) -> bool:
        fetched_at = _parse_datetime(payload.get("fetched_at"))
        if fetched_at is None:
            return False
        return datetime.now(timezone.utc) - fetched_at <= self.cache_ttl

    def _read_cache(self, code: str) -> dict[str, Any] | None:
        if str(self.cache_db) != ":memory:" and not self.cache_db.exists():
            return None
        try:
            with closing(sqlite3.connect(self.cache_db)) as conn:
                row = conn.execute(
                    f"SELECT payload FROM {_CACHE_TABLE} WHERE code = ?",
                    (code,),
                ).fetchone()
        except (sqlite3.Error, OSError, ValueError):
            return None
        if not row:
            return None
        try:
            payload = json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _write_cache(self, code: str, payload: Mapping[str, Any]) -> None:
        try:
            with closing(sqlite3.connect(self.cache_db)) as conn:
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_CACHE_TABLE} (
                        code TEXT PRIMARY KEY,
                        fetched_at TEXT NOT NULL,
                        payload TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    f"""
                    INSERT OR REPLACE INTO {_CACHE_TABLE} (code, fetched_at, payload)
                    VALUES (?, ?, ?)
                    """,
                    (
                        code,
                        str(payload.get("fetched_at") or datetime.now(timezone.utc).isoformat()),
                        json.dumps(payload, ensure_ascii=False, allow_nan=False),
                    ),
                )
                conn.commit()
        except (sqlite3.Error, OSError, TypeError, ValueError):
            return


def normalize_financial_frames(
    code: str,
    frames: Mapping[str, pd.DataFrame] | None,
    *,
    provider: str,
) -> dict[str, Any]:
    observations: dict[str, list[tuple[str, float, str]]] = {
        field: [] for field in (*FINANCIAL_FIELDS, *_INTERNAL_FIELDS)
    }
    errors: list[str] = []
    for dataset, frame in (frames or {}).items():
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        try:
            _collect_frame_observations(frame, str(dataset), observations)
        except Exception as exc:
            errors.append(f"{dataset} normalization failed: {type(exc).__name__}: {exc}")

    selected = {field: _latest_observation(values) for field, values in observations.items()}
    _derive_fields(selected)
    result = _empty_result(code, errors=errors)
    populated = 0
    as_of_dates: list[str] = []
    for field in FINANCIAL_FIELDS:
        observation = selected.get(field)
        if observation is None:
            continue
        as_of, value, dataset = observation
        result[field] = value
        result["source_trace"][field] = {
            "source": "real_data",
            "provider": provider,
            "dataset": dataset,
            "as_of": as_of,
            "unit": "percent" if field in _PERCENT_FIELDS else "CNY",
            "status": "verified",
            "errors": [],
        }
        populated += 1
        if as_of:
            as_of_dates.append(as_of)

    result["as_of"] = max(as_of_dates) if as_of_dates else None
    result["provider"] = provider if populated else None
    result["status"] = "ok" if populated == len(FINANCIAL_FIELDS) else ("partial" if populated else "missing")
    result["fetched_at"] = datetime.now(timezone.utc).isoformat()
    result["web_search_fallback"] = {
        "available": False,
        "invoked": False,
        "status": "reserved_not_called",
    }
    return result


def _fetch_akshare_financial_frames(code: str) -> Mapping[str, pd.DataFrame]:
    import akshare as ak

    em_symbol = _eastmoney_symbol(code)
    start_year = str(datetime.now().year - 5)
    calls: tuple[tuple[str, Callable[[], pd.DataFrame]], ...] = (
        ("abstract", lambda: ak.stock_financial_abstract(symbol=code)),
        (
            "indicators",
            lambda: ak.stock_financial_analysis_indicator(symbol=code, start_year=start_year),
        ),
        ("balance_sheet", lambda: ak.stock_balance_sheet_by_report_em(symbol=em_symbol)),
        ("cash_flow", lambda: ak.stock_cash_flow_sheet_by_report_em(symbol=em_symbol)),
    )
    frames: dict[str, pd.DataFrame] = {}
    failures: list[str] = []
    for name, call in calls:
        try:
            frames[name] = call()
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    if not frames and failures:
        raise RuntimeError("; ".join(failures))
    return frames


def _collect_frame_observations(
    frame: pd.DataFrame,
    dataset: str,
    observations: dict[str, list[tuple[str, float, str]]],
) -> None:
    columns = {str(column): _normalize_label(column) for column in frame.columns}
    metric_column = _find_column(columns, {"指标", "项目", "metric", "metricname", "itemname"})
    if metric_column is not None:
        _collect_metric_matrix(frame, metric_column, dataset, observations)
        return

    date_column = _find_column(
        columns,
        {"日期", "报告日", "报告日期", "reportdate", "report_date", "enddate", "截止日期"},
    )
    if date_column is None:
        return
    for _, row in frame.iterrows():
        as_of = _normalize_period(row.get(date_column))
        if not as_of:
            continue
        for column in frame.columns:
            field = _canonical_field(column)
            value = _number(row.get(column))
            if field and value is not None:
                observations[field].append((as_of, value, dataset))


def _collect_metric_matrix(
    frame: pd.DataFrame,
    metric_column: Any,
    dataset: str,
    observations: dict[str, list[tuple[str, float, str]]],
) -> None:
    for _, row in frame.iterrows():
        field = _canonical_field(row.get(metric_column))
        if not field:
            continue
        for column in frame.columns:
            if column == metric_column:
                continue
            as_of = _normalize_period(column)
            value = _number(row.get(column))
            if as_of and value is not None:
                observations[field].append((as_of, value, dataset))


def _derive_fields(selected: dict[str, tuple[str, float, str] | None]) -> None:
    if selected.get("gross_margin") is None:
        revenue = selected.get("revenue")
        cost = selected.get("operating_cost")
        if revenue and cost and revenue[0] == cost[0] and revenue[1]:
            selected["gross_margin"] = (
                revenue[0],
                (revenue[1] - cost[1]) / revenue[1] * 100,
                "calculated:revenue-operating_cost",
            )
    if selected.get("debt_to_assets") is None:
        liabilities = selected.get("total_liabilities")
        assets = selected.get("total_assets")
        if liabilities and assets and liabilities[0] == assets[0] and assets[1]:
            selected["debt_to_assets"] = (
                assets[0],
                liabilities[1] / assets[1] * 100,
                "calculated:total_liabilities/total_assets",
            )
    cash = selected.get("operating_cash_flow")
    capex = selected.get("capital_expenditure")
    if selected.get("free_cash_flow") is None and cash and capex and cash[0] == capex[0]:
        selected["free_cash_flow"] = (
            cash[0],
            cash[1] - abs(capex[1]),
            "calculated:operating_cash_flow-capital_expenditure",
        )


def _latest_observation(values: list[tuple[str, float, str]]) -> tuple[str, float, str] | None:
    if not values:
        return None
    return max(values, key=lambda item: item[0])


def _canonical_field(label: Any) -> str | None:
    normalized = _normalize_label(label)
    aliases = {
        "revenue": {"营业总收入", "营业收入", "主营业务收入", "totaloperatereve", "operateincome", "revenue"},
        "revenue_growth": {
            "营业总收入同比增长",
            "营业收入同比增长",
            "主营业务收入增长率",
            "营业收入增长率",
            "totaloperatereveyoy",
            "operateincomeyoy",
            "revenuegrowth",
        },
        "net_profit": {"归母净利润", "净利润", "parentnetprofit", "netprofit", "netprofitparentcompany"},
        "profit_growth": {
            "归母净利润同比增长",
            "净利润同比增长",
            "净利润增长率",
            "parentnetprofityoy",
            "netprofityoy",
            "profitgrowth",
        },
        "gross_margin": {"销售毛利率", "毛利率", "grossprofitmargin", "grossmargin"},
        "operating_cash_flow": {
            "经营活动产生的现金流量净额",
            "经营现金净流量",
            "netcashoperate",
            "netcashflowoperating",
            "operatingcashflow",
        },
        "capital_expenditure": {
            "购建固定资产无形资产和其他长期资产支付的现金",
            "constructlongasset",
            "capitalexpenditure",
            "capex",
        },
        "total_liabilities": {"负债合计", "总负债", "totalliabilities", "totalliab"},
        "total_assets": {"资产总计", "总资产", "totalassets"},
        "debt_to_assets": {"资产负债率", "debttoassets", "debtassetratio"},
        "roe": {"净资产收益率", "加权净资产收益率", "roe", "weightedroe"},
        "operating_cost": {"营业成本", "主营业务成本", "totaloperatecost", "operatingcost"},
        "free_cash_flow": {"自由现金流", "freecashflow"},
    }
    for field, names in aliases.items():
        if normalized in {_normalize_label(name) for name in names}:
            return field
    return None


def _find_column(columns: Mapping[str, str], names: set[str]) -> str | None:
    normalized_names = {_normalize_label(name) for name in names}
    return next((original for original, normalized in columns.items() if normalized in normalized_names), None)


def _normalize_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(character for character in text if character.isalnum())


def _normalize_period(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("%", "")
        if not text or text in {"-", "--", "None", "nan"}:
            return None
        value = text
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return None
    return float(number)


def _empty_result(
    code: str,
    *,
    errors: list[str] | None = None,
    web_search_available: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {field: None for field in FINANCIAL_FIELDS}
    result.update(
        {
            "code": _a_share_code(code),
            "as_of": None,
            "provider": None,
            "status": "missing",
            "errors": list(errors or []),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source_trace": {
                field: {
                    "source": "missing",
                    "provider": None,
                    "dataset": None,
                    "as_of": None,
                    "unit": "percent" if field in _PERCENT_FIELDS else "CNY",
                    "status": "missing",
                    "errors": [],
                }
                for field in FINANCIAL_FIELDS
            },
            "provider_attempts": [],
            "web_search_fallback": {
                "available": web_search_available,
                "invoked": False,
                "status": "reserved_not_called",
            },
        }
    )
    return result


def _mark_cached(payload: Mapping[str, Any], *, stale: bool) -> dict[str, Any]:
    result = json.loads(json.dumps(payload, ensure_ascii=False))
    result["status"] = "fallback" if stale else "cached"
    result["provider"] = f"cache:{payload.get('provider') or 'unknown'}"
    for trace in result.get("source_trace", {}).values():
        if isinstance(trace, dict) and trace.get("source") != "missing":
            trace["source"] = "fallback"
            trace["provider"] = result["provider"]
            trace["status"] = "stale_cache" if stale else "cached"
    return result


def _a_share_code(code: str) -> str:
    digits = "".join(character for character in str(code or "") if character.isdigit())
    if len(digits) < 6:
        raise ValueError(f"invalid A-share code: {code!r}")
    return digits[-6:]


def _eastmoney_symbol(code: str) -> str:
    return ("SH" if code.startswith(("5", "6", "9")) else "SZ") + code


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
