from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from . import industry_agent


class IndustryAgentPerformanceTests(unittest.TestCase):
    def test_cache_hit_does_not_build_context_or_call_market_catalyst(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            original_cache = industry_agent.CACHE_PATH
            original_build_context = industry_agent.build_stock_context
            try:
                industry_agent.CACHE_PATH = Path(tmp) / "cache.json"
                cached = {"company": {"code": "600000", "name": "Test"}}
                key = f"{industry_agent.PROFILE_CACHE_VERSION}:600000:Test:tier:standard"
                industry_agent.CACHE_PATH.write_text(
                    json.dumps({key: cached}, ensure_ascii=False),
                    encoding="utf-8",
                )

                def fail_context(**_: object) -> dict[str, object]:
                    raise AssertionError("context should not be built on cache hit")

                industry_agent.build_stock_context = fail_context
                result = industry_agent.get_workbench_profile_data("600000", "Test")

                self.assertEqual(cached, result)
            finally:
                industry_agent.CACHE_PATH = original_cache
                industry_agent.build_stock_context = original_build_context

    def test_better_retry_only_reruns_failed_research_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            original_cache = industry_agent.CACHE_PATH
            original_build_context = industry_agent.build_stock_context
            original_wang = industry_agent._run_wang_research_agent
            original_public = industry_agent._run_public_equity_research_agent
            original_refresh = os.environ.get("WORKBENCH_AGENT_REFRESH")
            calls = {"wang": [], "public": []}
            try:
                os.environ["WORKBENCH_AGENT_REFRESH"] = "1"
                industry_agent.CACHE_PATH = Path(tmp) / "cache.json"
                industry_agent.build_stock_context = lambda **_: {
                    "company": {"code": "600000", "name": "Test"},
                    "trade": {},
                    "market": {},
                }

                def wang(context: dict[str, object], tier: str):
                    calls["wang"].append(tier)
                    return {"industry_rating": "A"}, []

                def public(context: dict[str, object], tier: str):
                    calls["public"].append(tier)
                    if tier == "better":
                        return {}, ["Public failed"]
                    return {"investment_rating": "B"}, []

                industry_agent._run_wang_research_agent = wang
                industry_agent._run_public_equity_research_agent = public

                result = industry_agent.get_workbench_profile_data(
                    "600000",
                    "Test",
                    research_model_tier="better",
                )

                self.assertEqual(["better"], calls["wang"])
                self.assertEqual(["better", "standard"], calls["public"])
                self.assertEqual("A", result["wang_agent"]["industry_rating"])
                self.assertEqual("B", result["public_equity_agent"]["investment_rating"])
            finally:
                if original_refresh is None:
                    os.environ.pop("WORKBENCH_AGENT_REFRESH", None)
                else:
                    os.environ["WORKBENCH_AGENT_REFRESH"] = original_refresh
                industry_agent.CACHE_PATH = original_cache
                industry_agent.build_stock_context = original_build_context
                industry_agent._run_wang_research_agent = original_wang
                industry_agent._run_public_equity_research_agent = original_public


if __name__ == "__main__":
    unittest.main()
