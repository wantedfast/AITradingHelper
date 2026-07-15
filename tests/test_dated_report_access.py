from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import unittest
from contextlib import ExitStack, closing
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from unittest.mock import patch

from trade_review_agent.api import simple_api
from trade_review_agent.auth_system import init_auth_db


class DatedReportAccessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "auth.sqlite"
        self.market_root = self.root / "market-day"
        self.research_root = self.root / "ai-research"
        self.market_root.mkdir()
        self.research_root.mkdir()
        init_auth_db(self.db_path)
        self.user_id = self._create_user_with_session_and_credits(20)

        self.stack = ExitStack()
        self.stack.enter_context(patch.object(simple_api, "AUTH_DB", self.db_path))
        self.stack.enter_context(patch.object(simple_api, "MARKET_DAY_REPORT_DIR", self.market_root))
        self.stack.enter_context(patch.object(simple_api, "AI_RESEARCH_REPORT_DIR", self.research_root))

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), simple_api.TradeReviewHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.stack.close()
        self.temp_dir.cleanup()

    def _create_user_with_session_and_credits(self, credits: int) -> int:
        now = "2026-07-14T10:00:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                user_id = int(
                    conn.execute(
                        """
                        INSERT INTO users (
                            phone, username, email, email_verified, password_hash,
                            password_salt, role, status, invite_code, created_at
                        ) VALUES (?, ?, ?, 1, 'hash', 'salt', 'user', 'active', ?, ?)
                        """,
                        ("dated@example.com", "dateduser", "dated@example.com", "DATED001", now),
                    ).lastrowid
                )
                conn.execute(
                    "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES ('dated-token', ?, ?, ?)",
                    (user_id, "2999-01-01T00:00:00+08:00", now),
                )
                conn.execute(
                    "INSERT INTO credit_ledger (user_id, delta, reason, related_id, created_at) VALUES (?, ?, 'test', NULL, ?)",
                    (user_id, credits, now),
                )
        return user_id

    def _request(self, path: str, *, method: str = "GET", authenticated: bool = True) -> tuple[int, object, dict[str, str]]:
        headers = {"Authorization": "Bearer dated-token"} if authenticated else {}
        request = Request(self.base_url + path, headers=headers, method=method)
        try:
            with urlopen(request, timeout=3) as response:
                raw = response.read()
                return response.status, self._decode_body(raw, response.headers.get("Content-Type", "")), dict(response.headers)
        except HTTPError as exc:
            with exc:
                raw = exc.read()
                return exc.code, self._decode_body(raw, exc.headers.get("Content-Type", "")), dict(exc.headers)

    @staticmethod
    def _decode_body(raw: bytes, content_type: str) -> object:
        if "application/json" in content_type:
            return json.loads(raw.decode("utf-8"))
        return raw

    def _write_market_report(self, run_id: str, report_date: str, *, order: int) -> Path:
        run_dir = self.market_root / run_id
        run_dir.mkdir()
        payload = {
            "run_id": run_id,
            "market_date": report_date,
            "report": {
                "marketDate": report_date,
                "oneLineConclusion": f"market-{order}",
                "mainline": {"name": f"line-{order}"},
            },
        }
        (run_dir / simple_api.MARKET_DAY_REPORT_NAME).write_text(json.dumps(payload), encoding="utf-8")
        (run_dir / simple_api.REPORT_STATUS_NAME).write_text(
            json.dumps({"run_id": run_id, "status": "done", "market_date": report_date, "ownerless": True}),
            encoding="utf-8",
        )
        stamp = 1_700_000_000 + order
        os.utime(run_dir, (stamp, stamp))
        return run_dir

    def _write_research_report(self, run_id: str, report_date: str, *, order: int) -> Path:
        run_dir = self.research_root / run_id
        run_dir.mkdir()
        payload = {
            "run_id": run_id,
            "research_date": report_date,
            "received_at": f"{report_date} 08:{order % 60:02d}:00",
            "title": f"research-{order}",
            "summary": f"summary-{order}",
        }
        (run_dir / simple_api.AI_RESEARCH_REPORT_NAME).write_text(json.dumps(payload), encoding="utf-8")
        (run_dir / simple_api.REPORT_STATUS_NAME).write_text(
            json.dumps({"run_id": run_id, "status": "done", "research_date": report_date, "ownerless": True}),
            encoding="utf-8",
        )
        stamp = 1_700_000_000 + order
        os.utime(run_dir, (stamp, stamp))
        return run_dir

    def _balance_and_usage(self, feature: str) -> tuple[int, list[tuple[int, str]]]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            balance = int(
                conn.execute(
                    "SELECT COALESCE(SUM(delta), 0) FROM credit_ledger WHERE user_id = ?",
                    (self.user_id,),
                ).fetchone()[0]
            )
            usage = conn.execute(
                "SELECT credits_spent, related_id FROM usage_events WHERE user_id = ? AND feature = ? ORDER BY id",
                (self.user_id, feature),
            ).fetchall()
        return balance, [(int(row[0]), str(row[1])) for row in usage]

    def test_lists_filter_by_date_validate_date_and_return_one_latest_report(self) -> None:
        today = datetime.now(simple_api.CN_TZ).date()
        old_date = (today - timedelta(days=2)).isoformat()
        self._write_market_report("market-old", old_date, order=1)
        self._write_market_report("market-new", old_date, order=2)
        self._write_research_report("research-old", old_date, order=1)
        self._write_research_report("research-new", old_date, order=2)

        for endpoint, expected_run in (
            ("/api/market-day/reports", "market-new"),
            ("/api/ai-research/reports", "research-new"),
        ):
            with self.subTest(endpoint=endpoint):
                status, payload, _ = self._request(f"{endpoint}?{urlencode({'date': old_date})}")
                self.assertEqual(status, 200)
                self.assertIsInstance(payload, dict)
                self.assertEqual(payload["selected_date"], old_date)
                self.assertLessEqual(len(payload["available_dates"]), 5)
                self.assertEqual(payload["reports"][0]["run_id"], expected_run)
                self.assertLessEqual(len(payload["reports"]), 1)
                self.assertIn("billing_status", payload)

                bad_status, _, _ = self._request(f"{endpoint}?date=2026%2F07%2F14")
                self.assertEqual(bad_status, 400)

    def test_retention_keeps_five_dates_and_latest_per_day_and_deletes_old_directories(self) -> None:
        today = datetime.now(simple_api.CN_TZ).date()
        expected_dates = [(today - timedelta(days=offset)).isoformat() for offset in range(5)]
        deleted_date = (today - timedelta(days=5)).isoformat()

        for offset in range(6):
            report_date = (today - timedelta(days=offset)).isoformat()
            self._write_market_report(f"market-{offset}-old", report_date, order=offset * 10)
            self._write_market_report(f"market-{offset}-new", report_date, order=offset * 10 + 1)
            self._write_research_report(f"research-{offset}-old", report_date, order=offset * 10)
            self._write_research_report(f"research-{offset}-new", report_date, order=offset * 10 + 1)

        for endpoint, root, prefix, filename in (
            ("/api/market-day/reports", self.market_root, "market", simple_api.MARKET_DAY_REPORT_NAME),
            ("/api/ai-research/reports", self.research_root, "research", simple_api.AI_RESEARCH_REPORT_NAME),
        ):
            with self.subTest(endpoint=endpoint):
                if endpoint == "/api/market-day/reports":
                    simple_api._prune_market_day_reports()
                else:
                    simple_api._prune_ai_research_reports()
                status, payload, _ = self._request(endpoint)
                self.assertEqual(status, 200)
                self.assertEqual(payload["available_dates"], expected_dates)
                self.assertEqual(len([path for path in root.iterdir() if path.is_dir()]), 5)
                for offset in range(5):
                    self.assertFalse((root / f"{prefix}-{offset}-old").exists())
                    self.assertTrue((root / f"{prefix}-{offset}-new").exists())
                self.assertFalse((root / f"{prefix}-5-old").exists())
                self.assertFalse((root / f"{prefix}-5-new").exists())

                deleted_run = f"{prefix}-5-new"
                direct_status, _, _ = self._request(f"{endpoint}/{deleted_run}/{filename}")
                status_status, _, _ = self._request(f"{endpoint}/{deleted_run}/status")
                self.assertEqual(direct_status, 404)
                self.assertEqual(status_status, 404)
                self.assertNotIn(deleted_date, payload["available_dates"])

    def test_historical_ack_status_and_file_are_free_without_usage_event(self) -> None:
        old_date = (datetime.now(simple_api.CN_TZ).date() - timedelta(days=1)).isoformat()
        market_run = "market-history"
        research_run = "research-history"
        self._write_market_report(market_run, old_date, order=1)
        self._write_research_report(research_run, old_date, order=1)

        for endpoint, run_id, filename, feature in (
            ("/api/market-day/reports", market_run, simple_api.MARKET_DAY_REPORT_NAME, "market_day_report"),
            ("/api/ai-research/reports", research_run, simple_api.AI_RESEARCH_REPORT_NAME, "ai_research_view"),
        ):
            with self.subTest(endpoint=endpoint):
                ack_status, ack, _ = self._request(f"{endpoint}/{run_id}/ack", method="POST")
                status_status, status_payload, _ = self._request(f"{endpoint}/{run_id}/status")
                file_status, file_payload, _ = self._request(f"{endpoint}/{run_id}/{filename}")
                self.assertEqual(ack_status, 200)
                self.assertEqual(ack["billing_status"], "free_history")
                self.assertEqual(status_status, 200)
                self.assertIsInstance(status_payload, dict)
                self.assertEqual(file_status, 200)
                self.assertIsInstance(file_payload, (dict, bytes))
                balance, usage = self._balance_and_usage(feature)
                self.assertEqual(balance, 20)
                self.assertEqual(usage, [])

    def test_current_reports_require_ack_then_charge_configured_cost_once(self) -> None:
        today = datetime.now(simple_api.CN_TZ).date().isoformat()
        market_run = "market-today"
        research_run = "research-today"
        self._write_market_report(market_run, today, order=1)
        self._write_research_report(research_run, today, order=1)

        expected_balance = 20
        for endpoint, run_id, filename, feature, cost in (
            ("/api/market-day/reports", market_run, simple_api.MARKET_DAY_REPORT_NAME, "market_day_report", 1),
            ("/api/ai-research/reports", research_run, simple_api.AI_RESEARCH_REPORT_NAME, "ai_research_view", 2),
        ):
            with self.subTest(endpoint=endpoint):
                before_status, _, _ = self._request(f"{endpoint}/{run_id}/status")
                before_file, _, _ = self._request(f"{endpoint}/{run_id}/{filename}")
                self.assertEqual(before_status, 402)
                self.assertEqual(before_file, 402)

                first_status, first_payload, _ = self._request(f"{endpoint}/{run_id}/ack", method="POST")
                second_status, second_payload, _ = self._request(f"{endpoint}/{run_id}/ack", method="POST")
                self.assertEqual(first_status, 200)
                self.assertEqual(second_status, 200)
                self.assertEqual(first_payload["billing_status"], "charged")
                self.assertEqual(second_payload["billing_status"], "charged")

                expected_balance -= cost
                balance, usage = self._balance_and_usage(feature)
                self.assertEqual(balance, expected_balance)
                self.assertEqual(usage, [(cost, run_id)])

                after_status, _, _ = self._request(f"{endpoint}/{run_id}/status")
                after_file, _, _ = self._request(f"{endpoint}/{run_id}/{filename}")
                self.assertEqual(after_status, 200)
                self.assertEqual(after_file, 200)

    def test_list_states_support_automatic_history_and_paid_access_but_new_run_requires_payment(self) -> None:
        today = datetime.now(simple_api.CN_TZ).date().isoformat()
        old_date = (datetime.now(simple_api.CN_TZ).date() - timedelta(days=1)).isoformat()
        cases = (
            (
                "/api/market-day/reports",
                "market_day_report",
                1,
                self._write_market_report,
                "market",
            ),
            (
                "/api/ai-research/reports",
                "ai_research_view",
                2,
                self._write_research_report,
                "research",
            ),
        )
        expected_balance = 20

        for endpoint, feature, cost, writer, prefix in cases:
            with self.subTest(endpoint=endpoint):
                empty_status, empty, _ = self._request(f"{endpoint}?{urlencode({'date': today})}")
                self.assertEqual(empty_status, 200)
                self.assertEqual(empty["billing_status"], "no_data")
                self.assertEqual(empty["billing_cost"], 0)
                self.assertEqual(empty["reports"], [])

                history_run = f"{prefix}-automatic-history"
                writer(history_run, old_date, order=10)
                history_status, history, _ = self._request(f"{endpoint}?{urlencode({'date': old_date})}")
                self.assertEqual(history_status, 200)
                self.assertEqual(history["billing_status"], "free_history")
                self.assertEqual(history["billing_cost"], 0)
                self.assertEqual(history["reports"][0]["run_id"], history_run)

                first_run = f"{prefix}-automatic-current"
                writer(first_run, today, order=20)
                pending_status, pending, _ = self._request(f"{endpoint}?{urlencode({'date': today})}")
                self.assertEqual(pending_status, 200)
                self.assertEqual(pending["billing_status"], "pending_view")
                self.assertEqual(pending["billing_cost"], cost)
                self.assertEqual(self._balance_and_usage(feature), (expected_balance, []))

                ack_status, _, _ = self._request(f"{endpoint}/{first_run}/ack", method="POST")
                charged_status, charged, _ = self._request(f"{endpoint}?{urlencode({'date': today})}")
                self.assertEqual(ack_status, 200)
                self.assertEqual(charged_status, 200)
                self.assertEqual(charged["billing_status"], "charged")
                self.assertEqual(charged["billing_cost"], 0)
                expected_balance -= cost
                self.assertEqual(self._balance_and_usage(feature), (expected_balance, [(cost, first_run)]))

                replacement_run = f"{prefix}-automatic-replacement"
                writer(replacement_run, today, order=30)
                replacement_status, replacement, _ = self._request(f"{endpoint}?{urlencode({'date': today})}")
                self.assertEqual(replacement_status, 200)
                self.assertEqual(replacement["reports"][0]["run_id"], replacement_run)
                self.assertEqual(replacement["billing_status"], "pending_view")
                self.assertEqual(replacement["billing_cost"], cost)
                self.assertEqual(self._balance_and_usage(feature), (expected_balance, [(cost, first_run)]))

    def test_ai_research_cost_two_rejects_one_credit_without_partial_charge(self) -> None:
        today = datetime.now(simple_api.CN_TZ).date().isoformat()
        run_id = "research-insufficient"
        self._write_research_report(run_id, today, order=1)
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO credit_ledger (user_id, delta, reason, related_id, created_at) VALUES (?, -19, 'test_adjustment', NULL, ?)",
                    (self.user_id, "2026-07-14T10:01:00+08:00"),
                )

        ack_status, _, _ = self._request(f"/api/ai-research/reports/{run_id}/ack", method="POST")

        self.assertEqual(ack_status, 402)
        with closing(sqlite3.connect(self.db_path)) as conn:
            balance = int(
                conn.execute(
                    "SELECT COALESCE(SUM(delta), 0) FROM credit_ledger WHERE user_id = ?",
                    (self.user_id,),
                ).fetchone()[0]
            )
            charged = int(
                conn.execute(
                    "SELECT COUNT(*) FROM usage_events WHERE user_id = ? AND feature = 'ai_research_view' AND status = 'charged'",
                    (self.user_id,),
                ).fetchone()[0]
            )
        self.assertEqual(balance, 1)
        self.assertEqual(charged, 0)

    def test_concurrent_ack_charges_each_current_report_only_once(self) -> None:
        today = datetime.now(simple_api.CN_TZ).date().isoformat()
        cases = (
            ("/api/market-day/reports", "market-concurrent", "market_day_report", 1, self._write_market_report),
            ("/api/ai-research/reports", "research-concurrent", "ai_research_view", 2, self._write_research_report),
        )
        expected_balance = 20
        for endpoint, run_id, feature, cost, writer in cases:
            with self.subTest(endpoint=endpoint):
                writer(run_id, today, order=1)
                barrier = threading.Barrier(3)
                results: list[tuple[int, object, dict[str, str]]] = []

                def acknowledge() -> None:
                    barrier.wait()
                    results.append(self._request(f"{endpoint}/{run_id}/ack", method="POST"))

                threads = [threading.Thread(target=acknowledge) for _ in range(2)]
                for thread in threads:
                    thread.start()
                barrier.wait()
                for thread in threads:
                    thread.join(timeout=5)

                self.assertTrue(all(not thread.is_alive() for thread in threads))
                self.assertEqual([status for status, _, _ in results], [200, 200])
                expected_balance -= cost
                balance, usage = self._balance_and_usage(feature)
                self.assertEqual(balance, expected_balance)
                self.assertEqual(usage, [(cost, run_id)])

    def test_list_ack_status_and_file_require_authentication(self) -> None:
        today = datetime.now(simple_api.CN_TZ).date().isoformat()
        self._write_market_report("market-auth", today, order=1)
        self._write_research_report("research-auth", today, order=1)

        for endpoint, run_id, filename in (
            ("/api/market-day/reports", "market-auth", simple_api.MARKET_DAY_REPORT_NAME),
            ("/api/ai-research/reports", "research-auth", simple_api.AI_RESEARCH_REPORT_NAME),
        ):
            with self.subTest(endpoint=endpoint):
                for path, method in (
                    (endpoint, "GET"),
                    (f"{endpoint}/{run_id}/ack", "POST"),
                    (f"{endpoint}/{run_id}/status", "GET"),
                    (f"{endpoint}/{run_id}/{filename}", "GET"),
                ):
                    status, _, _ = self._request(path, method=method, authenticated=False)
                    self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
