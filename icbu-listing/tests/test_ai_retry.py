"""AiClient retries transient provider failures up to five times."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from ai import AiClient, AiUnavailable, MAX_AI_ATTEMPTS  # noqa: E402


class AiRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = AiClient(
            api_key="test-key",
            base_url="https://example.com/v1",
            text_model="gpt-test",
            timeout=5.0,
        )

    @patch("ai.time.sleep")
    @patch("ai.requests.post")
    def test_chat_retries_transient_http_errors(self, post: MagicMock, sleep: MagicMock) -> None:
        bad = MagicMock(status_code=503, text="busy")
        good = MagicMock(status_code=200)
        good.json.return_value = {"choices": [{"message": {"content": "hello"}}]}
        post.side_effect = [bad, bad, good]

        text = self.client.chat([{"role": "user", "content": "hi"}])

        self.assertEqual(text, "hello")
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @patch("ai.time.sleep")
    @patch("ai.requests.post")
    def test_chat_gives_up_after_max_attempts(self, post: MagicMock, sleep: MagicMock) -> None:
        bad = MagicMock(status_code=503, text="busy")
        post.return_value = bad

        with self.assertRaises(AiUnavailable):
            self.client.chat([{"role": "user", "content": "hi"}])

        self.assertEqual(post.call_count, MAX_AI_ATTEMPTS)
        self.assertEqual(sleep.call_count, MAX_AI_ATTEMPTS - 1)

    @patch("ai.time.sleep")
    @patch("ai.requests.post")
    def test_chat_does_not_retry_client_errors(self, post: MagicMock, sleep: MagicMock) -> None:
        bad = MagicMock(status_code=400, text="bad request")
        post.return_value = bad

        with self.assertRaises(AiUnavailable):
            self.client.chat([{"role": "user", "content": "hi"}])

        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    @patch("ai.time.sleep")
    @patch("ai.AiClient._chat_json_once")
    def test_chat_json_retries_invalid_json(self, once: MagicMock, sleep: MagicMock) -> None:
        once.side_effect = [ValueError("bad json"), {"ok": True}]

        payload = self.client.chat_json([{"role": "user", "content": "return json"}])

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(once.call_count, 2)
        sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
