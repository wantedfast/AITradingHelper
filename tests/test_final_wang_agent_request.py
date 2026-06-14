import json
import unittest
import urllib.error
from io import BytesIO
from unittest.mock import patch

from trade_review_agent.review.final_wang_agent.agent import FinalWangAgentError, build_search_prompt, call_doubao_search


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return b'{"output_text":"ok"}'


class FinalWangAgentRequestTest(unittest.TestCase):
    def test_search_prompt_uses_trade_day_not_date_window(self):
        prompt = build_search_prompt("东材科技", "601208", "2026-06-09", ["2026-06-09 09:25:00"])

        self.assertIn("你是A股资金逻辑研究员。", prompt)
        self.assertIn("必须先确认：\n\n市场在炒什么", prompt)
        self.assertIn("2026年06月09日 A股市场复盘", prompt)
        self.assertIn("第三步：个股市场表现", prompt)
        self.assertIn("2026年06月09日\n\n东材科技", prompt)
        self.assertIn("原始日期：\n\n2026-06-09", prompt)
        self.assertIn("来源等级", prompt)
        self.assertNotIn("2026年06月07日至06月11日", prompt)

    @patch("trade_review_agent.review.final_wang_agent.agent.urllib.request.urlopen")
    def test_doubao_search_uses_medium_reasoning(self, urlopen):
        urlopen.return_value = _Response()

        with patch.dict("os.environ", {"WANG_DOUBAO_MODEL": "test-doubao-model"}, clear=False):
            call_doubao_search("test-key", "test prompt")

        request = urlopen.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "test-doubao-model")
        self.assertEqual(body["thinking"], {"type": "enabled"})
        self.assertEqual(body["reasoning"], {"effort": "medium"})
        self.assertEqual(body["tools"], [{"type": "web_search"}])

    @patch("trade_review_agent.review.final_wang_agent.agent.urllib.request.urlopen")
    def test_doubao_search_wraps_http_error_body(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.test",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=BytesIO(b'{"error":"no permission"}'),
        )

        with self.assertRaises(FinalWangAgentError) as raised:
            call_doubao_search("test-key", "test prompt")

        self.assertEqual(raised.exception.user_message, "豆包 Research 搜索失败")
        self.assertEqual(raised.exception.status_code, 403)
        self.assertIn("no permission", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
