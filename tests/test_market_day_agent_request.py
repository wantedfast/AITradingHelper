import json
import unittest
from unittest.mock import patch

from trade_review_agent.review.market_day_agent.agent import (
    build_market_day_judge_prompt,
    build_market_day_search_prompt,
    call_doubao_market_search,
)


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return b'{"output_text":"ok"}'


class MarketDayAgentRequestTest(unittest.TestCase):
    def test_search_prompt_targets_today_a_share_mainlines(self):
        prompt = build_market_day_search_prompt("2026-06-19")

        self.assertIn("A股全市场当日行情复盘资料搜索员", prompt)
        self.assertIn("2026年06月19日 A股市场复盘", prompt)
        self.assertIn("当天行情主线", prompt)
        self.assertIn("涨停潮", prompt)
        self.assertIn("连板梯队", prompt)
        self.assertIn("只输出搜索证据包", prompt)
        self.assertNotIn("买入日期", prompt)

    def test_judge_prompt_requires_strict_market_day_json(self):
        prompt = build_market_day_judge_prompt("2026-06-19", "搜索资料包")

        self.assertIn("只基于资料包判断", prompt)
        self.assertIn("当日最强主线", prompt)
        self.assertIn("主线内最强势个股", prompt)
        self.assertIn('"marketDate"', prompt)
        self.assertIn('"strongestStocks"', prompt)
        self.assertIn('"leaderType"', prompt)
        self.assertIn("不要输出投资建议", prompt)
        self.assertIn("搜索资料包", prompt)

    @patch("trade_review_agent.review.market_day_agent.agent.urllib.request.urlopen")
    def test_doubao_market_search_uses_web_search_and_medium_reasoning(self, urlopen):
        urlopen.return_value = _Response()

        with patch.dict("os.environ", {"MARKET_DAY_DOUBAO_MODEL": "market-day-doubao"}, clear=False):
            call_doubao_market_search("test-key", "test prompt")

        request = urlopen.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "market-day-doubao")
        self.assertEqual(body["tools"], [{"type": "web_search"}])
        self.assertEqual(body["thinking"], {"type": "enabled"})
        self.assertEqual(body["reasoning"], {"effort": "medium"})


if __name__ == "__main__":
    unittest.main()
