from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from trade_review_agent.api import simple_api
from trade_review_agent.auth_system import (
    AuthError,
    acknowledge_update_notice,
    admin_dashboard,
    confirm_membership_order,
    create_membership_order,
    create_update_notice,
    init_auth_db,
    list_pending_update_notices,
    list_update_notices,
    publish_update_notice,
    public_credit_catalog,
    public_membership_catalog,
    reject_membership_order,
    unpublish_update_notice,
)


class ProductScopeTest(unittest.TestCase):
    def _database(self) -> tuple[tempfile.TemporaryDirectory[str], Path, int, int]:
        temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(temp_dir.name) / "auth.sqlite"
        init_auth_db(db_path)
        now = "2026-07-20T10:00:00+08:00"
        with closing(sqlite3.connect(db_path)) as conn:
            with conn:
                admin_id = int(conn.execute(
                    """
                    INSERT INTO users (phone, username, email, email_verified, password_hash, password_salt,
                                       role, status, invite_code, created_at)
                    VALUES ('admin', 'adminuser', 'admin@example.com', 1, 'hash', 'salt',
                            'admin', 'active', 'ADMINCODE', ?)
                    """,
                    (now,),
                ).lastrowid)
                user_id = int(conn.execute(
                    """
                    INSERT INTO users (phone, username, email, email_verified, password_hash, password_salt,
                                       role, status, invite_code, created_at)
                    VALUES ('user', 'normaluser', 'user@example.com', 1, 'hash', 'salt',
                            'user', 'active', 'USERCODE', ?)
                    """,
                    (now,),
                ).lastrowid)
                conn.execute(
                    "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES ('user-token', ?, '2999-01-01', ?)",
                    (user_id, now),
                )
        return temp_dir, db_path, admin_id, user_id

    def test_pending_notices_are_ordered_filtered_and_acknowledged_idempotently(self) -> None:
        temp_dir, db_path, admin_id, user_id = self._database()
        self.addCleanup(temp_dir.cleanup)
        first = create_update_notice(db_path, title="First", version="v1", items=["One"], admin_id=admin_id)
        second = create_update_notice(db_path, title="Second", version="v2", items=["Two"], admin_id=admin_id)
        expired = create_update_notice(db_path, title="Expired", version="v0", items=["Old"], admin_id=admin_id)
        for notice in (first, second, expired):
            publish_update_notice(db_path, notice_id=int(notice["id"]))
        with closing(sqlite3.connect(db_path)) as conn:
            with conn:
                conn.execute("UPDATE users SET created_at = '2026-07-17T09:00:00+08:00' WHERE id = ?", (user_id,))
                conn.execute("UPDATE update_notices SET published_at = '2026-07-18T10:00:00+08:00' WHERE id = ?", (first["id"],))
                conn.execute("UPDATE update_notices SET published_at = '2026-07-19T10:00:00+08:00' WHERE id = ?", (second["id"],))
                conn.execute("UPDATE update_notices SET published_at = '2026-07-17T10:00:00+08:00' WHERE id = ?", (expired["id"],))
                conn.execute("UPDATE update_notices SET expires_at = '2020-01-01T00:00:00+08:00' WHERE id = ?", (expired["id"],))

        pending = list_pending_update_notices(db_path, user_id=user_id)
        self.assertEqual([item["id"] for item in pending], [second["id"]])
        first_ack = acknowledge_update_notice(db_path, notice_id=int(second["id"]), user_id=user_id)
        second_ack = acknowledge_update_notice(db_path, notice_id=int(second["id"]), user_id=user_id)
        self.assertEqual(first_ack, second_ack)
        self.assertEqual(list_pending_update_notices(db_path, user_id=user_id), [])
        with closing(sqlite3.connect(db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM update_notice_acknowledgements").fetchone()[0], 1)

        archived = unpublish_update_notice(db_path, notice_id=int(second["id"]))
        self.assertEqual(archived["status"], "archived")
        self.assertEqual(list_pending_update_notices(db_path, user_id=user_id), [])

    def test_pending_notices_ignore_pre_registration_history_and_admins(self) -> None:
        temp_dir, db_path, admin_id, user_id = self._database()
        self.addCleanup(temp_dir.cleanup)
        old_notice = create_update_notice(db_path, title="Old", version="v1", items=["Old"], admin_id=admin_id)
        new_notice = create_update_notice(db_path, title="New", version="v2", items=["New"], admin_id=admin_id)
        for notice in (old_notice, new_notice):
            publish_update_notice(db_path, notice_id=int(notice["id"]))
        with closing(sqlite3.connect(db_path)) as conn:
            with conn:
                conn.execute("UPDATE update_notices SET published_at = '2026-07-19T09:00:00+08:00' WHERE id = ?", (old_notice["id"],))
                conn.execute("UPDATE update_notices SET published_at = '2026-07-20T11:00:00+08:00' WHERE id = ?", (new_notice["id"],))
                conn.execute("UPDATE users SET created_at = '2026-07-20T10:30:00+08:00' WHERE id = ?", (user_id,))
                conn.execute(
                    "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES ('admin-token', ?, '2999-01-01', '2026-07-20T10:00:00+08:00')",
                    (admin_id,),
                )

        self.assertEqual([item["id"] for item in list_pending_update_notices(db_path, user_id=user_id)], [new_notice["id"]])
        self.assertEqual(list_pending_update_notices(db_path, user_id=admin_id), [])
        with self.assertRaises(AuthError) as error:
            acknowledge_update_notice(db_path, notice_id=int(old_notice["id"]), user_id=user_id)
        self.assertEqual(error.exception.status, 404)

    def test_notice_payload_and_dashboard_do_not_expose_removed_statistics(self) -> None:
        temp_dir, db_path, admin_id, _user_id = self._database()
        self.addCleanup(temp_dir.cleanup)
        create_update_notice(db_path, title="No stats", version="v1", items=["One"], admin_id=admin_id)
        notice = list_update_notices(db_path)[0]
        for field in ("target_count", "acknowledged_count", "acknowledgement_rate"):
            self.assertNotIn(field, notice)
        self.assertNotIn("funnel_summary", admin_dashboard(db_path, days=30)["analytics"])

    def test_concurrent_membership_confirmation_delivers_entitlement_once(self) -> None:
        temp_dir, db_path, admin_id, user_id = self._database()
        self.addCleanup(temp_dir.cleanup)
        order = create_membership_order(db_path, user_id=user_id)
        with closing(sqlite3.connect(db_path)) as conn:
            with conn:
                conn.execute("UPDATE orders SET status = 'submitted' WHERE id = ?", (order["id"],))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda _index: confirm_membership_order(db_path, order_id=int(order["id"]), admin_id=admin_id),
                range(2),
            ))
        self.assertEqual([result["status"] for result in results], ["paid", "paid"])
        with closing(sqlite3.connect(db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM membership_ledger WHERE order_id = ?", (order["id"],)).fetchone()[0], 1)

    def test_membership_rejection_requires_and_persists_reason(self) -> None:
        temp_dir, db_path, admin_id, user_id = self._database()
        self.addCleanup(temp_dir.cleanup)
        order = create_membership_order(db_path, user_id=user_id)
        with closing(sqlite3.connect(db_path)) as conn:
            with conn:
                conn.execute("UPDATE orders SET status = 'submitted' WHERE id = ?", (order["id"],))
        with self.assertRaises(AuthError) as error:
            reject_membership_order(db_path, order_id=int(order["id"]), admin_id=admin_id, admin_note="")
        self.assertEqual(error.exception.status, 400)
        rejected = reject_membership_order(
            db_path,
            order_id=int(order["id"]),
            admin_id=admin_id,
            admin_note="付款金额未到账，请核对交易记录",
        )
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(rejected["admin_note"], "付款金额未到账，请核对交易记录")

    def test_payment_qr_assets_are_embedded_only_in_authenticated_catalogs(self) -> None:
        public = public_membership_catalog()
        private = public_membership_catalog(include_payment_assets=True)
        self.assertNotIn("alipay_qr_url", public["plans"][0])
        self.assertNotIn("wechat_qr_url", public["plans"][0])
        self.assertNotIn("alipay_qr_url", private["plans"][0])
        self.assertTrue(private["plans"][0]["wechat_qr_url"].startswith("data:image/"))
        self.assertNotIn("/pay/", json.dumps(private))

        public_credits = public_credit_catalog()
        private_credits = public_credit_catalog(include_payment_assets=True)
        self.assertNotIn("payment_assets", public_credits)
        self.assertNotIn("alipay_qr_url", private_credits["payment_assets"])
        self.assertTrue(private_credits["payment_assets"]["wechat_qr_url"].startswith("data:image/"))
        self.assertNotIn("/pay/", json.dumps(private_credits))


class PublicBoundaryApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite"
        init_auth_db(self.db_path)
        self.auth_patch = patch.object(simple_api, "AUTH_DB", self.db_path)
        self.auth_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), simple_api.TradeReviewHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.auth_patch.stop()
        self.temp_dir.cleanup()

    def _request(self, path: str, *, method: str = "GET", payload: dict | None = None, token: str | None = None) -> tuple[int, dict]:
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(self.base_url + path, data=body, method=method, headers=headers)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_only_membership_catalog_is_public(self) -> None:
        plan_status, catalog = self._request("/api/public/membership/plans")
        self.assertEqual(plan_status, 200)
        self.assertEqual({plan["id"] for plan in catalog["plans"]}, {"monthly_membership", "annual_membership"})
        self.assertNotIn("alipay_qr_url", catalog["plans"][0])
        self.assertNotIn("wechat_qr_url", catalog["plans"][0])

        for path, method in (
            ("/api/public/samples/review", "GET"),
            ("/api/review/demo-completed", "POST"),
            ("/api/funnel-events", "POST"),
        ):
            status, _payload = self._request(path, method=method, payload={} if method == "POST" else None)
            self.assertEqual(status, 404)

    def test_notices_and_daily_top5_history_require_login(self) -> None:
        for path in (
            "/api/update-notices/pending",
            "/api/update-notices/latest",
            "/api/auction-strength?date=2026-07-01",
        ):
            status, _payload = self._request(path)
            self.assertEqual(status, 401)

    def test_pending_notice_api_returns_only_homepage_relevant_latest_notice(self) -> None:
        now = "2026-07-20T10:00:00+08:00"
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                admin_id = int(conn.execute(
                    """
                    INSERT INTO users (phone, username, email, email_verified, password_hash, password_salt,
                                       role, status, invite_code, created_at)
                    VALUES ('api-admin', 'apiadmin', 'api-admin@example.com', 1, 'hash', 'salt',
                            'admin', 'active', 'APIADMIN', ?)
                    """,
                    (now,),
                ).lastrowid)
                user_id = int(conn.execute(
                    """
                    INSERT INTO users (phone, username, email, email_verified, password_hash, password_salt,
                                       role, status, invite_code, created_at)
                    VALUES ('api-user', 'apiuser', 'api-user@example.com', 1, 'hash', 'salt',
                            'user', 'active', 'APIUSER', ?)
                    """,
                    (now,),
                ).lastrowid)
                conn.execute(
                    "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES ('api-user-token', ?, '2999-01-01', ?)",
                    (user_id, now),
                )
                conn.execute(
                    "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES ('api-admin-token', ?, '2999-01-01', ?)",
                    (admin_id, now),
                )
        older = create_update_notice(self.db_path, title="Older", version="v1", items=["Older"], admin_id=admin_id)
        latest = create_update_notice(self.db_path, title="Latest", version="v2", items=["Latest"], admin_id=admin_id)
        for notice in (older, latest):
            publish_update_notice(self.db_path, notice_id=int(notice["id"]))
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute("UPDATE update_notices SET published_at = '2026-07-20T10:01:00+08:00' WHERE id = ?", (older["id"],))
                conn.execute("UPDATE update_notices SET published_at = '2026-07-20T10:02:00+08:00' WHERE id = ?", (latest["id"],))

        status, payload = self._request("/api/update-notices/pending", token="api-user-token")
        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in payload["notices"]], [latest["id"]])

        ack_status, acknowledged = self._request(
            f"/api/update-notices/{latest['id']}/ack", method="POST", payload={}, token="api-user-token"
        )
        self.assertEqual(ack_status, 200)
        self.assertEqual(acknowledged["acknowledgement"]["notice_id"], latest["id"])
        self.assertEqual(acknowledged["remaining"], [])

        admin_status, admin_payload = self._request("/api/update-notices/pending", token="api-admin-token")
        self.assertEqual(admin_status, 200)
        self.assertEqual(admin_payload["notices"], [])


if __name__ == "__main__":
    unittest.main()
