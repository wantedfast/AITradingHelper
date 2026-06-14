import json
import os
import unittest
from unittest.mock import patch

from trade_review_agent.ocr.ai_trade_parser import parse_trade_text_to_intents


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "trades": [
                                    {
                                        "name": "东材科技",
                                        "code": "601208",
                                        "trade_date": "2026-06-09",
                                        "trade_time": "09:25:00",
                                        "side": "buy",
                                        "price": 10.5,
                                        "quantity": 100,
                                        "amount": 1050,
                                        "fee": 0,
                                    }
                                ]
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class TradeOcrDeepSeekTest(unittest.TestCase):
    def test_trade_text_parser_uses_deepseek_config_not_openai(self):
        old_env = dict(os.environ)
        try:
            os.environ.update(
                {
                    "OPENAI_API_KEY": "should-not-be-used",
                    "OPENAI_BASE_URL": "https://api.openai.invalid/v1",
                    "OPENAI_MODEL": "gpt-should-not-be-used",
                    "DEEPSEEK_API_KEY": "ds-key",
                    "DEEPSEEK_BASE_URL": "https://deepseek.example/v1",
                    "TRADE_OCR_MODEL": "deepseek-chat",
                }
            )
            captured = {}

            def fake_urlopen(request, timeout=0):
                captured["url"] = request.full_url
                captured["headers"] = dict(request.header_items())
                captured["body"] = json.loads(request.data.decode("utf-8"))
                captured["timeout"] = timeout
                return _FakeResponse()

            with patch("urllib.request.urlopen", fake_urlopen):
                intents = parse_trade_text_to_intents("2026-06-09 09:25 买入 东材科技 601208 100股 10.5")

            self.assertEqual(intents[0].code, "601208")
            self.assertEqual(captured["url"], "https://deepseek.example/v1/chat/completions")
            self.assertEqual(captured["headers"]["Authorization"], "Bearer ds-key")
            self.assertEqual(captured["body"]["model"], "deepseek-chat")
            self.assertNotIn("gpt-should-not-be-used", json.dumps(captured["body"], ensure_ascii=False))
        finally:
            os.environ.clear()
            os.environ.update(old_env)


if __name__ == "__main__":
    unittest.main()
