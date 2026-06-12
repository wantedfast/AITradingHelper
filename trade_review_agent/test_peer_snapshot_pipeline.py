from __future__ import annotations

import unittest

from .peer_snapshot import build_peer_snapshot
from .v3_better_opportunity_agent import run_better_opportunity_agent
from .v3_market_scout import run_market_scout


class PeerSnapshotPipelineTests(unittest.TestCase):
    def test_cached_peer_quotes_remain_fallback(self) -> None:
        snapshot = build_peer_snapshot(
            {
                "trade_facts": {"trades": [{"date": "2026-06-01"}]},
                "market_data": {
                    "peers": [
                        {
                            "code": "600001",
                            "name": "Cached Peer",
                            "source": "fallback_existing",
                            "day_pct": 1.2,
                        }
                    ]
                },
            }
        )

        self.assertEqual(1, len(snapshot))
        self.assertEqual(
            "fallback",
            snapshot[0]["source_trace"]["metrics"]["source"],
        )

    def test_real_peer_metrics_reach_better_opportunity(self) -> None:
        snapshot = build_peer_snapshot(
            {
                "trade_facts": {
                    "trades": [{"side": "buy", "date": "2026-05-11"}],
                },
                "market_data": {
                    "peers": [
                        {
                            "code": "600001",
                            "name": "Peer One",
                            "day_pct": 2.5,
                            "five_day_pct": 8.25,
                            "twenty_day_pct": 13.4,
                            "source": "tencent_finance",
                        }
                    ]
                },
            }
        )

        self.assertEqual(
            {
                "return_1d_pct": 2.5,
                "return_5d_pct": 8.25,
                "return_20d_pct": 13.4,
            },
            snapshot[0]["metrics"],
        )
        self.assertEqual("2026-05-11", snapshot[0]["as_of"])
        self.assertEqual("real_data", snapshot[0]["source_trace"]["metrics"]["source"])

        market_scout = run_market_scout(
            {"market_theme": "verified sector", "peer_snapshot": snapshot}
        )
        calls: list[tuple[str, str]] = []

        def llm_caller(system_prompt: str, user_prompt: str) -> dict:
            calls.append((system_prompt, user_prompt))
            return {
                "better_candidates": [
                    {
                        "code": "600001",
                        "name": "Peer One",
                        "superiority_reason": "Higher verified trailing returns",
                        "evidence": ["return_20d_pct=13.4"],
                    }
                ],
                "superiority_reason": "Peer has stronger supplied quote metrics",
                "confidence": 0.7,
                "replacement_thesis": "Compare execution against the verified peer",
            }

        result = run_better_opportunity_agent(
            company={"code": "600000", "name": "Target"},
            market_scout=market_scout,
            wang={"industry_position": "same verified sector"},
            public_equity={},
            llm_caller=llm_caller,
        )

        self.assertEqual("available", result["status"])
        self.assertEqual("600001", result["better_candidates"][0]["code"])
        self.assertEqual(1, len(calls))

    def test_missing_or_unverified_peer_data_stays_missing(self) -> None:
        snapshot = build_peer_snapshot(
            {
                "trade_facts": {"trades": [{"date": "2026-05-11"}]},
                "market_data": {
                    "peers": [
                        {
                            "code": "600001",
                            "name": "Unverified Peer",
                            "day_pct": 3.0,
                            "source": "missing",
                        },
                        {
                            "code": "600002",
                            "name": "No Metrics",
                            "source": "akshare",
                        },
                    ]
                },
            }
        )
        self.assertEqual([], snapshot)

        market_scout = run_market_scout(
            {"market_theme": "verified sector", "peer_snapshot": snapshot}
        )
        called = False

        def llm_caller(_system_prompt: str, _user_prompt: str) -> dict:
            nonlocal called
            called = True
            return {}

        result = run_better_opportunity_agent(
            company={"code": "600000", "name": "Target"},
            market_scout=market_scout,
            wang={"industry_position": "same sector"},
            public_equity={},
            llm_caller=llm_caller,
        )

        self.assertEqual("missing", result["status"])
        self.assertIn("peer_snapshot", result["missing_reason"])
        self.assertFalse(called)


if __name__ == "__main__":
    unittest.main()
