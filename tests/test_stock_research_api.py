from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack, closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from trade_review_agent.api import simple_api
from trade_review_agent.auth_system import init_auth_db
from trade_review_agent.stock_research import init_schema
from tests.test_stock_research import FakeProvider


class StockResearchApiE2ETest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Path(self.temp.name) / "auth.sqlite"
        init_auth_db(self.db)
        init_schema(self.db)
        now = "2026-08-23T10:00:00+08:00"
        with closing(sqlite3.connect(self.db)) as conn, conn:
            self.user_id = int(conn.execute(
                """INSERT INTO users(phone,username,email,email_verified,password_hash,password_salt,role,status,invite_code,created_at)
                   VALUES('api@example.com','apiuser','api@example.com',1,'x','y','user','active','APIUSER1',?)""", (now,)
            ).lastrowid)
            admin_id = int(conn.execute(
                """INSERT INTO users(phone,username,email,email_verified,password_hash,password_salt,role,status,invite_code,created_at)
                   VALUES('admin-api','apiadmin','admin-api@example.com',1,'x','y','admin','active','APIADMIN',?)""", (now,)
            ).lastrowid)
            self.second_user_id = int(conn.execute(
                """INSERT INTO users(phone,username,email,email_verified,password_hash,password_salt,role,status,invite_code,created_at)
                   VALUES('api2@example.com','apiuser2','api2@example.com',1,'x','y','user','active','APIUSER2',?)""", (now,)
            ).lastrowid)
            conn.execute("INSERT INTO credit_ledger(user_id,delta,reason,created_at) VALUES(?,5,'test',?)", (self.user_id, now))
            conn.execute("INSERT INTO credit_ledger(user_id,delta,reason,created_at) VALUES(?,5,'test',?)", (self.second_user_id, now))
            conn.execute("INSERT INTO sessions(token,user_id,expires_at,created_at) VALUES('user-token',?,'2999-01-01T00:00:00+08:00',?)", (self.user_id, now))
            conn.execute("INSERT INTO sessions(token,user_id,expires_at,created_at) VALUES('second-token',?,'2999-01-01T00:00:00+08:00',?)", (self.second_user_id, now))
            conn.execute("INSERT INTO sessions(token,user_id,expires_at,created_at) VALUES('admin-token',?,'2999-01-01T00:00:00+08:00',?)", (admin_id, now))
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(simple_api, "AUTH_DB", self.db))
        self.stack.enter_context(patch("trade_review_agent.stock_research.build_provider", side_effect=lambda _: FakeProvider()))
        self.stack.enter_context(patch.dict("os.environ", {
            "STOCK_RESEARCH_ACCESS": "all",
            "STOCK_RESEARCH_PROVIDER": "luna",
            "OPENAI_API_KEY": "test-key",
        }))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), simple_api.TradeReviewHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        self.stack.close(); self.temp.cleanup()

    def request(self, path, *, method="GET", token="user-token", payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Authorization": f"Bearer {token}"}
        if data: headers["Content-Type"] = "application/json"
        req = Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_create_progress_report_history_and_admin_visibility(self):
        status, payload = self.request("/api/stock-research/jobs", method="POST", payload={"type": "stock", "value": "华正新材"})
        self.assertEqual(status, 202)
        job_id = payload["job"]["id"]
        completed = None
        for _ in range(30):
            status, current = self.request(f"/api/stock-research/jobs/{job_id}/status")
            self.assertEqual(status, 200)
            if current["job"]["status"] == "completed":
                completed = current["job"]
                break
            time.sleep(0.05)
        self.assertIsNotNone(completed)
        status, report_payload = self.request(f"/api/stock-research/reports/{completed['report_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(report_payload["report"]["report"]["subject"]["code"], "603186")
        status, second_cached = self.request(
            "/api/stock-research/jobs", method="POST", token="second-token",
            payload={"type": "stock", "value": "603186"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(second_cached["reused"])
        self.assertTrue(second_cached["charged"])
        self.assertEqual(second_cached["billing_cost"], 3)
        self.assertFalse(second_cached["existing_access"])
        status, second_history = self.request("/api/stock-research/reports", token="second-token")
        self.assertEqual(status, 200)
        self.assertEqual(second_history["quota"]["credit_balance"], 2)
        self.assertEqual(second_history["quota"]["monthly_used"], 1)
        status, cached = self.request(
            "/api/stock-research/jobs", method="POST",
            payload={"type": "stock", "value": "603186"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(cached["reused"])
        self.assertEqual(cached["billing_cost"], 0)
        self.assertFalse(cached["charged"])
        self.assertTrue(cached["existing_access"])
        self.assertEqual(cached["job"]["report_id"], completed["report_id"])
        status, history = self.request("/api/stock-research/reports")
        self.assertEqual(status, 200)
        self.assertEqual(len(history["reports"]), 1)
        status, admin = self.request("/api/admin/stock-research/jobs", token="admin-token")
        self.assertEqual(status, 200)
        self.assertEqual(admin["jobs"][0]["source_count"], 2)

    def test_unauthenticated_and_multi_subject_are_rejected(self):
        status, _ = self.request("/api/stock-research/reports", token="")
        self.assertEqual(status, 401)
        status, _ = self.request("/api/stock-research/jobs", method="POST", payload={"type": "industry_chain", "value": "算力、PCB"})
        self.assertEqual(status, 422)

    def test_admin_can_record_blind_benchmark_result(self):
        status, payload = self.request(
            "/api/admin/stock-research/benchmark", method="POST", token="admin-token",
            payload={"sample_key": "stock-01", "provider": "luna", "citation_rate": 98, "completeness_rate": 100, "severe_error": False, "quality_score": 93, "cost_cny": 1.1, "duration_seconds": 120},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["metrics"]["luna"]["samples"], 1)
        self.assertFalse(payload["decision"]["gate_passed"])


if __name__ == "__main__":
    unittest.main()
