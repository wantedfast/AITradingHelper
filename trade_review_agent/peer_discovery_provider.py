from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Callable

import pandas as pd

from .industry_profiles import IndustryProfile


FrameFetcher = Callable[..., pd.DataFrame]


@dataclass(frozen=True)
class PeerCandidate:
    name: str
    code: str
    universe_source: str
    universe_detail: str = ""


class PeerDiscoveryProvider:
    """Discover comparable A-share peers from data providers, not static sector lists."""

    def __init__(
        self,
        *,
        individual_info_fetcher: FrameFetcher | None = None,
        industry_cons_fetcher: FrameFetcher | None = None,
    ) -> None:
        self.individual_info_fetcher = individual_info_fetcher or _fetch_akshare_individual_info
        self.industry_cons_fetcher = industry_cons_fetcher or _fetch_akshare_industry_cons

    def discover(self, *, code: str, name: str = "", profile: IndustryProfile | None = None, limit: int = 6) -> list[PeerCandidate]:
        if os.getenv("PEER_DISCOVERY_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
            return _profile_peer_candidates(profile, target_code=code, limit=limit)

        industry = self._fetch_industry(code) or _industry_from_profile(profile)
        peers = self._fetch_industry_peers(code=code, industry=industry, limit=limit)
        if peers:
            return peers
        return _profile_peer_candidates(profile, target_code=code, limit=limit)

    def _fetch_industry(self, code: str) -> str:
        try:
            frame = self.individual_info_fetcher(symbol=_digits(code))
        except Exception:
            return ""
        return _extract_industry(frame)

    def _fetch_industry_peers(self, *, code: str, industry: str, limit: int) -> list[PeerCandidate]:
        if not industry:
            return []
        try:
            frame = self.industry_cons_fetcher(symbol=industry)
        except Exception:
            return []
        return _constituent_peers(frame, target_code=code, industry=industry, limit=limit)


def _fetch_akshare_individual_info(symbol: str) -> pd.DataFrame:
    import akshare as ak

    return ak.stock_individual_info_em(symbol=symbol)


def _fetch_akshare_industry_cons(symbol: str) -> pd.DataFrame:
    import akshare as ak

    return ak.stock_board_industry_cons_em(symbol=symbol)


def _profile_peer_candidates(profile: IndustryProfile | None, *, target_code: str, limit: int) -> list[PeerCandidate]:
    rows: list[PeerCandidate] = []
    for item in getattr(profile, "peers", ()) or ():
        text = str(item or "").strip()
        peer_code = _digits(text)
        if len(peer_code) < 6:
            continue
        clean_code = peer_code[-6:]
        clean_name = text.replace(clean_code, "").strip(" -_()") or clean_code
        rows.append(
            PeerCandidate(
                name=clean_name,
                code=clean_code,
                universe_source="profile",
                universe_detail="Industry profile peer list",
            )
        )
    return _dedupe_candidates(rows, target_code=target_code, limit=limit)


def _extract_industry(frame: pd.DataFrame) -> str:
    if frame.empty:
        return ""
    item_col = _find_column(frame, "item", "\u9879\u76ee")
    value_col = _find_column(frame, "value", "\u503c")
    if item_col is not None and value_col is not None:
        for row in frame[[item_col, value_col]].dropna().itertuples(index=False):
            label = str(row[0]).strip()
            if "\u884c\u4e1a" in label or label.lower() == "industry":
                return str(row[1]).strip()
    if len(frame.columns) >= 2:
        for row in frame.iloc[:, :2].dropna().itertuples(index=False):
            label = str(row[0]).strip()
            if "\u884c\u4e1a" in label or label.lower() == "industry":
                return str(row[1]).strip()
    return ""


def _constituent_peers(frame: pd.DataFrame, *, target_code: str, industry: str, limit: int) -> list[PeerCandidate]:
    if frame.empty:
        return []
    code_col = _find_column(frame, "code", "\u4ee3\u7801", "\u80a1\u7968\u4ee3\u7801")
    name_col = _find_column(frame, "name", "\u540d\u79f0", "\u80a1\u7968\u7b80\u79f0")
    if code_col is None or name_col is None:
        return []
    candidates: list[PeerCandidate] = []
    for row in frame[[code_col, name_col]].dropna().itertuples(index=False):
        peer_code = _digits(row[0])[-6:]
        peer_name = str(row[1]).strip()
        if len(peer_code) != 6 or not peer_name:
            continue
        candidates.append(
            PeerCandidate(
                name=peer_name,
                code=peer_code,
                universe_source="akshare",
                universe_detail=f"AKShare industry constituents: {industry}",
            )
        )
    return _dedupe_candidates(candidates, target_code=target_code, limit=limit)


def _find_column(frame: pd.DataFrame, *candidates: str) -> Any:
    normalized = {str(col).strip().lower(): col for col in frame.columns}
    for candidate in candidates:
        key = str(candidate).strip().lower()
        if key in normalized:
            return normalized[key]
    for col in frame.columns:
        text = str(col).strip().lower()
        if any(str(candidate).strip().lower() in text for candidate in candidates):
            return col
    return None


def _dedupe_candidates(candidates: list[PeerCandidate], *, target_code: str, limit: int) -> list[PeerCandidate]:
    target = _digits(target_code)[-6:]
    seen = {target}
    result: list[PeerCandidate] = []
    for candidate in candidates:
        code = _digits(candidate.code)[-6:]
        if len(code) != 6 or code in seen:
            continue
        seen.add(code)
        result.append(
            PeerCandidate(
                name=candidate.name,
                code=code,
                universe_source=candidate.universe_source,
                universe_detail=candidate.universe_detail,
            )
        )
        if len(result) >= limit:
            break
    return result


def _industry_from_profile(profile: IndustryProfile | None) -> str:
    for field in ("theme", "node"):
        value = str(getattr(profile, field, "") or "").strip()
        if value and "\u5f85" not in value:
            return value
    return ""


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())
