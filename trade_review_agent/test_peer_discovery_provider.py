from __future__ import annotations

import unittest

import pandas as pd

from .industry_profiles import DEFAULT_PROFILE
from .peer_discovery_provider import PeerDiscoveryProvider
from .peer_snapshot import build_peer_snapshot


class PeerDiscoveryProviderTests(unittest.TestCase):
    def test_discovers_industry_peers_from_akshare_frames(self) -> None:
        provider = PeerDiscoveryProvider(
            individual_info_fetcher=lambda symbol: pd.DataFrame(
                [{"item": "industry", "value": "Electronic materials"}]
            ),
            industry_cons_fetcher=lambda symbol: pd.DataFrame(
                [
                    {"code": "601208", "name": "Target"},
                    {"code": "600563", "name": "Peer A"},
                    {"code": "603260", "name": "Peer B"},
                    {"code": "002409", "name": "Peer C"},
                ]
            ),
        )

        peers = provider.discover(code="601208", name="Target", profile=DEFAULT_PROFILE)

        self.assertEqual(["600563", "603260", "002409"], [item.code for item in peers])
        self.assertTrue(all(item.universe_source == "akshare" for item in peers))

    def test_peer_snapshot_separates_universe_and_quote_lineage(self) -> None:
        snapshot = build_peer_snapshot(
            {
                "trade_facts": {"trades": [{"date": "2026-06-09"}]},
                "market_data": {
                    "peers": [
                        {
                            "code": "600563",
                            "name": "Peer A",
                            "day_pct": 1.5,
                            "source": "tencent_finance",
                            "universe_source": "akshare",
                            "universe_detail": "AKShare industry constituents: Electronic materials",
                        }
                    ]
                },
            }
        )

        self.assertEqual("real_data", snapshot[0]["source_trace"]["code"]["source"])
        self.assertEqual("real_data", snapshot[0]["source_trace"]["metrics"]["source"])
        self.assertEqual("akshare", snapshot[0]["universe_source"])


if __name__ == "__main__":
    unittest.main()
