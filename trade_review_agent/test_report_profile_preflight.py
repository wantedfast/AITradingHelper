from __future__ import annotations

import inspect
import unittest

from . import visual_report


class ReportProfilePreflightTests(unittest.TestCase):
    def test_report_entrypoints_do_not_trigger_ai_profile_preflight(self) -> None:
        for function in (
            visual_report.build_round_html,
            visual_report.build_single_stock_html,
        ):
            source = inspect.getsource(function)
            self.assertNotIn("get_profile(", source)
            self.assertIn("_base_report_profile(", source)


if __name__ == "__main__":
    unittest.main()
