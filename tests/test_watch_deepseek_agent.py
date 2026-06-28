import json
import os
import unittest
from unittest.mock import patch

from trade_review_agent.common.openai_agent_api import run_deepseek_json_agent


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(
            {
                "id": "chatcmpl-watch-test",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({"watch_date": "2026-06-19", "action": "observe"})
                        }
                    }
                ],
            }
        ).encode("utf-8")


class WatchDeepSeekAgentTest(unittest.TestCase):
    def test_run_deepseek_json_agent_uses_deepseek_chat_completion(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return _FakeResponse()

        env = {
            "DEEPSEEK_API_KEY": "test-ds-key",
            "DEEPSEEK_BASE_URL": "https://deepseek.example/v1",
            "WATCH_DEEPSEEK_MODEL": "deepseek-watch-test",
        }
        with patch.dict(os.environ, env, clear=False), patch("urllib.request.urlopen", fake_urlopen):
            parsed, response_id = run_deepseek_json_agent(
                system_prompt="Return JSON only.",
                user_payload={"stock": "平安银行"},
                max_output_tokens=600,
            )

        self.assertEqual(parsed["action"], "observe")
        self.assertEqual(response_id, "chatcmpl-watch-test")
        self.assertEqual(captured["url"], "https://deepseek.example/v1/chat/completions")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer test-ds-key")
        self.assertEqual(captured["body"]["model"], "deepseek-watch-test")
        self.assertEqual(captured["body"]["response_format"], {"type": "json_object"})

    def test_run_deepseek_json_agent_does_not_fall_back_to_wang_judge_model(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _FakeResponse()

        env = {
            "DEEPSEEK_API_KEY": "test-ds-key",
            "DEEPSEEK_MODEL": "deepseek-chat",
            "WANG_JUDGE_MODEL": "deepseek-v4-pro",
        }
        with patch.dict(os.environ, env, clear=False), patch("urllib.request.urlopen", fake_urlopen):
            run_deepseek_json_agent(
                system_prompt="Return JSON only.",
                user_payload={"stock": "冰轮环境"},
                max_output_tokens=600,
            )

        self.assertEqual(captured["body"]["model"], "deepseek-chat")


if __name__ == "__main__":
    unittest.main()
