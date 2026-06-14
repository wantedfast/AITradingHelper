import json
import unittest
from unittest.mock import patch

from trade_review_agent.review.final_wang_agent.agent import call_doubao_search


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return b'{"output_text":"ok"}'


class FinalWangAgentRequestTest(unittest.TestCase):
    @patch("trade_review_agent.review.final_wang_agent.agent.urllib.request.urlopen")
    def test_doubao_search_uses_medium_reasoning(self, urlopen):
        urlopen.return_value = _Response()

        call_doubao_search("test-key", "test prompt")

        request = urlopen.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["thinking"], {"type": "enabled"})
        self.assertEqual(body["reasoning"], {"effort": "medium"})
        self.assertEqual(body["tools"], [{"type": "web_search"}])


if __name__ == "__main__":
    unittest.main()
