import unittest
from datetime import datetime

from trade_review_agent.auction_strength.top1_performance import auction_top1_next_refresh_at


class AuctionTop1RefreshClockTest(unittest.TestCase):
    def test_next_refresh_uses_today_at_1600_before_cutoff(self):
        now = datetime.fromisoformat("2026-06-30T15:59:00+08:00")

        next_run = auction_top1_next_refresh_at(now)

        self.assertEqual(next_run.isoformat(), "2026-06-30T16:00:00+08:00")

    def test_next_refresh_uses_tomorrow_at_1600_after_cutoff(self):
        now = datetime.fromisoformat("2026-06-30T16:00:01+08:00")

        next_run = auction_top1_next_refresh_at(now)

        self.assertEqual(next_run.isoformat(), "2026-07-01T16:00:00+08:00")


if __name__ == "__main__":
    unittest.main()
