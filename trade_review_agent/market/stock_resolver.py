from __future__ import annotations

import json
from pathlib import Path

from trade_review_agent.common.cache_policy import report_cache_disabled


BASE_DIR = Path(__file__).resolve().parents[2]
CACHE_PATH = BASE_DIR / "work" / "stock_code_name_cache.json"

KNOWN_CODES = {
    "东材科技": "601208",
    "黄河旋风": "600172",
    "长电科技": "600584",
    "风华高科": "000636",
    "华天科技": "002185",
    "鹏鼎控股": "002938",
    "中国巨石": "600176",
    "生益科技": "600183",
    "沪电股份": "002463",
    "深南电路": "002916",
    "胜宏科技": "300476",
    "兴森科技": "002436",
    "方正科技": "600601",
}


def resolve_stock_code(name: str | None, *, allow_fetch: bool = True) -> str:
    text = _clean_name(name)
    if not text:
        return ""
    direct_code = _extract_code(text)
    if direct_code:
        return direct_code
    if text in KNOWN_CODES:
        return KNOWN_CODES[text]

    mapping = _load_cached_mapping()
    if text in mapping:
        return mapping[text]

    if not allow_fetch:
        for stock_name, code in mapping.items():
            if text in stock_name or stock_name in text:
                return code
        return ""

    mapping = _fetch_mapping()
    if text in mapping:
        return mapping[text]

    for stock_name, code in mapping.items():
        if text in stock_name or stock_name in text:
            return code
    return ""


def _clean_name(name: str | None) -> str:
    if not name:
        return ""
    return str(name).strip().replace(" ", "")


def _extract_code(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) >= 6:
        return digits[-6:]
    return ""


def _load_cached_mapping() -> dict[str, str]:
    if report_cache_disabled():
        return {}
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value).zfill(6)[-6:] for key, value in data.items() if value}


def _fetch_mapping() -> dict[str, str]:
    try:
        import akshare as ak

        frame = ak.stock_info_a_code_name()
    except Exception:
        return {}

    if frame.empty:
        return {}

    columns = {str(col).lower(): col for col in frame.columns}
    code_col = columns.get("code") or columns.get("证券代码") or columns.get("代码")
    name_col = columns.get("name") or columns.get("证券简称") or columns.get("名称")
    if code_col is None or name_col is None:
        return {}

    mapping: dict[str, str] = {}
    for row in frame[[code_col, name_col]].dropna().itertuples(index=False):
        code = "".join(ch for ch in str(row[0]) if ch.isdigit())
        name = _clean_name(str(row[1]))
        if code and name:
            mapping[name] = code.zfill(6)[-6:]

    if mapping and not report_cache_disabled():
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    return mapping
