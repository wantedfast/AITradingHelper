from __future__ import annotations

import unittest

from trade_review_agent.api.simple_api import normalize_research_model_tier


class ReportModeDisabledTest(unittest.TestCase):
    def test_all_report_tier_requests_use_standard_mode(self) -> None:
        for requested_tier in (None, "", "standard", "better", "premium", "gpt-5.5", True):
            with self.subTest(requested_tier=requested_tier):
                self.assertEqual(normalize_research_model_tier(requested_tier), "standard")


if __name__ == "__main__":
    unittest.main()
