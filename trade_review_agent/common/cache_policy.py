from __future__ import annotations

import os


def report_cache_disabled() -> bool:
    value = os.getenv("REPORT_DISABLE_CACHE", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}
