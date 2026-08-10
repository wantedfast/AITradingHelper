from __future__ import annotations

import unittest
from unittest import mock

from trade_review_agent.api import simple_api


class UpdateEmailWorkerConfigTest(unittest.TestCase):
    def test_worker_count_defaults_to_existing_parallelism(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                simple_api._configured_update_email_worker_count(),
                simple_api.UPDATE_EMAIL_WORKER_COUNT,
            )

    def test_worker_count_can_be_reduced_for_smtp_connection_limits(self) -> None:
        with mock.patch.dict("os.environ", {"UPDATE_EMAIL_WORKER_COUNT": "1"}, clear=False):
            self.assertEqual(simple_api._configured_update_email_worker_count(), 1)

    def test_worker_count_rejects_invalid_and_clamps_extremes(self) -> None:
        for value, expected in (("invalid", 4), ("0", 1), ("99", 16)):
            with self.subTest(value=value), mock.patch.dict(
                "os.environ", {"UPDATE_EMAIL_WORKER_COUNT": value}, clear=False
            ):
                self.assertEqual(simple_api._configured_update_email_worker_count(), expected)


if __name__ == "__main__":
    unittest.main()
