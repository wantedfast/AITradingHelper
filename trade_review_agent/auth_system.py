from __future__ import annotations

import hashlib
import hmac
import base64
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import smtplib
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

from trade_review_agent.auction_strength.close_email import (
    close_email_cutoff_at,
    close_email_due_at,
    collect_close_email_snapshot,
)
from trade_review_agent.legal_agreements import (
    REGISTRATION_AGREEMENT_TYPE,
    REGISTRATION_AGREEMENT_VERSION,
    registration_agreement_payload,
)
from trade_review_agent.outlook_graph import (
    configure_outlook_graph_runtime,
    init_outlook_graph_schema,
    send_outlook_mime,
)


CN_TZ = ZoneInfo("Asia/Shanghai")
PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
CREDIT_GRANT_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
SESSION_DAYS = 30
INITIAL_FREE_CREDITS = 5
REFERRAL_REWARD_CREDITS = 5
INVITEE_BONUS_CREDITS = 2
FEEDBACK_REWARD_CREDITS = 10
FEATURE_CREDIT_COSTS = {
    "review_report": 2,
    "watch_plan": 1,
    "market_day_report": 1,
    "ai_research_view": 2,
    "auction_strength_view": 2,
}
SMS_CODE_TTL_MINUTES = 5
SMS_RESEND_SECONDS = 60
EMAIL_CODE_TTL_MINUTES = 10
EMAIL_RESEND_SECONDS = 60
UPDATE_EMAIL_MAX_ATTEMPTS = 3
UPDATE_EMAIL_RETRY_MINUTES = (1, 5, 30)
DAILY_TOP5_EMAIL_MAX_ATTEMPTS = 8
DAILY_TOP5_EMAIL_RETRY_MINUTES = (1, 5, 15, 30, 60, 180, 360)
PERMANENT_EMAIL_ERROR_PREFIX = "[permanent] "
PERMANENT_EMAIL_ERROR_MARKERS = (
    "blacklisted by the recipient",
    "user unknown",
    "no such user",
    "recipient address rejected",
    "mailbox not found",
    "recipient not found",
    "account does not exist",
    "invalid recipient",
)
DAILY_TOP5_CLOSE_EMAIL_RETRY_MINUTES = 5
CREDIT_PACKAGES = {
    "pack_10": {"plan_name": "10 次使用包", "credits": 10, "amount_cents": 990},
    "pack_50": {"plan_name": "50 次使用包", "credits": 50, "amount_cents": 3990},
    "pack_120": {"plan_name": "120 次使用包", "credits": 120, "amount_cents": 7990},
}
MONTHLY_MEMBERSHIP_PLAN = {
    "id": "monthly_membership",
    "plan_name": "月度会员",
    "amount_cents": 5900,
    "duration_days": 31,
}
ANNUAL_MEMBERSHIP_PLAN = {
    "id": "annual_membership",
    "plan_name": "年度会员",
    "amount_cents": 39900,
    "duration_days": 365,
}


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def init_auth_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE NOT NULL,
                username TEXT UNIQUE,
                email TEXT UNIQUE,
                email_verified INTEGER NOT NULL DEFAULT 0,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'active',
                invite_code TEXT UNIQUE NOT NULL,
                referred_by INTEGER,
                register_ip TEXT,
                last_login_at TEXT,
                created_at TEXT NOT NULL,
                update_emails_enabled INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (referred_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS invalidated_sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS credit_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                reason TEXT NOT NULL,
                related_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS credit_grant_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                credits INTEGER NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                eligible_count INTEGER NOT NULL DEFAULT 0,
                granted_count INTEGER NOT NULL DEFAULT 0,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS admin_credit_adjustments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                reason TEXT NOT NULL,
                admin_id INTEGER,
                resulting_balance INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (admin_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_user_id INTEGER NOT NULL,
                referred_user_id INTEGER UNIQUE NOT NULL,
                reward_credits INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (referrer_user_id) REFERENCES users(id),
                FOREIGN KEY (referred_user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                feature TEXT NOT NULL,
                credits_spent INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL,
                related_id TEXT,
                ip TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                contact TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                reward_credits INTEGER NOT NULL DEFAULT 0,
                admin_note TEXT,
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                order_no TEXT UNIQUE NOT NULL,
                plan_name TEXT NOT NULL,
                credits INTEGER NOT NULL,
                amount_cents INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                paid_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS membership_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                order_id INTEGER NOT NULL,
                plan_name TEXT NOT NULL,
                started_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                admin_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (order_id) REFERENCES orders(id)
            );

            CREATE TABLE IF NOT EXISTS update_notices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                version TEXT NOT NULL,
                items_json TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                content_markdown TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                audience TEXT NOT NULL DEFAULT 'registered_users',
                created_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                published_at TEXT,
                expires_at TEXT,
                FOREIGN KEY (created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS update_notice_acknowledgements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notice_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                acknowledged_at TEXT NOT NULL,
                FOREIGN KEY (notice_id) REFERENCES update_notices(id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE (notice_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS update_email_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notice_id INTEGER NOT NULL,
                request_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending',
                created_by INTEGER,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                FOREIGN KEY (notice_id) REFERENCES update_notices(id),
                FOREIGN KEY (created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS update_email_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                next_attempt_at TEXT,
                last_error TEXT,
                sent_at TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (campaign_id) REFERENCES update_email_campaigns(id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE (campaign_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS daily_top5_email_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL UNIQUE,
                report_id TEXT NOT NULL,
                report_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS daily_top5_email_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                content_variant TEXT NOT NULL DEFAULT 'teaser',
                membership_active INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                next_attempt_at TEXT,
                last_error TEXT,
                sent_at TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (campaign_id) REFERENCES daily_top5_email_campaigns(id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE (campaign_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS ai_report_email_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT NOT NULL,
                run_id TEXT NOT NULL,
                report_date TEXT NOT NULL,
                report_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                UNIQUE (report_type, run_id)
            );

            CREATE TABLE IF NOT EXISTS ai_report_email_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                content_variant TEXT NOT NULL DEFAULT 'teaser',
                membership_active INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                next_attempt_at TEXT,
                last_error TEXT,
                sent_at TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (campaign_id) REFERENCES ai_report_email_campaigns(id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE (campaign_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS daily_top5_close_email_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL UNIQUE,
                report_id TEXT NOT NULL,
                report_json TEXT NOT NULL,
                close_report_json TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                calculation_status TEXT NOT NULL DEFAULT 'pending',
                calculation_attempt_count INTEGER NOT NULL DEFAULT 0,
                calculation_due_at TEXT,
                next_calculation_at TEXT,
                calculation_started_at TEXT,
                calculation_ready_at TEXT,
                calculation_override_requested_at TEXT,
                calculation_last_error TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS daily_top5_close_email_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                content_variant TEXT NOT NULL DEFAULT 'full',
                membership_active INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                next_attempt_at TEXT,
                last_error TEXT,
                sent_at TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (campaign_id) REFERENCES daily_top5_close_email_campaigns(id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE (campaign_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS sms_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                purpose TEXT NOT NULL,
                ip TEXT,
                consumed INTEGER NOT NULL DEFAULT 0,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS email_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                purpose TEXT NOT NULL,
                ip TEXT,
                consumed INTEGER NOT NULL DEFAULT 0,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agreement_acceptances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                agreement_type TEXT NOT NULL,
                agreement_version TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                accepted_at TEXT NOT NULL,
                ip TEXT,
                user_agent TEXT,
                acceptance_method TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE (user_id, agreement_type, agreement_version)
            );

            CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_events(created_at);
            CREATE INDEX IF NOT EXISTS idx_credit_grant_campaigns_created ON credit_grant_campaigns(created_at);
            CREATE INDEX IF NOT EXISTS idx_admin_credit_adjustments_user_created
                ON admin_credit_adjustments(user_id, created_at DESC);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_credit_ledger_grant_campaign_user
                ON credit_ledger(user_id, related_id) WHERE reason = 'admin_grant_all';
            CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback(status);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
            CREATE INDEX IF NOT EXISTS idx_update_notices_status ON update_notices(status, published_at);
            CREATE INDEX IF NOT EXISTS idx_update_notice_acks_user ON update_notice_acknowledgements(user_id, acknowledged_at);
            CREATE INDEX IF NOT EXISTS idx_update_email_campaigns_notice ON update_email_campaigns(notice_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_update_email_deliveries_queue ON update_email_deliveries(status, next_attempt_at, id);
            CREATE INDEX IF NOT EXISTS idx_daily_top5_email_deliveries_queue
                ON daily_top5_email_deliveries(status, next_attempt_at, id);
            CREATE INDEX IF NOT EXISTS idx_ai_report_email_deliveries_queue
                ON ai_report_email_deliveries(status, next_attempt_at, id);
            CREATE INDEX IF NOT EXISTS idx_ai_report_email_campaigns_date
                ON ai_report_email_campaigns(report_type, report_date, id);
            CREATE INDEX IF NOT EXISTS idx_daily_top5_close_email_campaigns_queue
                ON daily_top5_close_email_campaigns(calculation_status, next_calculation_at, id);
            CREATE INDEX IF NOT EXISTS idx_daily_top5_close_email_deliveries_queue
                ON daily_top5_close_email_deliveries(status, next_attempt_at, id);
            CREATE INDEX IF NOT EXISTS idx_sms_codes_phone ON sms_codes(phone, purpose, created_at);
            CREATE INDEX IF NOT EXISTS idx_email_codes_email ON email_codes(email, purpose, created_at);
            CREATE INDEX IF NOT EXISTS idx_agreement_acceptances_user ON agreement_acceptances(user_id, accepted_at);
            """
        )
        _ensure_user_columns(conn)
        _ensure_order_columns(conn)
        _ensure_update_notice_columns(conn)
        _ensure_daily_top5_close_email_schema(conn)
        init_outlook_graph_schema(conn)
        conn.executescript(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username) WHERE username IS NOT NULL AND username != '';
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL AND email != '';
            """
        )
        _ensure_admin(conn)
    configure_outlook_graph_runtime(db_path)


def _ensure_user_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    migrations = {
        "username": "ALTER TABLE users ADD COLUMN username TEXT",
        "email": "ALTER TABLE users ADD COLUMN email TEXT",
        "email_verified": "ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0",
        "membership_plan": "ALTER TABLE users ADD COLUMN membership_plan TEXT",
        "membership_status": "ALTER TABLE users ADD COLUMN membership_status TEXT",
        "membership_expires_at": "ALTER TABLE users ADD COLUMN membership_expires_at TEXT",
        "update_emails_enabled": "ALTER TABLE users ADD COLUMN update_emails_enabled INTEGER NOT NULL DEFAULT 1",
    }
    for column, statement in migrations.items():
        if column not in columns:
            conn.execute(statement)


def _ensure_order_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(orders)").fetchall()}
    migrations = {
        "payment_provider": "ALTER TABLE orders ADD COLUMN payment_provider TEXT",
        "provider_trade_no": "ALTER TABLE orders ADD COLUMN provider_trade_no TEXT",
        "paid_amount_cents": "ALTER TABLE orders ADD COLUMN paid_amount_cents INTEGER",
        "product_type": "ALTER TABLE orders ADD COLUMN product_type TEXT",
        "package_id": "ALTER TABLE orders ADD COLUMN package_id TEXT",
        "duration_days": "ALTER TABLE orders ADD COLUMN duration_days INTEGER",
        "payment_method": "ALTER TABLE orders ADD COLUMN payment_method TEXT",
        "payment_submit_status": "ALTER TABLE orders ADD COLUMN payment_submit_status TEXT",
        "payer_name": "ALTER TABLE orders ADD COLUMN payer_name TEXT",
        "payer_note": "ALTER TABLE orders ADD COLUMN payer_note TEXT",
        "payer_paid_at": "ALTER TABLE orders ADD COLUMN payer_paid_at TEXT",
        "submitted_amount_cents": "ALTER TABLE orders ADD COLUMN submitted_amount_cents INTEGER",
        "submitted_at": "ALTER TABLE orders ADD COLUMN submitted_at TEXT",
        "admin_id": "ALTER TABLE orders ADD COLUMN admin_id INTEGER",
        "admin_note": "ALTER TABLE orders ADD COLUMN admin_note TEXT",
        "confirmed_at": "ALTER TABLE orders ADD COLUMN confirmed_at TEXT",
        "rejected_at": "ALTER TABLE orders ADD COLUMN rejected_at TEXT",
    }
    for column, statement in migrations.items():
        if column not in columns:
            conn.execute(statement)


def _ensure_update_notice_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(update_notices)").fetchall()}
    migrations = {
        "summary": "ALTER TABLE update_notices ADD COLUMN summary TEXT NOT NULL DEFAULT ''",
        "content_markdown": "ALTER TABLE update_notices ADD COLUMN content_markdown TEXT NOT NULL DEFAULT ''",
        "audience": "ALTER TABLE update_notices ADD COLUMN audience TEXT NOT NULL DEFAULT 'registered_users'",
        "expires_at": "ALTER TABLE update_notices ADD COLUMN expires_at TEXT",
    }
    for column, statement in migrations.items():
        if column not in columns:
            conn.execute(statement)


def _ensure_daily_top5_close_email_schema(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(daily_top5_close_email_campaigns)").fetchall()}
    migrations = {
        "close_report_json": "ALTER TABLE daily_top5_close_email_campaigns ADD COLUMN close_report_json TEXT NOT NULL DEFAULT ''",
        "calculation_status": "ALTER TABLE daily_top5_close_email_campaigns ADD COLUMN calculation_status TEXT NOT NULL DEFAULT 'pending'",
        "calculation_attempt_count": "ALTER TABLE daily_top5_close_email_campaigns ADD COLUMN calculation_attempt_count INTEGER NOT NULL DEFAULT 0",
        "calculation_due_at": "ALTER TABLE daily_top5_close_email_campaigns ADD COLUMN calculation_due_at TEXT",
        "next_calculation_at": "ALTER TABLE daily_top5_close_email_campaigns ADD COLUMN next_calculation_at TEXT",
        "calculation_started_at": "ALTER TABLE daily_top5_close_email_campaigns ADD COLUMN calculation_started_at TEXT",
        "calculation_ready_at": "ALTER TABLE daily_top5_close_email_campaigns ADD COLUMN calculation_ready_at TEXT",
        "calculation_override_requested_at": "ALTER TABLE daily_top5_close_email_campaigns ADD COLUMN calculation_override_requested_at TEXT",
        "calculation_last_error": "ALTER TABLE daily_top5_close_email_campaigns ADD COLUMN calculation_last_error TEXT",
    }
    for column, statement in migrations.items():
        if column not in columns:
            conn.execute(statement)
    conn.execute(
        """
        UPDATE update_notices
        SET summary = version
        WHERE TRIM(COALESCE(summary, '')) = ''
        """
    )
    conn.execute(
        """
        UPDATE update_notices
        SET content_markdown = (
            SELECT GROUP_CONCAT(value, char(10))
            FROM json_each(COALESCE(items_json, '[]'))
        )
        WHERE TRIM(COALESCE(content_markdown, '')) = ''
        """
    )
    conn.execute(
        """
        UPDATE update_notices
        SET audience = 'registered_users'
        WHERE TRIM(COALESCE(audience, '')) = ''
        """
    )


def send_login_code(db_path: Path, *, phone: str, purpose: str = "login", ip: str = "", log_path: Path | None = None) -> dict[str, Any]:
    phone = normalize_phone(phone)
    purpose = _normalize_sms_purpose(purpose)
    now_dt = datetime.now(CN_TZ)
    now = now_dt.isoformat()
    with _connect(db_path) as conn:
        recent = conn.execute(
            """
            SELECT created_at
            FROM sms_codes
            WHERE phone = ? AND purpose = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (phone, purpose),
        ).fetchone()
        if recent:
            elapsed = now_dt - datetime.fromisoformat(recent["created_at"])
            wait_seconds = SMS_RESEND_SECONDS - int(elapsed.total_seconds())
            if wait_seconds > 0:
                raise AuthError(f"验证码发送过于频繁，请 {wait_seconds} 秒后再试", 429)

        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = (now_dt + timedelta(minutes=SMS_CODE_TTL_MINUTES)).isoformat()
        conn.execute(
            """
            INSERT INTO sms_codes (phone, code_hash, purpose, ip, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (phone, _hash_sms_code(phone, code), purpose, ip, expires_at, now),
        )
        provider_result = _send_sms_code(phone, code, log_path)
        payload = {
            "ok": True,
            "expires_in": SMS_CODE_TTL_MINUTES * 60,
            "resend_after": SMS_RESEND_SECONDS,
            "provider": provider_result["provider"],
        }
        if provider_result.get("debug_code"):
            payload["debug_code"] = provider_result["debug_code"]
        return payload


def send_email_code(db_path: Path, *, email: str, purpose: str = "register", ip: str = "", log_path: Path | None = None) -> dict[str, Any]:
    email = normalize_email(email)
    purpose = _normalize_email_purpose(purpose)
    now_dt = datetime.now(CN_TZ)
    now = now_dt.isoformat()
    with _connect(db_path) as conn:
        recent = conn.execute(
            """
            SELECT created_at
            FROM email_codes
            WHERE email = ? AND purpose = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (email, purpose),
        ).fetchone()
        if recent:
            elapsed = now_dt - datetime.fromisoformat(recent["created_at"])
            wait_seconds = EMAIL_RESEND_SECONDS - int(elapsed.total_seconds())
            if wait_seconds > 0:
                raise AuthError(f"邮箱验证码发送过于频繁，请 {wait_seconds} 秒后再试", 429)

        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = (now_dt + timedelta(minutes=EMAIL_CODE_TTL_MINUTES)).isoformat()
        conn.execute(
            """
            INSERT INTO email_codes (email, code_hash, purpose, ip, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (email, _hash_email_code(email, code), purpose, ip, expires_at, now),
        )
        provider_result = _send_email_code(email, code, log_path)
        payload = {
            "ok": True,
            "expires_in": EMAIL_CODE_TTL_MINUTES * 60,
            "resend_after": EMAIL_RESEND_SECONDS,
            "provider": provider_result["provider"],
        }
        return payload


def send_email_binding_code(
    db_path: Path, *, user_id: int, email: str, ip: str = "", log_path: Path | None = None
) -> dict[str, Any]:
    email = normalize_email(email)
    with _connect(db_path) as conn:
        user = _fetch_user_by_id(conn, user_id)
        if bool(user["email_verified"]):
            raise AuthError("当前账号已绑定并验证邮箱，不能更换", 409)
        existing = _fetch_user_by_email(conn, email)
        if existing and int(existing["id"]) != user_id:
            raise AuthError("该邮箱已被其他账号使用", 409)
    return send_email_code(db_path, email=email, purpose="bind_email", ip=ip, log_path=log_path)


def bind_user_email(db_path: Path, *, user_id: int, email: str, email_code: str) -> dict[str, Any]:
    email = normalize_email(email)
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        user = _fetch_user_by_id(conn, user_id)
        if bool(user["email_verified"]):
            raise AuthError("当前账号已绑定并验证邮箱，不能更换", 409)
        existing = _fetch_user_by_email(conn, email)
        if existing and int(existing["id"]) != user_id:
            raise AuthError("该邮箱已被其他账号使用", 409)
        _verify_email_code(conn, email, email_code, purpose="bind_email")
        conn.execute(
            "UPDATE users SET email = ?, email_verified = 1 WHERE id = ?",
            (email, user_id),
        )
        conn.execute("DELETE FROM email_codes WHERE email = ? AND purpose = 'bind_email'", (email,))
        return _user_payload(conn, _fetch_user_by_id(conn, user_id))


def register_user(db_path: Path, *, phone: str, code: str, password: str, invite_code: str = "", ip: str = "") -> dict[str, Any]:
    phone = normalize_phone(phone)
    _validate_password(password)
    invite_code = invite_code.strip()
    now = _now()
    with _connect(db_path) as conn:
        _verify_sms_code(conn, phone, code, purpose="login")
        if _fetch_user_by_phone(conn, phone):
            raise AuthError("手机号已注册，请直接登录", 409)

        referrer = _fetch_user_by_invite_code(conn, invite_code) if invite_code else None
        salt, password_hash = _hash_password(password)
        user_invite_code = _new_invite_code(conn)
        cursor = conn.execute(
            """
            INSERT INTO users (phone, password_hash, password_salt, role, invite_code, referred_by, register_ip, created_at)
            VALUES (?, ?, ?, 'user', ?, ?, ?, ?)
            """,
            (phone, password_hash, salt, user_invite_code, referrer["id"] if referrer else None, ip, now),
        )
        user_id = int(cursor.lastrowid)
        _add_credits(conn, user_id, INITIAL_FREE_CREDITS, "initial_free", None)

        if referrer:
            conn.execute(
                """
                INSERT INTO referrals (referrer_user_id, referred_user_id, reward_credits, status, created_at)
                VALUES (?, ?, ?, 'completed', ?)
                """,
                (referrer["id"], user_id, REFERRAL_REWARD_CREDITS, now),
            )
            _add_credits(conn, int(referrer["id"]), REFERRAL_REWARD_CREDITS, "referral_reward", str(user_id))
            _add_credits(conn, user_id, INVITEE_BONUS_CREDITS, "invitee_bonus", str(referrer["id"]))

        user = _fetch_user_by_id(conn, user_id)
        token = _create_session(conn, user_id)
        conn.execute("DELETE FROM sms_codes WHERE phone = ?", (phone,))
        return {"token": token, "user": _user_payload(conn, user)}


def register_password_user(
    db_path: Path,
    *,
    username: str,
    email: str,
    password: str,
    email_code: str,
    invite_code: str = "",
    ip: str = "",
    user_agent: str = "",
    agreement_accepted: object = None,
    agreement_version: object = None,
) -> dict[str, Any]:
    _validate_registration_agreement(agreement_accepted, agreement_version)
    username = normalize_username(username)
    email = normalize_email(email)
    _validate_password(password)
    invite_code = invite_code.strip()
    now = _now()
    with _connect(db_path) as conn:
        _verify_email_code(conn, email, email_code, purpose="register")
        if _fetch_user_by_username(conn, username):
            raise AuthError("账号名已被占用", 409)
        if _fetch_user_by_email(conn, email):
            raise AuthError("邮箱已注册，请直接登录", 409)

        referrer = _fetch_user_by_invite_code(conn, invite_code) if invite_code else None
        salt, password_hash = _hash_password(password)
        placeholder_phone = f"email:{email}"
        cursor = conn.execute(
            """
            INSERT INTO users (
                phone, username, email, email_verified, password_hash, password_salt,
                role, invite_code, referred_by, register_ip, created_at
            )
            VALUES (?, ?, ?, 1, ?, ?, 'user', ?, ?, ?, ?)
            """,
            (placeholder_phone, username, email, password_hash, salt, _new_invite_code(conn), referrer["id"] if referrer else None, ip, now),
        )
        user_id = int(cursor.lastrowid)
        agreement = registration_agreement_payload()
        conn.execute(
            """
            INSERT INTO agreement_acceptances (
                user_id, agreement_type, agreement_version, content_hash,
                accepted_at, ip, user_agent, acceptance_method
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'registration_modal')
            """,
            (
                user_id,
                REGISTRATION_AGREEMENT_TYPE,
                REGISTRATION_AGREEMENT_VERSION,
                agreement["content_hash"],
                now,
                (ip or "").strip(),
                (user_agent or "")[:512],
            ),
        )
        _add_credits(conn, user_id, INITIAL_FREE_CREDITS, "initial_free", None)

        if referrer:
            conn.execute(
                """
                INSERT INTO referrals (referrer_user_id, referred_user_id, reward_credits, status, created_at)
                VALUES (?, ?, ?, 'completed', ?)
                """,
                (referrer["id"], user_id, REFERRAL_REWARD_CREDITS, now),
            )
            _add_credits(conn, int(referrer["id"]), REFERRAL_REWARD_CREDITS, "referral_reward", str(user_id))
            _add_credits(conn, user_id, INVITEE_BONUS_CREDITS, "invitee_bonus", str(referrer["id"]))

        user = _fetch_user_by_id(conn, user_id)
        token = _create_session(conn, user_id)
        conn.execute("DELETE FROM email_codes WHERE email = ?", (email,))
        return {"token": token, "user": _user_payload(conn, user)}


def login_user(db_path: Path, *, phone: str, code: str = "", password: str = "", ip: str = "") -> dict[str, Any]:
    login_id = (phone or "").strip()
    is_admin_login = login_id == os.getenv("ADMIN_PHONE", "admin").strip()
    phone = login_id if is_admin_login else normalize_phone(login_id)
    with _connect(db_path) as conn:
        user = _fetch_user_by_phone(conn, phone)
        if not user:
            raise AuthError("账号不存在，请先注册", 404)
        if is_admin_login:
            if not password or not _verify_password(password, user["password_salt"], user["password_hash"]):
                raise AuthError("管理员账号或密码错误", 401)
        else:
            _verify_sms_code(conn, phone, code, purpose="login")
        if user["status"] != "active":
            raise AuthError("账号已被停用，请联系管理员", 403)
        now = _now()
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, user["id"]))
        token = _create_session(conn, int(user["id"]))
        user = _fetch_user_by_id(conn, int(user["id"]))
        return {"token": token, "user": _user_payload(conn, user)}


def login_password_user(db_path: Path, *, account: str, password: str, ip: str = "") -> dict[str, Any]:
    account = (account or "").strip()
    if not account or not password:
        raise AuthError("请输入账号/邮箱和密码", 400)
    with _connect(db_path) as conn:
        user = _fetch_user_by_login_account(conn, account)
        if not user or not _verify_password(password, user["password_salt"], user["password_hash"]):
            raise AuthError("账号/邮箱或密码错误", 401)
        if user["role"] == "admin":
            raise AuthError("管理员账号请使用运营后台入口登录", 403)
        if user["status"] != "active":
            raise AuthError("账号已被停用，请联系管理员", 403)
        now = _now()
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, user["id"]))
        token = _create_session(conn, int(user["id"]))
        user = _fetch_user_by_id(conn, int(user["id"]))
        return {"token": token, "user": _user_payload(conn, user)}


def login_admin_password_user(db_path: Path, *, account: str, password: str, ip: str = "") -> dict[str, Any]:
    account = (account or "").strip()
    if not account or not password:
        raise AuthError("管理员账号或权限错误", 401)
    with _connect(db_path) as conn:
        user = _fetch_user_by_login_account(conn, account)
        if not user or not _verify_password(password, user["password_salt"], user["password_hash"]):
            raise AuthError("管理员账号或权限错误", 401)
        if user["role"] != "admin":
            raise AuthError("管理员账号或权限错误", 401)
        if user["status"] != "active":
            raise AuthError("账号已被停用，请联系管理员", 403)
        now = _now()
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, user["id"]))
        token = _create_session(conn, int(user["id"]))
        user = _fetch_user_by_id(conn, int(user["id"]))
        return {"token": token, "user": _user_payload(conn, user)}


def logout_user(db_path: Path, token: str) -> None:
    if not token:
        return
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def _session_user_row_strict(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    if not token:
        return None
    now = _now()
    return conn.execute(
        """
        SELECT u.*
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token = ? AND s.expires_at > ?
        """,
        (token, now),
    ).fetchone()


def consume_feature_credit(db_path: Path, *, user_id: int, feature: str, ip: str = "", related_id: str = "") -> dict[str, Any]:
    with _connect(db_path) as conn:
        user = _fetch_user_by_id(conn, user_id)
        if user["role"] == "admin":
            _record_usage(conn, user_id, feature, 0, "admin_free", ip, related_id)
            return _user_payload(conn, user)
        if _has_active_membership(user):
            _record_usage(conn, user_id, feature, 0, "membership_free", ip, related_id)
            return _user_payload(conn, user)

        cost = _feature_credit_cost(feature)
        balance = _credit_balance(conn, user_id)
        if balance < cost:
            _record_usage(conn, user_id, feature, 0, "blocked_no_credits", ip, related_id)
            raise AuthError(f"可用次数不足，本功能需要 {cost} 次，请邀请新用户注册登录获取次数，或购买次数后继续使用", 402)
        _add_credits(conn, user_id, -cost, f"use_{feature}", related_id or None)
        _record_usage(conn, user_id, feature, cost, "charged", ip, related_id)
        return _user_payload(conn, user)


def ensure_feature_credit_available(db_path: Path, *, user_id: int, feature: str, ip: str = "", related_id: str = "") -> dict[str, Any]:
    with _connect(db_path) as conn:
        user = _fetch_user_by_id(conn, user_id)
        if related_id and _feature_charge_exists(conn, user_id, feature, related_id):
            return _user_payload(conn, user)
        if user["role"] == "admin":
            return _user_payload(conn, user)
        if _has_active_membership(user):
            return _user_payload(conn, user)

        cost = _feature_credit_cost(feature)
        balance = _credit_balance(conn, user_id)
        if balance < cost:
            _record_usage(conn, user_id, feature, 0, "blocked_no_credits", ip, related_id)
            raise AuthError(f"可用次数不足，本功能需要 {cost} 次，请邀请新用户注册登录获取次数，或购买次数后继续使用", 402)
        return _user_payload(conn, user)


def consume_feature_credit_once(
    db_path: Path,
    *,
    user_id: int,
    feature: str,
    ip: str = "",
    related_id: str = "",
    credits: int = 1,
) -> dict[str, Any]:
    cost = max(1, int(credits))
    with _connect(db_path) as conn:
        # Serialize the idempotency check and both accounting writes.  A deferred
        # SQLite transaction allows two concurrent acknowledgements to observe
        # the same pre-charge state before either writes, which can double-charge
        # one report.  BEGIN IMMEDIATE obtains the database write reservation up
        # front; the second request then re-checks after the first commits.
        conn.execute("BEGIN IMMEDIATE")
        user = _fetch_user_by_id(conn, user_id)
        if related_id and _feature_charge_exists(conn, user_id, feature, related_id):
            return _user_payload(conn, user)

        if user["role"] == "admin":
            _record_usage(conn, user_id, feature, 0, "admin_free", ip, related_id)
            return _user_payload(conn, user)
        if _has_active_membership(user):
            _record_usage(conn, user_id, feature, 0, "membership_free", ip, related_id)
            return _user_payload(conn, user)

        cost = _feature_credit_cost(feature)
        balance = _credit_balance(conn, user_id)
        if balance < cost:
            _record_usage(conn, user_id, feature, 0, "blocked_no_credits", ip, related_id)
            raise AuthError(f"可用次数不足，本功能需要 {cost} 次，请邀请新用户注册登录获取次数，或购买次数后继续使用", 402)
        _add_credits(conn, user_id, -cost, f"use_{feature}", related_id or None)
        _record_usage(conn, user_id, feature, cost, "charged", ip, related_id)
        return _user_payload(conn, user)


def has_feature_access(db_path: Path, *, user_id: int, feature: str, related_id: str) -> bool:
    with _connect(db_path) as conn:
        user = _fetch_user_by_id(conn, user_id)
        if user["role"] == "admin" or _has_active_membership(user):
            return True
        return bool(related_id and _feature_charge_exists(conn, user_id, feature, related_id))


def submit_feedback(
    db_path: Path,
    *,
    user_id: int,
    category: str,
    content: str,
    contact: str = "",
) -> dict[str, Any]:
    category = (category or "建议").strip()[:40]
    content = content.strip()
    contact = contact.strip()[:120]
    if len(content) < 5:
        raise AuthError("反馈内容至少需要 5 个字", 400)
    now = _now()
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO feedback (user_id, category, content, contact, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, category, content, contact, now),
        )
        return {"id": int(cursor.lastrowid), "status": "pending"}


def credit_packages() -> list[dict[str, Any]]:
    return [{"id": key, **value} for key, value in CREDIT_PACKAGES.items()]


def _manual_checkout_config(prefix: str) -> dict[str, str]:
    prefix = (prefix or "MEMBERSHIP").strip().upper() or "MEMBERSHIP"
    business_hours = (
        os.getenv(f"{prefix}_SUPPORT_HOURS", "").strip()
        or os.getenv("MEMBERSHIP_SUPPORT_HOURS", "工作日 10:00-18:00").strip()
        or "工作日 10:00-18:00"
    )
    confirmation_eta = os.getenv(f"{prefix}_CONFIRMATION_ETA", "").strip()
    support_channel = (
        os.getenv(f"{prefix}_SUPPORT_CHANNEL", "").strip()
        or os.getenv("MEMBERSHIP_SUPPORT_CHANNEL", "如长时间未处理，请联系站内反馈或运营客服。").strip()
    )
    policy_note = (
        os.getenv(f"{prefix}_POLICY_NOTE", "").strip()
        or os.getenv("MEMBERSHIP_POLICY_NOTE", "当前为人工核款开通，退款与发票按人工客服规则处理。").strip()
    )
    return {
        "business_hours": business_hours,
        "confirmation_eta": confirmation_eta or "提交付款信息后由运营在客服工作时间内人工核对",
        "support_channel": support_channel or "如长时间未处理，请联系站内反馈或运营客服。",
        "policy_note": policy_note or "当前为人工核款开通，退款与发票按人工客服规则处理。",
    }


def membership_checkout_config() -> dict[str, str]:
    business_hours = os.getenv("MEMBERSHIP_SUPPORT_HOURS", "工作日 10:00-18:00").strip() or "工作日 10:00-18:00"
    confirmation_eta = os.getenv("MEMBERSHIP_CONFIRMATION_ETA", "").strip()
    support_channel = os.getenv("MEMBERSHIP_SUPPORT_CHANNEL", "如长时间未处理，请联系站内反馈或运营客服。").strip()
    policy_note = os.getenv("MEMBERSHIP_POLICY_NOTE", "当前为人工核款开通，退款与发票按人工客服规则处理。").strip()
    return {
        "business_hours": business_hours,
        "confirmation_eta": confirmation_eta or "提交付款信息后由运营在客服工作时间内人工核对",
        "support_channel": support_channel or "如长时间未处理，请联系站内反馈或运营客服。",
        "policy_note": policy_note or "当前为人工核款开通，退款与发票按人工客服规则处理。",
    }


def credit_checkout_config() -> dict[str, str]:
    return _manual_checkout_config("CREDITS")


def membership_plans() -> list[dict[str, Any]]:
    checkout = membership_checkout_config()
    return [
        {
            **plan,
            "alipay_qr_url": _payment_qr_data_uri("PAYMENT_ALIPAY_QR_FILE", "alipay-qr.jpg"),
            "wechat_qr_url": _payment_qr_data_uri("PAYMENT_WECHAT_QR_FILE", "wechat-qr.jpg"),
            "manual_checkout": checkout,
        }
        for plan in _membership_plans()
    ]


def _payment_qr_data_uri(env_key: str, fallback_name: str) -> str:
    configured_path = os.getenv(env_key, "").strip()
    file_path = (
        Path(configured_path)
        if configured_path
        else Path(__file__).resolve().parent / "private_assets" / "pay" / fallback_name
    )
    if not file_path.exists() or not file_path.is_file():
        return ""
    content_type = mimetypes.guess_type(file_path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def public_membership_catalog(*, include_payment_assets: bool = False) -> dict[str, Any]:
    plans = membership_plans()
    if not include_payment_assets:
        plans = [
            {key: value for key, value in plan.items() if key not in {"alipay_qr_url", "wechat_qr_url"}}
            for plan in plans
        ]
    return {
        "plans": plans,
        "checkout": membership_checkout_config(),
    }


def public_credit_catalog(*, include_payment_assets: bool = False) -> dict[str, Any]:
    catalog = {
        "checkout": credit_checkout_config(),
        "pricing": {
            "unit_price_cents": 100,
            "currency": "CNY",
        },
        "rules": {
            "min_credits": 1,
            "max_credits": 10000,
            "price_text": "1 元 / 次",
            "support_text": "人工核款，确认后到账；退款、发票请联系人工客服处理。",
        },
    }
    if include_payment_assets:
        catalog["payment_assets"] = {
            "alipay_qr_url": _payment_qr_data_uri("PAYMENT_ALIPAY_QR_FILE", "alipay-qr.jpg"),
            "wechat_qr_url": _payment_qr_data_uri("PAYMENT_WECHAT_QR_FILE", "wechat-qr.jpg"),
        }
    return catalog


def _normalize_credit_purchase_quantity(credits: int) -> int:
    if isinstance(credits, bool) or not isinstance(credits, int):
        raise AuthError("购买次数必须是正整数", 400)
    if credits <= 0:
        raise AuthError("购买次数必须是正整数", 400)
    if credits > 10000:
        raise AuthError("单次购买次数过大，请拆分后重试", 400)
    return credits


def create_order(db_path: Path, *, user_id: int, plan_name: str = "", credits: int = 0, amount_cents: int = 0, package_id: str = "") -> dict[str, Any]:
    package_id = (package_id or "").strip()
    if package_id:
        package = CREDIT_PACKAGES.get(package_id)
        if not package:
            raise AuthError("未知的次数包", 400)
        plan_name = str(package["plan_name"])
        credits = int(package["credits"])
        amount_cents = int(package["amount_cents"])
    if credits <= 0 or amount_cents < 0:
        raise AuthError("订单参数不正确", 400)
    order_no = f"YT{datetime.now(CN_TZ).strftime('%Y%m%d%H%M%S')}{secrets.token_hex(3).upper()}"
    now = _now()
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO orders (user_id, order_no, plan_name, credits, amount_cents, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, order_no, plan_name.strip()[:60] or "次数包", credits, amount_cents, now),
        )
        return _order_payload(conn.execute("SELECT * FROM orders WHERE id = ?", (cursor.lastrowid,)).fetchone())


def create_credit_order(db_path: Path, *, user_id: int, credits: int) -> dict[str, Any]:
    credits = _normalize_credit_purchase_quantity(credits)
    order_no = f"YC{datetime.now(CN_TZ).strftime('%Y%m%d%H%M%S')}{secrets.token_hex(3).upper()}"
    now = _now()
    with _connect(db_path) as conn:
        _require_manageable_user(conn, user_id)
        cursor = conn.execute(
            """
            INSERT INTO orders (
                user_id, order_no, plan_name, credits, amount_cents, status, created_at,
                product_type, package_id, payment_submit_status
            )
            VALUES (?, ?, ?, ?, ?, 'pending', ?, 'credits', '', 'none')
            """,
            (user_id, order_no, f"{credits} 次使用", credits, credits * 100, now),
        )
        return _order_payload(conn.execute("SELECT * FROM orders WHERE id = ?", (cursor.lastrowid,)).fetchone())


def create_membership_order(db_path: Path, *, user_id: int, plan_id: str = "monthly_membership") -> dict[str, Any]:
    plan = _membership_plan(plan_id)
    order_no = f"YM{datetime.now(CN_TZ).strftime('%Y%m%d%H%M%S')}{secrets.token_hex(3).upper()}"
    now = _now()
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO orders (
                user_id, order_no, plan_name, credits, amount_cents, status, created_at,
                product_type, package_id, duration_days, payment_submit_status
            )
            VALUES (?, ?, ?, 0, ?, 'pending', ?, 'membership', ?, ?, 'none')
            """,
            (user_id, order_no, plan["plan_name"], int(plan["amount_cents"]), now, plan["id"], int(plan["duration_days"])),
        )
        return _order_payload(conn.execute("SELECT * FROM orders WHERE id = ?", (cursor.lastrowid,)).fetchone())


def latest_membership_order(db_path: Path, *, user_id: int) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM orders
            WHERE user_id = ? AND COALESCE(product_type, '') = 'membership'
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        return _order_payload(row) if row else None


def latest_credit_order(db_path: Path, *, user_id: int) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM orders
            WHERE user_id = ? AND COALESCE(product_type, 'credits') = 'credits'
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        return _order_payload(row) if row else None


def get_order(db_path: Path, *, order_id: int, user_id: int | None = None, admin: bool = False) -> dict[str, Any]:
    with _connect(db_path) as conn:
        if admin:
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        else:
            row = conn.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, user_id)).fetchone()
        if not row:
            raise AuthError("订单不存在", 404)
        return _order_payload(row)


def submit_membership_payment(
    db_path: Path,
    *,
    order_id: int,
    user_id: int,
    payment_method: str,
    payer_name: str,
    payer_paid_at: str,
    submitted_amount_cents: int,
    payer_note: str = "",
) -> dict[str, Any]:
    payment_method = _normalize_payment_method(payment_method)
    payer_name = (payer_name or "").strip()[:80]
    payer_note = (payer_note or "").strip()[:240]
    payer_paid_at = (payer_paid_at or "").strip()[:60]
    submitted_amount_cents = int(submitted_amount_cents or 0)
    if not payer_name:
        raise AuthError("请填写付款人昵称或姓名", 400)
    if not payer_paid_at:
        raise AuthError("请填写付款时间", 400)
    if submitted_amount_cents <= 0:
        raise AuthError("请填写实付金额", 400)
    now = _now()
    notify_result: dict[str, Any]
    with _connect(db_path) as conn:
        order = conn.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, user_id)).fetchone()
        if not order:
            raise AuthError("订单不存在", 404)
        if (order["product_type"] if "product_type" in order.keys() else "") != "membership":
            raise AuthError("该订单不是会员订单", 400)
        if order["status"] == "paid":
            raise AuthError("该订单已开通，无需重复提交", 409)
        if int(order["amount_cents"]) != submitted_amount_cents:
            raise AuthError("实付金额与订单金额不一致，请核对后再提交", 400)
        conn.execute(
            """
            UPDATE orders
            SET status = 'submitted',
                payment_method = ?,
                payment_submit_status = 'submitted',
                payer_name = ?,
                payer_note = ?,
                payer_paid_at = ?,
                submitted_amount_cents = ?,
                submitted_at = ?,
                rejected_at = NULL
            WHERE id = ?
            """,
            (payment_method, payer_name, payer_note, payer_paid_at, submitted_amount_cents, now, order_id),
        )
        updated = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        user = _fetch_user_by_id(conn, user_id)
        order_payload = _order_payload(updated)
        user_payload = _user_payload(conn, user)
    notify_result = notify_admin_membership_payment(order=order_payload, user=user_payload)
    order_payload["admin_notification"] = notify_result
    return order_payload


def confirm_membership_order(db_path: Path, *, order_id: int, admin_id: int, admin_note: str = "") -> dict[str, Any]:
    now_dt = datetime.now(CN_TZ)
    now = now_dt.isoformat()
    admin_note = (admin_note or "").strip()[:300]
    with _connect(db_path) as conn:
        # Serialize entitlement delivery so double-clicks and concurrent admin retries
        # cannot create duplicate membership ledger rows.
        conn.execute("BEGIN IMMEDIATE")
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order:
            raise AuthError("订单不存在", 404)
        if (order["product_type"] if "product_type" in order.keys() else "") != "membership":
            raise AuthError("该订单不是会员订单", 400)
        if order["status"] == "paid":
            return _order_payload(order)
        if order["status"] != "submitted":
            raise AuthError("用户尚未提交付款信息，不能确认开通", 400)
        user = _fetch_user_by_id(conn, int(order["user_id"]))
        start_dt = now_dt
        current_expiry = str(user["membership_expires_at"] if "membership_expires_at" in user.keys() else "").strip()
        if current_expiry:
            try:
                parsed = datetime.fromisoformat(current_expiry)
                if parsed > start_dt:
                    start_dt = parsed
            except ValueError:
                start_dt = now_dt
        duration_days = int(order["duration_days"] if "duration_days" in order.keys() and order["duration_days"] else _membership_plan()["duration_days"])
        expires_dt = start_dt + timedelta(days=duration_days)
        updated_order_count = conn.execute(
            """
            UPDATE orders
            SET status = 'paid',
                paid_at = ?,
                confirmed_at = ?,
                admin_id = ?,
                admin_note = ?
            WHERE id = ? AND status = 'submitted'
            """,
            (now, now, admin_id, admin_note, order_id),
        ).rowcount
        if updated_order_count != 1:
            refreshed_order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if refreshed_order and refreshed_order["status"] == "paid":
                return _order_payload(refreshed_order)
            raise AuthError("订单状态已变化，请刷新后重试", 409)
        conn.execute(
            """
            UPDATE users
            SET membership_plan = ?,
                membership_status = 'active',
                membership_expires_at = ?
            WHERE id = ?
            """,
            (order["plan_name"], expires_dt.isoformat(), int(order["user_id"])),
        )
        conn.execute(
            """
            INSERT INTO membership_ledger (user_id, order_id, plan_name, started_at, expires_at, created_at, admin_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (int(order["user_id"]), order_id, order["plan_name"], start_dt.isoformat(), expires_dt.isoformat(), now, admin_id),
        )
        updated = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return _order_payload(updated)


def reject_membership_order(db_path: Path, *, order_id: int, admin_id: int, admin_note: str = "") -> dict[str, Any]:
    admin_note = (admin_note or "").strip()[:300]
    if len(admin_note) < 2:
        raise AuthError("请填写驳回或异常原因", 400)
    now = _now()
    with _connect(db_path) as conn:
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order:
            raise AuthError("订单不存在", 404)
        if (order["product_type"] if "product_type" in order.keys() else "") != "membership":
            raise AuthError("该订单不是会员订单", 400)
        if order["status"] == "paid":
            raise AuthError("已开通订单不能驳回", 409)
        conn.execute(
            """
            UPDATE orders
            SET status = 'rejected',
                rejected_at = ?,
                admin_id = ?,
                admin_note = ?
            WHERE id = ?
            """,
            (now, admin_id, admin_note, order_id),
        )
        updated = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return _order_payload(updated)



def submit_credit_payment(
    db_path: Path,
    *,
    order_id: int,
    user_id: int,
    payment_method: str,
    payer_name: str,
    payer_paid_at: str,
    submitted_amount_cents: int,
    payer_note: str = "",
) -> dict[str, Any]:
    payment_method = _normalize_payment_method(payment_method)
    payer_name = (payer_name or "").strip()[:80]
    payer_note = (payer_note or "").strip()[:240]
    payer_paid_at = (payer_paid_at or "").strip()[:60]
    if isinstance(submitted_amount_cents, bool) or not isinstance(submitted_amount_cents, int):
        raise AuthError("实付金额格式不正确", 400)
    if not payer_name:
        raise AuthError("请填写付款人昵称或姓名", 400)
    if not payer_paid_at:
        raise AuthError("请填写付款时间", 400)
    if submitted_amount_cents <= 0:
        raise AuthError("请填写实付金额", 400)
    now = _now()
    notify_result: dict[str, Any]
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        order = conn.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, user_id)).fetchone()
        if not order:
            raise AuthError("订单不存在", 404)
        if (order["product_type"] if "product_type" in order.keys() else "credits") != "credits":
            raise AuthError("该订单不是次数订单", 400)
        _require_manageable_user(conn, int(order["user_id"]))
        if order["status"] == "paid":
            raise AuthError("该订单已到账，无需重复提交", 409)
        if order["status"] not in {"pending", "rejected"}:
            raise AuthError("付款信息已提交，请等待管理员核款", 409)
        if int(order["amount_cents"]) != submitted_amount_cents:
            raise AuthError("实付金额与订单金额不一致，请核对后再提交", 400)
        updated_count = conn.execute(
            """
            UPDATE orders
            SET status = 'submitted',
                payment_method = ?,
                payment_submit_status = 'submitted',
                payer_name = ?,
                payer_note = ?,
                payer_paid_at = ?,
                submitted_amount_cents = ?,
                submitted_at = ?,
                rejected_at = NULL,
                admin_note = ''
            WHERE id = ? AND status IN ('pending', 'rejected')
            """,
            (payment_method, payer_name, payer_note, payer_paid_at, submitted_amount_cents, now, order_id),
        ).rowcount
        if updated_count != 1:
            raise AuthError("订单状态已变化，请刷新后重试", 409)
        updated = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        user = _fetch_user_by_id(conn, user_id)
        order_payload = _order_payload(updated)
        user_payload = _user_payload(conn, user)
    notify_result = notify_admin_credit_payment(order=order_payload, user=user_payload)
    order_payload["admin_notification"] = notify_result
    return order_payload


def _grant_order_credits_once(conn: sqlite3.Connection, *, user_id: int, order_id: int, credits: int) -> None:
    existing = conn.execute(
        """
        SELECT id
        FROM credit_ledger
        WHERE user_id = ? AND reason = 'order_paid' AND related_id = ?
        LIMIT 1
        """,
        (user_id, str(order_id)),
    ).fetchone()
    if existing:
        return
    _add_credits(conn, user_id, credits, "order_paid", str(order_id))


def confirm_credit_order(db_path: Path, *, order_id: int, admin_id: int, admin_note: str = "") -> dict[str, Any]:
    now = _now()
    admin_note = (admin_note or "").strip()[:300]
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order:
            raise AuthError("订单不存在", 404)
        if (order["product_type"] if "product_type" in order.keys() else "credits") != "credits":
            raise AuthError("该订单不是次数订单", 400)
        _require_manageable_user(conn, int(order["user_id"]))
        if order["status"] == "paid":
            return _order_payload(order)
        if order["status"] != "submitted":
            raise AuthError("用户尚未提交付款信息，不能确认到账", 400)
        updated_order_count = conn.execute(
            """
            UPDATE orders
            SET status = 'paid',
                paid_at = ?,
                confirmed_at = ?,
                admin_id = ?,
                admin_note = ?
            WHERE id = ? AND status = 'submitted'
            """,
            (now, now, admin_id, admin_note, order_id),
        ).rowcount
        if updated_order_count != 1:
            refreshed_order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if refreshed_order and refreshed_order["status"] == "paid":
                return _order_payload(refreshed_order)
            raise AuthError("订单状态已变化，请刷新后重试", 409)
        _grant_order_credits_once(
            conn,
            user_id=int(order["user_id"]),
            order_id=order_id,
            credits=int(order["credits"]),
        )
        updated = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return _order_payload(updated)


def reject_credit_order(db_path: Path, *, order_id: int, admin_id: int, admin_note: str = "") -> dict[str, Any]:
    admin_note = (admin_note or "").strip()[:300]
    if len(admin_note) < 2:
        raise AuthError("请填写驳回或异常原因", 400)
    now = _now()
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order:
            raise AuthError("订单不存在", 404)
        if (order["product_type"] if "product_type" in order.keys() else "credits") != "credits":
            raise AuthError("该订单不是次数订单", 400)
        if order["status"] == "paid":
            raise AuthError("已到账订单不能驳回", 409)
        if order["status"] != "submitted":
            raise AuthError("只有待核款订单可以驳回", 400)
        updated_count = conn.execute(
            """
            UPDATE orders
            SET status = 'rejected',
                rejected_at = ?,
                admin_id = ?,
                admin_note = ?
            WHERE id = ? AND status = 'submitted'
            """,
            (now, admin_id, admin_note, order_id),
        ).rowcount
        if updated_count != 1:
            raise AuthError("订单状态已变化，请刷新后重试", 409)
        updated = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return _order_payload(updated)


def get_order_by_order_no(db_path: Path, *, order_no: str) -> dict[str, Any]:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_no = ?", (order_no,)).fetchone()
        if not row:
            raise AuthError("订单不存在", 404)
        return _order_payload(row)


def admin_dashboard(db_path: Path, days: int = 14) -> dict[str, Any]:
    days = max(1, min(90, int(days or 14)))
    end_day = datetime.now(CN_TZ).date()
    start_day = end_day - timedelta(days=days - 1)
    start_date = start_day.isoformat()
    end_date = end_day.isoformat()
    end_exclusive = (end_day + timedelta(days=1)).isoformat()
    date_keys = [(start_day + timedelta(days=offset)).isoformat() for offset in range(days)]
    with _connect(db_path) as conn:
        totals = {
            "users": conn.execute("SELECT COUNT(*) AS count FROM users WHERE role = 'user'").fetchone()["count"],
            "credits": conn.execute("SELECT COALESCE(SUM(delta), 0) AS count FROM credit_ledger").fetchone()["count"],
            "feedback_pending": conn.execute("SELECT COUNT(*) AS count FROM feedback WHERE status = 'pending'").fetchone()["count"],
            "orders_paid": conn.execute("SELECT COUNT(*) AS count FROM orders WHERE status = 'paid'").fetchone()["count"],
        }
        usage_rows = conn.execute(
            """
            SELECT substr(created_at, 1, 10) AS day, feature, COUNT(*) AS count, COALESCE(SUM(credits_spent), 0) AS credits
            FROM usage_events
            WHERE created_at >= ?
            GROUP BY day, feature
            ORDER BY day ASC
            """,
            (start_date,),
        ).fetchall()
        user_rows = conn.execute(
            """
            SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS count
            FROM users
            WHERE role = 'user' AND created_at >= ?
            GROUP BY day
            ORDER BY day ASC
            """,
            (start_date,),
        ).fetchall()
        feedback_rows = conn.execute(
            """
            SELECT f.*, u.phone
            FROM feedback f
            JOIN users u ON u.id = f.user_id
            ORDER BY f.created_at DESC
            LIMIT 50
            """
        ).fetchall()
        orders = conn.execute(
            """
            SELECT o.*, u.phone, u.username, u.email
            FROM orders o
            JOIN users u ON u.id = o.user_id
            ORDER BY o.created_at DESC
            LIMIT 50
            """
        ).fetchall()
        managed_users = conn.execute(
            """
            SELECT u.id, u.phone, u.username, u.email, u.role, u.status, u.created_at, u.last_login_at,
                   COALESCE(SUM(e.credits_spent), 0) AS used_count,
                   COALESCE((SELECT SUM(delta) FROM credit_ledger c WHERE c.user_id = u.id), 0) AS credits
            FROM users u
            LEFT JOIN usage_events e ON e.user_id = u.id
            WHERE u.role = 'user'
            GROUP BY u.id
            ORDER BY u.created_at DESC, u.id DESC
            """
        ).fetchall()
        top_users = conn.execute(
            """
            SELECT u.id, u.phone, u.username, u.email, u.role, u.created_at, COALESCE(SUM(e.credits_spent), 0) AS used_count,
                   (SELECT COALESCE(SUM(delta), 0) FROM credit_ledger c WHERE c.user_id = u.id) AS credits
            FROM users u
            LEFT JOIN usage_events e ON e.user_id = u.id
            GROUP BY u.id
            ORDER BY used_count DESC, u.created_at DESC
            LIMIT 30
            """
        ).fetchall()

        # Analytics intentionally count successful end-user usage only.  Legacy
        # fields above retain their original semantics for existing clients.
        successful_statuses = ("charged", "membership_free")
        feature_rows = conn.execute(
            """
            WITH successful_events AS (
                SELECT user_id, feature, credits_spent, related_id, created_at
                FROM (
                    SELECT e.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY e.user_id, e.feature,
                                   CASE
                                       WHEN TRIM(COALESCE(e.related_id, '')) = '' THEN printf('event:%d', e.id)
                                       ELSE 'related:' || e.related_id
                                   END
                               ORDER BY e.created_at ASC, e.id ASC
                           ) AS use_rank
                    FROM usage_events e
                    WHERE e.status IN (?, ?)
                )
                WHERE use_rank = 1
                  AND created_at >= ?
                  AND created_at < ?
            )
            SELECT substr(e.created_at, 1, 10) AS day,
                   e.feature,
                   COUNT(*) AS count,
                   COALESCE(SUM(e.credits_spent), 0) AS credits
            FROM successful_events e
            JOIN users u ON u.id = e.user_id
            WHERE u.role = 'user'
            GROUP BY day, e.feature
            ORDER BY day ASC, e.feature ASC
            """,
            (*successful_statuses, start_date, end_exclusive),
        ).fetchall()
        feature_lookup = {
            (str(row["day"]), str(row["feature"])): {
                "count": int(row["count"]),
                "credits": int(row["credits"]),
            }
            for row in feature_rows
        }
        # Keep all product features visible even when a feature has no usage in
        # the selected window. Dict insertion order is the product's canonical
        # display order and therefore makes the payload deterministic.
        observed_features = list(FEATURE_CREDIT_COSTS)
        feature_by_day = [
            {
                "day": day,
                "feature": feature,
                **feature_lookup.get((day, feature), {"count": 0, "credits": 0}),
            }
            for day in date_keys
            for feature in observed_features
        ]
        feature_totals_unsorted = [
            {
                "feature": feature,
                "count": sum(feature_lookup.get((day, feature), {"count": 0})["count"] for day in date_keys),
                "credits": sum(feature_lookup.get((day, feature), {"credits": 0})["credits"] for day in date_keys),
            }
            for feature in observed_features
        ]
        total_feature_uses = sum(item["count"] for item in feature_totals_unsorted)
        feature_totals = [
            item | {"share": round(item["count"] / total_feature_uses, 4) if total_feature_uses else 0.0}
            for item in feature_totals_unsorted
        ]

        starting_users = int(
            conn.execute(
                "SELECT COUNT(*) AS count FROM users WHERE role = 'user' AND created_at < ?",
                (start_date,),
            ).fetchone()["count"]
        )
        growth_rows = conn.execute(
            """
            SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS count
            FROM users
            WHERE role = 'user'
              AND created_at >= ?
              AND created_at < ?
            GROUP BY day
            ORDER BY day ASC
            """,
            (start_date, end_exclusive),
        ).fetchall()
        new_user_lookup = {str(row["day"]): int(row["count"]) for row in growth_rows}
        cumulative_users = starting_users
        growth_by_day: list[dict[str, Any]] = []
        for day in date_keys:
            new_users = new_user_lookup.get(day, 0)
            cumulative_users += new_users
            growth_by_day.append(
                {"day": day, "new_users": new_users, "cumulative_users": cumulative_users}
            )

        frequent_rows = conn.execute(
            """
            WITH successful_events AS (
                SELECT user_id, feature, credits_spent, related_id, created_at
                FROM (
                    SELECT e.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY e.user_id, e.feature,
                                   CASE
                                       WHEN TRIM(COALESCE(e.related_id, '')) = '' THEN printf('event:%d', e.id)
                                       ELSE 'related:' || e.related_id
                                   END
                               ORDER BY e.created_at ASC, e.id ASC
                           ) AS use_rank
                    FROM usage_events e
                    WHERE e.status IN (?, ?)
                )
                WHERE use_rank = 1
                  AND created_at >= ?
                  AND created_at < ?
            )
            SELECT u.id, u.phone, u.username, u.email,
                   COUNT(*) AS total_uses,
                   COALESCE(SUM(e.credits_spent), 0) AS credits_spent,
                   COUNT(DISTINCT substr(e.created_at, 1, 10)) AS active_days,
                   MAX(e.created_at) AS last_used_at
            FROM successful_events e
            JOIN users u ON u.id = e.user_id
            WHERE u.role = 'user'
            GROUP BY u.id
            ORDER BY total_uses DESC, active_days DESC, last_used_at DESC, u.id ASC
            LIMIT 5
            """,
            (*successful_statuses, start_date, end_exclusive),
        ).fetchall()
        frequent_user_ids = [int(row["id"]) for row in frequent_rows]
        frequent_usage_lookup: dict[tuple[int, str], dict[str, int]] = {}
        if frequent_user_ids:
            placeholders = ",".join("?" for _ in frequent_user_ids)
            daily_rows = conn.execute(
                f"""
                WITH successful_events AS (
                    SELECT user_id, feature, credits_spent, related_id, created_at
                    FROM (
                        SELECT e.*,
                               ROW_NUMBER() OVER (
                                   PARTITION BY e.user_id, e.feature,
                                       CASE
                                           WHEN TRIM(COALESCE(e.related_id, '')) = '' THEN printf('event:%d', e.id)
                                           ELSE 'related:' || e.related_id
                                       END
                                   ORDER BY e.created_at ASC, e.id ASC
                               ) AS use_rank
                        FROM usage_events e
                        WHERE e.status IN (?, ?)
                    )
                    WHERE use_rank = 1
                      AND created_at >= ?
                      AND created_at < ?
                )
                SELECT e.user_id, substr(e.created_at, 1, 10) AS day,
                       COUNT(*) AS count,
                       COALESCE(SUM(e.credits_spent), 0) AS credits
                FROM successful_events e
                JOIN users u ON u.id = e.user_id
                WHERE u.role = 'user'
                  AND e.user_id IN ({placeholders})
                GROUP BY e.user_id, day
                ORDER BY e.user_id ASC, day ASC
                """,
                (*successful_statuses, start_date, end_exclusive, *frequent_user_ids),
            ).fetchall()
            frequent_usage_lookup = {
                (int(row["user_id"]), str(row["day"])): {
                    "count": int(row["count"]),
                    "credits": int(row["credits"]),
                }
                for row in daily_rows
            }
        high_frequency_users = [
            {
                "id": int(row["id"]),
                "phone": row["phone"],
                "username": row["username"],
                "email": row["email"],
                "total_uses": int(row["total_uses"]),
                "credits_spent": int(row["credits_spent"]),
                "active_days": int(row["active_days"]),
                "usage_by_day": [
                    {
                        "day": day,
                        **frequent_usage_lookup.get((int(row["id"]), day), {"count": 0, "credits": 0}),
                    }
                    for day in date_keys
                ],
            }
            for row in frequent_rows
        ]
        recent_usage_rows = conn.execute(
            """
            WITH ranked_events AS (
                SELECT e.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY e.user_id, e.feature,
                               CASE
                                   WHEN TRIM(COALESCE(e.related_id, '')) = '' THEN printf('event:%d', e.id)
                                   ELSE 'related:' || e.related_id
                               END
                           ORDER BY e.created_at ASC, e.id ASC
                       ) AS use_rank
                FROM usage_events e
                WHERE e.status IN (?, ?)
            )
            SELECT e.id, e.user_id, e.feature, e.credits_spent, e.status,
                   e.related_id, e.created_at,
                   u.username, u.email, u.phone
            FROM ranked_events e
            JOIN users u ON u.id = e.user_id
            WHERE e.use_rank = 1
              AND u.role = 'user'
              AND e.created_at >= ?
              AND e.created_at < ?
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT 200
            """,
            (*successful_statuses, start_date, end_exclusive),
        ).fetchall()
        recent_usage_events = []
        for row in recent_usage_rows:
            created_at = str(row["created_at"] or "")
            time_text = created_at[11:19] if len(created_at) >= 19 else ""
            feature = str(row["feature"] or "")
            username = str(row["username"] or "").strip()
            email = str(row["email"] or "").strip()
            phone = str(row["phone"] or "").strip()
            recent_usage_events.append(
                {
                    "id": int(row["id"]),
                    "user_id": int(row["user_id"]),
                    "username": username,
                    "email": email,
                    "phone": phone,
                    "display_name": username or email or phone or f"用户 {int(row['user_id'])}",
                    "feature": feature,
                    "credits_spent": int(row["credits_spent"] or 0),
                    "status": str(row["status"] or ""),
                    "related_id": str(row["related_id"] or ""),
                    "used_at": created_at,
                    "market_session": (
                        "before_open" if time_text and time_text < "09:30:00" else "after_open"
                    ) if feature == "auction_strength_view" else None,
                }
            )
        daily_top5_campaign_rows = conn.execute(
            "SELECT id FROM daily_top5_email_campaigns ORDER BY trade_date DESC, id DESC LIMIT 20"
        ).fetchall()
        daily_top5_email_campaigns = [
            _daily_top5_email_campaign_payload(conn, int(row["id"]))
            for row in daily_top5_campaign_rows
        ]
        daily_top5_email_failed_count = int(
            conn.execute(
                "SELECT COUNT(*) AS count FROM daily_top5_email_deliveries WHERE status = 'failed'"
            ).fetchone()["count"]
        )
        daily_top5_close_campaign_rows = conn.execute(
            "SELECT id FROM daily_top5_close_email_campaigns ORDER BY trade_date DESC, id DESC LIMIT 20"
        ).fetchall()
        daily_top5_close_email_campaigns = [
            _daily_top5_close_email_campaign_payload(conn, int(row["id"]))
            for row in daily_top5_close_campaign_rows
        ]
        daily_top5_close_email_failed_count = int(
            conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM daily_top5_close_email_campaigns
                WHERE status IN ('failed', 'partial_failed')
                   OR calculation_status = 'failed'
                """
            ).fetchone()["count"]
        )
        ai_report_campaign_rows = conn.execute(
            "SELECT id FROM ai_report_email_campaigns ORDER BY report_date DESC, id DESC LIMIT 30"
        ).fetchall()
        ai_report_email_campaigns = [
            _ai_report_email_campaign_payload(conn, int(row["id"]))
            for row in ai_report_campaign_rows
        ]
        ai_report_email_failed_count = int(
            conn.execute(
                "SELECT COUNT(*) AS count FROM ai_report_email_deliveries WHERE status = 'failed'"
            ).fetchone()["count"]
        )
        return {
            "totals": totals,
            "usage_by_day": [dict(row) for row in usage_rows],
            "new_users_by_day": [dict(row) for row in user_rows],
            "feedback": [_feedback_payload(row) for row in feedback_rows],
            "orders": [_order_payload(row) | {"phone": row["phone"], "username": row["username"], "email": row["email"]} for row in orders],
            "managed_users": [dict(row) for row in managed_users],
            "top_users": [dict(row) for row in top_users],
            "analytics": {
                "window": {"days": days, "start_date": start_date, "end_date": end_date},
                "feature_usage": {"totals": feature_totals, "by_day": feature_by_day},
                "user_growth": {
                    "starting_users": starting_users,
                    "total_users": cumulative_users,
                    "by_day": growth_by_day,
                },
                "high_frequency_users": high_frequency_users,
                "recent_usage_events": recent_usage_events,
            },
            "credit_grant_campaigns": [
                _credit_grant_campaign_payload(row)
                for row in conn.execute(
                    "SELECT * FROM credit_grant_campaigns ORDER BY id DESC LIMIT 20"
                ).fetchall()
            ],
            "update_notices": [_update_notice_payload(row, conn=conn) for row in _update_notice_rows(conn)],
            "daily_top5_email_campaigns": daily_top5_email_campaigns,
            "daily_top5_email_failed_count": daily_top5_email_failed_count,
            "daily_top5_close_email_campaigns": daily_top5_close_email_campaigns,
            "daily_top5_close_email_failed_count": daily_top5_close_email_failed_count,
            "ai_report_email_campaigns": ai_report_email_campaigns,
            "ai_report_email_failed_count": ai_report_email_failed_count,
        }


def list_admin_users(
    db_path: Path,
    *,
    query: str = "",
    status: str = "all",
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    normalized_status = _normalize_admin_choice(status, allowed={"all", "active", "disabled"})
    normalized_query = _normalize_admin_query(query)
    page = _normalize_admin_page(page)
    page_size = _normalize_admin_page_size(page_size, default=25, maximum=100)
    where = ["u.role = 'user'"]
    params: list[Any] = []
    if normalized_status != "all":
        where.append("u.status = ?")
        params.append(normalized_status)
    if normalized_query:
        like = _admin_like(normalized_query)
        where.append(
            "("
            "LOWER(COALESCE(u.username, '')) LIKE ? OR "
            "LOWER(COALESCE(u.email, '')) LIKE ? OR "
            "LOWER(COALESCE(u.phone, '')) LIKE ? OR "
            "CAST(u.id AS TEXT) = ?"
            ")"
        )
        params.extend([like, like, like, normalized_query])
    where_sql = " AND ".join(where)
    offset = (page - 1) * page_size
    with _connect(db_path) as conn:
        total = int(
            conn.execute(f"SELECT COUNT(*) AS count FROM users u WHERE {where_sql}", tuple(params)).fetchone()["count"]
        )
        rows = conn.execute(
            f"""
            SELECT u.id, u.phone, u.username, u.email, u.role, u.status, u.created_at, u.last_login_at,
                   COALESCE(usage.used_count, 0) AS used_count,
                   COALESCE(ledger.credits, 0) AS credits
            FROM users u
            LEFT JOIN (
                SELECT user_id, COALESCE(SUM(credits_spent), 0) AS used_count
                FROM usage_events
                GROUP BY user_id
            ) usage ON usage.user_id = u.id
            LEFT JOIN (
                SELECT user_id, COALESCE(SUM(delta), 0) AS credits
                FROM credit_ledger
                GROUP BY user_id
            ) ledger ON ledger.user_id = u.id
            WHERE {where_sql}
            ORDER BY u.created_at DESC, u.id DESC
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, offset),
        ).fetchall()
        campaigns = [
            _credit_grant_campaign_payload(row)
            for row in conn.execute(
                "SELECT * FROM credit_grant_campaigns ORDER BY id DESC LIMIT 5"
            ).fetchall()
        ]
        return {
            **_admin_page_payload(page=page, page_size=page_size, total=total),
            "items": [dict(row) for row in rows],
            "campaigns": campaigns,
            "filters": {"query": normalized_query, "status": normalized_status},
        }


def list_admin_orders(
    db_path: Path,
    *,
    query: str = "",
    status: str = "all",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    normalized_status = _normalize_admin_choice(status, allowed={"all", "pending", "submitted", "paid", "rejected"})
    normalized_query = _normalize_admin_query(query)
    page = _normalize_admin_page(page)
    page_size = _normalize_admin_page_size(page_size, default=20, maximum=100)
    where = ["1 = 1"]
    params: list[Any] = []
    if normalized_status != "all":
        where.append("o.status = ?")
        params.append(normalized_status)
    if normalized_query:
        like = _admin_like(normalized_query)
        where.append(
            "("
            "LOWER(COALESCE(o.order_no, '')) LIKE ? OR "
            "LOWER(COALESCE(o.plan_name, '')) LIKE ? OR "
            "LOWER(COALESCE(u.username, '')) LIKE ? OR "
            "LOWER(COALESCE(u.email, '')) LIKE ? OR "
            "LOWER(COALESCE(u.phone, '')) LIKE ?"
            ")"
        )
        params.extend([like, like, like, like, like])
    where_sql = " AND ".join(where)
    offset = (page - 1) * page_size
    with _connect(db_path) as conn:
        total = int(
            conn.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM orders o
                JOIN users u ON u.id = o.user_id
                WHERE {where_sql}
                """,
                tuple(params),
            ).fetchone()["count"]
        )
        rows = conn.execute(
            f"""
            SELECT o.*, u.phone, u.username, u.email
            FROM orders o
            JOIN users u ON u.id = o.user_id
            WHERE {where_sql}
            ORDER BY o.created_at DESC, o.id DESC
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, offset),
        ).fetchall()
        return {
            **_admin_page_payload(page=page, page_size=page_size, total=total),
            "items": [
                _order_payload(row)
                | {"phone": row["phone"], "username": row["username"], "email": row["email"]}
                for row in rows
            ],
            "filters": {"query": normalized_query, "status": normalized_status},
        }


def list_admin_feedback(
    db_path: Path,
    *,
    query: str = "",
    status: str = "all",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    normalized_status = _normalize_admin_choice(status, allowed={"all", "pending", "accepted", "rejected"})
    normalized_query = _normalize_admin_query(query)
    page = _normalize_admin_page(page)
    page_size = _normalize_admin_page_size(page_size, default=20, maximum=100)
    where = ["1 = 1"]
    params: list[Any] = []
    if normalized_status != "all":
        where.append("f.status = ?")
        params.append(normalized_status)
    if normalized_query:
        like = _admin_like(normalized_query)
        where.append(
            "("
            "LOWER(COALESCE(f.category, '')) LIKE ? OR "
            "LOWER(COALESCE(f.content, '')) LIKE ? OR "
            "LOWER(COALESCE(f.contact, '')) LIKE ? OR "
            "LOWER(COALESCE(u.phone, '')) LIKE ?"
            ")"
        )
        params.extend([like, like, like, like])
    where_sql = " AND ".join(where)
    offset = (page - 1) * page_size
    with _connect(db_path) as conn:
        total = int(
            conn.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM feedback f
                JOIN users u ON u.id = f.user_id
                WHERE {where_sql}
                """,
                tuple(params),
            ).fetchone()["count"]
        )
        rows = conn.execute(
            f"""
            SELECT f.*, u.phone
            FROM feedback f
            JOIN users u ON u.id = f.user_id
            WHERE {where_sql}
            ORDER BY f.created_at DESC, f.id DESC
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, offset),
        ).fetchall()
        return {
            **_admin_page_payload(page=page, page_size=page_size, total=total),
            "items": [_feedback_payload(row) for row in rows],
            "filters": {"query": normalized_query, "status": normalized_status},
        }


def list_admin_update_notices(
    db_path: Path,
    *,
    query: str = "",
    status: str = "all",
    page: int = 1,
    page_size: int = 12,
) -> dict[str, Any]:
    normalized_status = _normalize_admin_choice(status, allowed={"all", "draft", "published", "archived"})
    normalized_query = _normalize_admin_query(query)
    page = _normalize_admin_page(page)
    page_size = _normalize_admin_page_size(page_size, default=12, maximum=100)
    where = ["1 = 1"]
    params: list[Any] = []
    if normalized_status != "all":
        where.append("status = ?")
        params.append(normalized_status)
    if normalized_query:
        like = _admin_like(normalized_query)
        where.append(
            "("
            "LOWER(COALESCE(title, '')) LIKE ? OR "
            "LOWER(COALESCE(version, '')) LIKE ? OR "
            "LOWER(COALESCE(summary, '')) LIKE ?"
            ")"
        )
        params.extend([like, like, like])
    where_sql = " AND ".join(where)
    offset = (page - 1) * page_size
    with _connect(db_path) as conn:
        total = int(
            conn.execute(
                f"SELECT COUNT(*) AS count FROM update_notices WHERE {where_sql}",
                tuple(params),
            ).fetchone()["count"]
        )
        rows = conn.execute(
            f"""
            SELECT *
            FROM update_notices
            WHERE {where_sql}
            ORDER BY COALESCE(published_at, updated_at, created_at) DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, offset),
        ).fetchall()
        return {
            **_admin_page_payload(page=page, page_size=page_size, total=total),
            "items": [_update_notice_payload(row, conn=conn) for row in rows],
            "filters": {"query": normalized_query, "status": normalized_status},
        }


def list_admin_email_campaigns(
    db_path: Path,
    *,
    kind: str = "all",
    status: str = "all",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    normalized_kind = _normalize_admin_choice(
        kind,
        allowed={"all", "update_notice", "daily_top5", "daily_top5_close", "market_day", "ai_research"},
    )
    normalized_status = _normalize_admin_choice(
        status,
        allowed={"all", "pending", "sending", "completed", "partial_failed", "failed"},
    )
    normalized_date_from = _normalize_admin_date(date_from)
    normalized_date_to = _normalize_admin_date(date_to)
    page = _normalize_admin_page(page)
    page_size = _normalize_admin_page_size(page_size, default=20, maximum=100)
    with _connect(db_path) as conn:
        items: list[dict[str, Any]] = []
        for row in conn.execute(
            """
            SELECT c.id, n.title, n.version
            FROM update_email_campaigns c
            JOIN update_notices n ON n.id = c.notice_id
            ORDER BY c.created_at DESC, c.id DESC
            """
        ).fetchall():
            payload = _email_campaign_payload(conn, int(row["id"]))
            items.append(
                {
                    **payload,
                    "kind": "update_notice",
                    "title": str(row["title"] or "更新公告"),
                    "summary": str(row["version"] or ""),
                    "retry_type": "update_notice",
                }
            )
        for row in conn.execute(
            "SELECT id FROM daily_top5_email_campaigns ORDER BY created_at DESC, id DESC"
        ).fetchall():
            payload = _daily_top5_email_campaign_payload(conn, int(row["id"]))
            items.append(
                {
                    **payload,
                    "kind": "daily_top5",
                    "title": f"{payload['trade_date']} · 每日 TOP5",
                    "summary": f"完整版 {payload['full']} · 摘要版 {payload['teaser']}",
                    "retry_type": "daily_top5",
                }
            )
        for row in conn.execute(
            "SELECT id FROM daily_top5_close_email_campaigns ORDER BY created_at DESC, id DESC"
        ).fetchall():
            payload = _daily_top5_close_email_campaign_payload(conn, int(row["id"]))
            items.append(
                {
                    **payload,
                    "kind": "daily_top5_close",
                    "title": f"{payload['trade_date']} · 每日 TOP5 收盘表现",
                    "summary": payload.get("calculation_last_error") or f"完整版 {payload['full']} · 待发 {payload['pending']}",
                    "retry_type": "daily_top5_close",
                }
            )
        for row in conn.execute(
            "SELECT id FROM ai_report_email_campaigns ORDER BY created_at DESC, id DESC"
        ).fetchall():
            payload = _ai_report_email_campaign_payload(conn, int(row["id"]))
            kind_value = str(payload["report_type"] or "")
            items.append(
                {
                    **payload,
                    "kind": kind_value,
                    "title": (
                        f"{payload['report_date']} · 市场日报"
                        if kind_value == "market_day"
                        else f"{payload['report_date']} · AI 复盘"
                    ),
                    "summary": f"完整版 {payload['full']} · 摘要版 {payload['teaser']}",
                    "retry_type": "ai_report",
                }
            )
    filtered = [
        item
        for item in items
        if (normalized_kind == "all" or str(item.get("kind") or "") == normalized_kind)
        and (
            normalized_status == "all"
            or str(item.get("status") or "") == normalized_status
            or (normalized_status == "failed" and str(item.get("status") or "") == "partial_failed")
        )
        and (not normalized_date_from or str(item.get("created_at") or "")[:10] >= normalized_date_from)
        and (not normalized_date_to or str(item.get("created_at") or "")[:10] <= normalized_date_to)
    ]
    filtered.sort(key=lambda item: (str(item.get("created_at") or ""), int(item.get("id") or 0)), reverse=True)
    total = len(filtered)
    offset = (page - 1) * page_size
    delivery_totals = {
        key: sum(int(item.get(key) or 0) for item in filtered)
        for key in ("sent", "pending", "sending", "failed", "skipped")
    }
    return {
        **_admin_page_payload(page=page, page_size=page_size, total=total),
        "items": filtered[offset: offset + page_size],
        "delivery_totals": delivery_totals,
        "filters": {
            "kind": normalized_kind,
            "status": normalized_status,
            "date_from": normalized_date_from,
            "date_to": normalized_date_to,
        },
    }


def get_admin_email_campaign_detail(db_path: Path, *, kind: str, campaign_id: int) -> dict[str, Any]:
    normalized_kind = _normalize_admin_choice(
        kind,
        allowed={"update_notice", "daily_top5", "daily_top5_close", "market_day", "ai_research"},
    )
    if campaign_id <= 0:
        raise AuthError("邮件任务不存在", 404)
    if normalized_kind == "update_notice":
        campaign_table = "update_email_campaigns"
        delivery_table = "update_email_deliveries"
        payload_builder = _email_campaign_payload
    elif normalized_kind == "daily_top5":
        campaign_table = "daily_top5_email_campaigns"
        delivery_table = "daily_top5_email_deliveries"
        payload_builder = _daily_top5_email_campaign_payload
    elif normalized_kind == "daily_top5_close":
        campaign_table = "daily_top5_close_email_campaigns"
        delivery_table = "daily_top5_close_email_deliveries"
        payload_builder = _daily_top5_close_email_campaign_payload
    else:
        campaign_table = "ai_report_email_campaigns"
        delivery_table = "ai_report_email_deliveries"
        payload_builder = _ai_report_email_campaign_payload

    with _connect(db_path) as conn:
        campaign_row = conn.execute(
            f"SELECT id FROM {campaign_table} WHERE id = ?",
            (campaign_id,),
        ).fetchone()
        if not campaign_row:
            raise AuthError("邮件任务不存在", 404)
        campaign = payload_builder(conn, campaign_id)
        if normalized_kind in {"market_day", "ai_research"} and str(campaign.get("report_type") or "") != normalized_kind:
            raise AuthError("邮件任务不存在", 404)
        deliveries = [
            {
                "email": str(row["email"] or ""),
                "status": str(row["status"] or ""),
                "attempt_count": int(row["attempt_count"] or 0),
                "last_error": str(row["last_error"] or ""),
                "next_attempt_at": row["next_attempt_at"],
                "updated_at": row["updated_at"],
            }
            for row in conn.execute(
                f"""
                SELECT email, status, attempt_count, last_error, next_attempt_at, updated_at
                FROM {delivery_table}
                WHERE campaign_id = ? AND status = 'failed'
                ORDER BY updated_at DESC, id DESC
                """,
                (campaign_id,),
            ).fetchall()
        ]
        return {
            "kind": normalized_kind,
            **campaign,
            "campaign": campaign,
            "failed_deliveries": deliveries,
        }


def _admin_page_payload(*, page: int, page_size: int, total: int) -> dict[str, int]:
    total_pages = max(1, (int(total) + page_size - 1) // page_size)
    return {
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "total_pages": total_pages,
    }


def _normalize_admin_page(value: object) -> int:
    try:
        page = int(value or 1)
    except (TypeError, ValueError):
        page = 1
    return max(1, page)


def _normalize_admin_page_size(value: object, *, default: int, maximum: int) -> int:
    try:
        page_size = int(value or default)
    except (TypeError, ValueError):
        page_size = default
    return max(1, min(page_size, maximum))


def _normalize_admin_choice(value: object, *, allowed: set[str]) -> str:
    normalized = str(value or "").strip().lower() or "all"
    return normalized if normalized in allowed else "all"


def _normalize_admin_query(value: object) -> str:
    return str(value or "").strip().lower()[:120]


def _admin_like(value: str) -> str:
    return f"%{value.replace('%', '').replace('_', '')}%"


def _normalize_admin_date(value: object) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else ""


def latest_published_update_notice(db_path: Path) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM update_notices
            WHERE status = 'published'
            ORDER BY published_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        return _update_notice_payload(row) if row else None


def _latest_eligible_update_notice_row(
    conn: sqlite3.Connection, *, user_id: int, now: str | None = None
) -> sqlite3.Row | None:
    user = _fetch_user_by_id(conn, user_id)
    if str(user["role"] or "").strip() != "user":
        return None
    current_time = str(now or _now())
    registered_at = str(user["created_at"] or "").strip()
    return conn.execute(
        """
        SELECT n.*
        FROM update_notices n
        WHERE n.audience = 'registered_users'
          AND COALESCE(n.published_at, '') != ''
          AND n.published_at >= ?
          AND n.published_at <= ?
        ORDER BY n.published_at DESC, n.id DESC
        LIMIT 1
        """,
        (registered_at, current_time),
    ).fetchone()


def list_pending_update_notices(db_path: Path, *, user_id: int) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        now = _now()
        latest = _latest_eligible_update_notice_row(conn, user_id=user_id, now=now)
        if not latest:
            return []
        expires_at = str(latest["expires_at"] or "").strip()
        if str(latest["status"] or "") != "published" or (expires_at and expires_at <= now):
            return []
        acknowledged = conn.execute(
            """
            SELECT 1
            FROM update_notice_acknowledgements
            WHERE notice_id = ? AND user_id = ?
            LIMIT 1
            """,
            (int(latest["id"]), user_id),
        ).fetchone()
        return [] if acknowledged else [_update_notice_payload(latest)]


def acknowledge_update_notice(db_path: Path, *, notice_id: int, user_id: int) -> dict[str, Any]:
    now = _now()
    with _connect(db_path) as conn:
        latest = _latest_eligible_update_notice_row(conn, user_id=user_id, now=now)
        expires_at = str(latest["expires_at"] or "").strip() if latest else ""
        if (
            not latest
            or int(latest["id"]) != notice_id
            or str(latest["status"] or "") != "published"
            or (expires_at and expires_at <= now)
        ):
            raise AuthError("更新公告不存在或已下线", 404)
        conn.execute(
            """
            INSERT OR IGNORE INTO update_notice_acknowledgements (notice_id, user_id, acknowledged_at)
            VALUES (?, ?, ?)
            """,
            (notice_id, user_id, now),
        )
        ack = conn.execute(
            """
            SELECT notice_id, user_id, acknowledged_at
            FROM update_notice_acknowledgements
            WHERE notice_id = ? AND user_id = ?
            """,
            (notice_id, user_id),
        ).fetchone()
        return {
            "notice_id": int(ack["notice_id"]),
            "user_id": int(ack["user_id"]),
            "acknowledged_at": str(ack["acknowledged_at"]),
        }


def list_update_notices(db_path: Path, limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(100, int(limit or 20)))
    with _connect(db_path) as conn:
        return [_update_notice_payload(row, conn=conn) for row in _update_notice_rows(conn, limit=limit)]


def set_update_email_preference(db_path: Path, *, user_id: int, enabled: bool) -> dict[str, Any]:
    if type(enabled) is not bool:
        raise AuthError("update_emails_enabled 必须是布尔值", 400)
    with _connect(db_path) as conn:
        conn.execute("UPDATE users SET update_emails_enabled = ? WHERE id = ?", (1 if enabled else 0, user_id))
        return _user_payload(conn, _fetch_user_by_id(conn, user_id))


def create_update_notice(
    db_path: Path,
    *,
    title: str,
    version: str,
    items: list[Any],
    admin_id: int,
    summary: str = "",
    content_markdown: str = "",
    audience: str = "registered_users",
    expires_at: str = "",
    status: str = "draft",
) -> dict[str, Any]:
    title, version, items, summary, content_markdown, audience, expires_at, status = _normalize_update_notice_input(
        title,
        version,
        items,
        summary,
        content_markdown,
        audience,
        expires_at,
        status,
    )
    now = _now()
    published_at = now if status == "published" else None
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO update_notices (
                title, version, items_json, summary, content_markdown, status, audience,
                created_by, created_at, updated_at, published_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                version,
                json.dumps(items, ensure_ascii=False),
                summary,
                content_markdown,
                status,
                audience,
                admin_id,
                now,
                now,
                published_at,
                expires_at or None,
            ),
        )
        return _update_notice_payload(conn.execute("SELECT * FROM update_notices WHERE id = ?", (cursor.lastrowid,)).fetchone())


def update_update_notice(
    db_path: Path,
    *,
    notice_id: int,
    title: str,
    version: str,
    items: list[Any],
    summary: str = "",
    content_markdown: str = "",
    audience: str = "registered_users",
    expires_at: str = "",
) -> dict[str, Any]:
    title, version, items, summary, content_markdown, audience, expires_at, _ = _normalize_update_notice_input(
        title,
        version,
        items,
        summary,
        content_markdown,
        audience,
        expires_at,
        "draft",
    )
    with _connect(db_path) as conn:
        existing = conn.execute("SELECT * FROM update_notices WHERE id = ?", (notice_id,)).fetchone()
        if not existing:
            raise AuthError("更新公告不存在", 404)
        conn.execute(
            """
            UPDATE update_notices
            SET title = ?, version = ?, items_json = ?, summary = ?, content_markdown = ?,
                audience = ?, expires_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                title,
                version,
                json.dumps(items, ensure_ascii=False),
                summary,
                content_markdown,
                audience,
                expires_at or None,
                _now(),
                notice_id,
            ),
        )
        return _update_notice_payload(conn.execute("SELECT * FROM update_notices WHERE id = ?", (notice_id,)).fetchone())


def publish_update_notice(
    db_path: Path,
    *,
    notice_id: int,
    send_email: bool = False,
    request_id: str = "",
    admin_id: int | None = None,
) -> dict[str, Any]:
    if type(send_email) is not bool:
        raise AuthError("send_email 必须是布尔值", 400)
    request_id = str(request_id or "").strip()
    if send_email and not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request_id):
        raise AuthError("邮件推送 request_id 无效", 400)
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT * FROM update_notices WHERE id = ?", (notice_id,)).fetchone()
        if not existing:
            raise AuthError("更新公告不存在", 404)
        now = _now()
        conn.execute(
            """
            UPDATE update_notices
            SET status = 'published', published_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, notice_id),
        )
        campaign = None
        if send_email:
            campaign = _create_update_email_campaign(conn, notice_id=notice_id, request_id=request_id, admin_id=admin_id)
        notice = _update_notice_payload(conn.execute("SELECT * FROM update_notices WHERE id = ?", (notice_id,)).fetchone(), conn=conn)
        return {"notice": notice, "email_campaign": campaign}


def retry_update_email_campaign(db_path: Path, *, campaign_id: int) -> dict[str, Any]:
    with _connect(db_path) as conn:
        existing = conn.execute("SELECT id FROM update_email_campaigns WHERE id = ?", (campaign_id,)).fetchone()
        if not existing:
            raise AuthError("邮件推送任务不存在", 404)
        now = _now()
        cursor = conn.execute(
            """
            UPDATE update_email_deliveries
            SET status = 'pending', attempt_count = 0, next_attempt_at = ?, last_error = NULL, updated_at = ?
            WHERE campaign_id = ? AND status = 'failed'
            """,
            (now, now, campaign_id),
        )
        if cursor.rowcount:
            conn.execute("UPDATE update_email_campaigns SET status = 'pending', finished_at = NULL WHERE id = ?", (campaign_id,))
        return _email_campaign_payload(conn, campaign_id)


def create_daily_top5_email_campaign(db_path: Path, *, report: dict[str, Any]) -> dict[str, Any]:
    """Create an idempotent recipient snapshot for one complete trading-day report."""
    trade_date = str(report.get("trade_date") or "").strip()
    report_id = str(report.get("id") or report.get("request_id") or "").strip()
    strong_stocks = report.get("top5_strong_stocks")
    conclusion = report.get("global_conclusion")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", trade_date):
        raise AuthError("每日 TOP5 交易日期无效", 400)
    if not _has_complete_daily_top5_stocks(strong_stocks):
        raise AuthError("每日 TOP5 报告尚未包含完整的 5 只强势标的", 409)
    if not isinstance(conclusion, dict) or not _has_complete_daily_top5_conclusion(conclusion):
        raise AuthError("每日 TOP5 报告尚未包含全局结论", 409)

    report_json = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
    now = _now()
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT id FROM daily_top5_email_campaigns WHERE trade_date = ?", (trade_date,)
        ).fetchone()
        if existing:
            return _daily_top5_email_campaign_payload(conn, int(existing["id"]))
        campaign_id = int(
            conn.execute(
                """
                INSERT INTO daily_top5_email_campaigns
                    (trade_date, report_id, report_json, status, created_at)
                VALUES (?, ?, ?, 'pending', ?)
                """,
                (trade_date, report_id, report_json, now),
            ).lastrowid
        )
        users = conn.execute(
            """
            SELECT id, email, email_verified, update_emails_enabled,
                   membership_status, membership_expires_at
            FROM users
            WHERE role = 'user'
            ORDER BY id
            """
        ).fetchall()
        for user in users:
            email = str(user["email"] or "").strip().lower()
            eligible = bool(
                email
                and int(user["email_verified"] or 0) == 1
                and int(user["update_emails_enabled"] or 0) == 1
            )
            membership_active = _has_active_membership(user)
            if not email or int(user["email_verified"] or 0) != 1:
                error = "邮箱未验证"
            elif int(user["update_emails_enabled"] or 0) != 1:
                error = "用户已关闭邮件推送"
            else:
                error = None
            conn.execute(
                """
                INSERT INTO daily_top5_email_deliveries (
                    campaign_id, user_id, email, content_variant, membership_active,
                    status, attempt_count, next_attempt_at, last_error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    campaign_id,
                    user["id"],
                    email,
                    "full" if membership_active else "teaser",
                    1 if membership_active else 0,
                    "pending" if eligible else "skipped",
                    now if eligible else None,
                    error,
                    now,
                ),
            )
        _refresh_daily_top5_email_campaign_status(conn, campaign_id)
        return _daily_top5_email_campaign_payload(conn, campaign_id)


def retry_daily_top5_email_campaign(db_path: Path, *, campaign_id: int) -> dict[str, Any]:
    with _connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM daily_top5_email_campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()
        if not existing:
            raise AuthError("每日 TOP5 邮件任务不存在", 404)
        now = _now()
        cursor = conn.execute(
            """
            UPDATE daily_top5_email_deliveries
            SET status = 'pending', attempt_count = 0, next_attempt_at = ?,
                last_error = NULL, updated_at = ?
            WHERE campaign_id = ? AND status = 'failed'
              AND COALESCE(last_error, '') NOT LIKE '[permanent] %'
            """,
            (now, now, campaign_id),
        )
        if cursor.rowcount:
            conn.execute(
                "UPDATE daily_top5_email_campaigns SET status = 'pending', finished_at = NULL WHERE id = ?",
                (campaign_id,),
            )
        return _daily_top5_email_campaign_payload(conn, campaign_id)


def create_daily_top5_close_email_campaign(
    db_path: Path,
    *,
    report: dict[str, Any],
    now_dt: datetime | None = None,
) -> dict[str, Any]:
    trade_date = str(report.get("trade_date") or "").strip()
    report_id = str(report.get("id") or report.get("request_id") or "").strip()
    strong_stocks = report.get("top5_strong_stocks")
    conclusion = report.get("global_conclusion")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", trade_date):
        raise AuthError("每日 TOP5 收盘交易日期无效", 400)
    if not _has_complete_daily_top5_stocks(strong_stocks):
        raise AuthError("每日 TOP5 报告尚未包含完整的 5 只强势标的", 409)
    if not isinstance(conclusion, dict) or not _has_complete_daily_top5_conclusion(conclusion):
        raise AuthError("每日 TOP5 报告尚未包含全局结论", 409)

    current_dt = (now_dt or datetime.now(CN_TZ)).astimezone(CN_TZ)
    due_at = close_email_due_at(trade_date)
    cutoff_at = close_email_cutoff_at(trade_date)
    next_calculation_at = max(current_dt, due_at).isoformat() if current_dt <= cutoff_at else None
    calculation_status = "pending" if next_calculation_at else "failed"
    calculation_error = "" if next_calculation_at else "Top5 报告在 16:00 后到达，已转为人工重试"
    status = "pending" if next_calculation_at else "failed"
    report_json = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
    now = current_dt.isoformat()

    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT id FROM daily_top5_close_email_campaigns WHERE trade_date = ?",
            (trade_date,),
        ).fetchone()
        if existing:
            return _daily_top5_close_email_campaign_payload(conn, int(existing["id"]))
        campaign_id = int(
            conn.execute(
                """
                INSERT INTO daily_top5_close_email_campaigns (
                    trade_date, report_id, report_json, status, calculation_status,
                    calculation_due_at, next_calculation_at, calculation_last_error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_date,
                    report_id,
                    report_json,
                    status,
                    calculation_status,
                    due_at.isoformat(),
                    next_calculation_at,
                    calculation_error,
                    now,
                ),
            ).lastrowid
        )
        return _daily_top5_close_email_campaign_payload(conn, campaign_id)


def retry_daily_top5_close_email_campaign(
    db_path: Path,
    *,
    campaign_id: int,
    now_dt: datetime | None = None,
) -> dict[str, Any]:
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT id FROM daily_top5_close_email_campaigns WHERE id = ?",
            (campaign_id,),
        ).fetchone()
        if not existing:
            raise AuthError("每日 TOP5 收盘邮件任务不存在", 404)
        delivery_count = int(
            conn.execute(
                "SELECT COUNT(*) AS count FROM daily_top5_close_email_deliveries WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()["count"]
        )
        current_dt = (now_dt or datetime.now(CN_TZ)).astimezone(CN_TZ)
        now = current_dt.isoformat()
        if delivery_count == 0:
            conn.execute(
                """
                UPDATE daily_top5_close_email_campaigns
                SET status = 'pending',
                    finished_at = NULL,
                    calculation_status = 'pending',
                    next_calculation_at = ?,
                    calculation_override_requested_at = ?,
                    calculation_last_error = NULL
                WHERE id = ?
                """,
                (now, now, campaign_id),
            )
        else:
            cursor = conn.execute(
                """
                UPDATE daily_top5_close_email_deliveries
                SET status = 'pending', attempt_count = 0, next_attempt_at = ?,
                    last_error = NULL, updated_at = ?
                WHERE campaign_id = ? AND status = 'failed'
                """,
                (now, now, campaign_id),
            )
            if cursor.rowcount:
                conn.execute(
                    "UPDATE daily_top5_close_email_campaigns SET status = 'pending', finished_at = NULL WHERE id = ?",
                    (campaign_id,),
                )
        return _daily_top5_close_email_campaign_payload(conn, campaign_id)


AI_REPORT_EMAIL_TYPES = {"market_day", "ai_research"}


def create_ai_report_email_campaign(
    db_path: Path,
    *,
    report_type: str,
    report: dict[str, Any],
) -> dict[str, Any]:
    """Persist an idempotent recipient and membership snapshot for an AI report."""
    report_type = str(report_type or "").strip()
    if report_type not in AI_REPORT_EMAIL_TYPES:
        raise AuthError("AI 报告邮件类型无效", 400)
    if not isinstance(report, dict):
        raise AuthError("AI 报告内容无效", 400)
    run_id = str(report.get("run_id") or "").strip()
    if report_type == "market_day":
        market_body = report.get("report") if isinstance(report.get("report"), dict) else {}
        report_date = str(
            report.get("market_date") or report.get("marketDate") or market_body.get("marketDate") or ""
        ).strip()
    else:
        report_date = str(report.get("research_date") or "").strip()
    if not run_id or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", run_id):
        raise AuthError("AI 报告 run_id 无效", 400)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_date):
        raise AuthError("AI 报告日期无效", 400)
    if not _is_complete_ai_email_report(report_type, report):
        raise AuthError("AI 报告内容尚未完整，暂不发送邮件", 409)

    report_json = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
    now = _now()
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT id FROM ai_report_email_campaigns WHERE report_type = ? AND run_id = ?",
            (report_type, run_id),
        ).fetchone()
        if existing:
            return _ai_report_email_campaign_payload(conn, int(existing["id"]))
        campaign_id = int(
            conn.execute(
                """
                INSERT INTO ai_report_email_campaigns
                    (report_type, run_id, report_date, report_json, status, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (report_type, run_id, report_date, report_json, now),
            ).lastrowid
        )
        users = conn.execute(
            """
            SELECT id, email, email_verified, update_emails_enabled,
                   membership_status, membership_expires_at
            FROM users
            WHERE role = 'user'
            ORDER BY id
            """
        ).fetchall()
        for user in users:
            email = str(user["email"] or "").strip().lower()
            verified = int(user["email_verified"] or 0) == 1
            opted_in = int(user["update_emails_enabled"] or 0) == 1
            eligible = bool(email and verified and opted_in)
            membership_active = _has_active_membership(user)
            reason = None
            if not email or not verified:
                reason = "邮箱未验证"
            elif not opted_in:
                reason = "用户已关闭邮件推送"
            conn.execute(
                """
                INSERT INTO ai_report_email_deliveries (
                    campaign_id, user_id, email, content_variant, membership_active,
                    status, attempt_count, next_attempt_at, last_error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    campaign_id,
                    int(user["id"]),
                    email,
                    "full" if membership_active else "teaser",
                    1 if membership_active else 0,
                    "pending" if eligible else "skipped",
                    now if eligible else None,
                    reason,
                    now,
                ),
            )
        _refresh_ai_report_email_campaign_status(conn, campaign_id)
        return _ai_report_email_campaign_payload(conn, campaign_id)


def retry_ai_report_email_campaign(db_path: Path, *, campaign_id: int) -> dict[str, Any]:
    with _connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM ai_report_email_campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()
        if not existing:
            raise AuthError("AI 报告邮件任务不存在", 404)
        now = _now()
        cursor = conn.execute(
            """
            UPDATE ai_report_email_deliveries
            SET status = 'pending', attempt_count = 0, next_attempt_at = ?,
                last_error = NULL, updated_at = ?
            WHERE campaign_id = ? AND status = 'failed'
            """,
            (now, now, campaign_id),
        )
        if cursor.rowcount:
            conn.execute(
                "UPDATE ai_report_email_campaigns SET status = 'pending', finished_at = NULL WHERE id = ?",
                (campaign_id,),
            )
        return _ai_report_email_campaign_payload(conn, campaign_id)


def _is_permanent_email_error(value: object) -> bool:
    message = str(value or "").strip().lower()
    return message.startswith(PERMANENT_EMAIL_ERROR_PREFIX) or any(
        marker in message for marker in PERMANENT_EMAIL_ERROR_MARKERS
    )


def _stored_email_error(exc: Exception) -> str:
    message = str(exc)[:500]
    if _is_permanent_email_error(message) and not message.lower().startswith(PERMANENT_EMAIL_ERROR_PREFIX):
        return f"{PERMANENT_EMAIL_ERROR_PREFIX}{message}"[:500]
    return message


def recover_update_email_queue(db_path: Path) -> int:
    cutoff = (datetime.now(CN_TZ) - timedelta(minutes=10)).isoformat()
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE update_email_deliveries
            SET status = 'pending', next_attempt_at = ?, updated_at = ?
            WHERE status = 'sending' AND updated_at < ?
            """,
            (_now(), _now(), cutoff),
        )
        return int(cursor.rowcount)


def recover_daily_top5_email_queue(db_path: Path) -> int:
    cutoff = (datetime.now(CN_TZ) - timedelta(minutes=10)).isoformat()
    with _connect(db_path) as conn:
        affected_campaigns: set[int] = set()
        normalized = 0
        for row in conn.execute(
            """
            SELECT id, campaign_id, last_error
            FROM daily_top5_email_deliveries
            WHERE status IN ('pending', 'sending') AND last_error IS NOT NULL
            """
        ).fetchall():
            if not _is_permanent_email_error(row["last_error"]):
                continue
            error = str(row["last_error"] or "")
            if not error.lower().startswith(PERMANENT_EMAIL_ERROR_PREFIX):
                error = f"{PERMANENT_EMAIL_ERROR_PREFIX}{error}"[:500]
            conn.execute(
                """
                UPDATE daily_top5_email_deliveries
                SET status = 'failed', next_attempt_at = NULL, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (error, _now(), row["id"]),
            )
            affected_campaigns.add(int(row["campaign_id"]))
            normalized += 1
        cursor = conn.execute(
            """
            UPDATE daily_top5_email_deliveries
            SET status = 'pending', next_attempt_at = ?, updated_at = ?
            WHERE status = 'sending' AND updated_at < ?
            """,
            (_now(), _now(), cutoff),
        )
        for campaign_id in affected_campaigns:
            _refresh_daily_top5_email_campaign_status(conn, campaign_id)
        return normalized + int(cursor.rowcount)


def recover_daily_top5_close_email_queue(db_path: Path, *, now_dt: datetime | None = None) -> int:
    current_dt = (now_dt or datetime.now(CN_TZ)).astimezone(CN_TZ)
    now = current_dt.isoformat()
    cutoff = (current_dt - timedelta(minutes=10)).isoformat()
    with _connect(db_path) as conn:
        delivery_cursor = conn.execute(
            """
            UPDATE daily_top5_close_email_deliveries
            SET status = 'pending', next_attempt_at = ?, updated_at = ?
            WHERE status = 'sending' AND updated_at < ?
            """,
            (now, now, cutoff),
        )
        campaign_rows = conn.execute(
            """
            SELECT id, trade_date, calculation_override_requested_at
            FROM daily_top5_close_email_campaigns
            WHERE calculation_status = 'calculating'
              AND COALESCE(calculation_started_at, '') < ?
            """,
            (cutoff,),
        ).fetchall()
        recovered = int(delivery_cursor.rowcount)
        for row in campaign_rows:
            trade_date = str(row["trade_date"] or "").strip()
            cutoff_at = close_email_cutoff_at(trade_date)
            manual_override = bool(str(row["calculation_override_requested_at"] or "").strip())
            if current_dt <= cutoff_at or manual_override:
                conn.execute(
                    """
                    UPDATE daily_top5_close_email_campaigns
                    SET calculation_status = 'pending',
                        next_calculation_at = ?,
                        calculation_last_error = COALESCE(NULLIF(calculation_last_error, ''), '收盘行情计算在恢复后重试')
                    WHERE id = ?
                    """,
                    (now, row["id"]),
                )
            else:
                conn.execute(
                    """
                    UPDATE daily_top5_close_email_campaigns
                    SET status = 'failed',
                        finished_at = ?,
                        calculation_status = 'failed',
                        next_calculation_at = NULL,
                        calculation_override_requested_at = NULL,
                        calculation_last_error = ?
                    WHERE id = ?
                    """,
                    (now, _daily_top5_close_calculation_failure_message(
                        [{"code": "", "name": trade_date, "reason": "calculation_recovered_after_cutoff"}],
                        fallback="收盘行情计算已超过自动重试截止时间，请管理员手动重试",
                    ), row["id"]),
                )
            recovered += 1
        return recovered


def recover_ai_report_email_queue(db_path: Path) -> int:
    cutoff = (datetime.now(CN_TZ) - timedelta(minutes=10)).isoformat()
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE ai_report_email_deliveries
            SET status = 'pending', next_attempt_at = ?, updated_at = ?
            WHERE status = 'sending' AND updated_at < ?
            """,
            (_now(), _now(), cutoff),
        )
        return int(cursor.rowcount)


def process_next_update_email(
    db_path: Path,
    *,
    sender: Callable[[dict[str, Any]], None] | None = None,
    smtp_session: "UpdateEmailSMTPSession | None" = None,
) -> bool:
    now = _now()
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        excluded_campaigns = [
            int(item["campaign_id"])
            for item in conn.execute(
                """
                SELECT DISTINCT d.campaign_id
                FROM update_email_deliveries d
                JOIN users u ON u.id = d.user_id
                WHERE u.role != 'user' AND d.status IN ('pending', 'failed')
                """
            ).fetchall()
        ]
        if excluded_campaigns:
            conn.execute(
                """
                UPDATE update_email_deliveries
                SET status = 'skipped', next_attempt_at = NULL,
                    last_error = '管理员不接收产品更新邮件', updated_at = ?
                WHERE status IN ('pending', 'failed')
                  AND user_id IN (SELECT id FROM users WHERE role != 'user')
                """,
                (now,),
            )
            for campaign_id in excluded_campaigns:
                _refresh_email_campaign_status(conn, campaign_id)
        row = conn.execute(
            """
            SELECT d.id, d.campaign_id, d.email, d.attempt_count,
                   n.title, n.version, n.items_json, n.summary, n.content_markdown
            FROM update_email_deliveries d
            JOIN update_email_campaigns c ON c.id = d.campaign_id
            JOIN update_notices n ON n.id = c.notice_id
            JOIN users u ON u.id = d.user_id
            WHERE u.role = 'user'
              AND d.status = 'pending'
              AND (d.next_attempt_at IS NULL OR d.next_attempt_at <= ?)
            ORDER BY d.id
            LIMIT 1
            """,
            (now,),
        ).fetchone()
        if not row:
            return False
        attempt = int(row["attempt_count"]) + 1
        conn.execute(
            "UPDATE update_email_deliveries SET status = 'sending', attempt_count = ?, updated_at = ? WHERE id = ?",
            (attempt, now, row["id"]),
        )
        conn.execute(
            "UPDATE update_email_campaigns SET status = 'sending', started_at = COALESCE(started_at, ?) WHERE id = ?",
            (now, row["campaign_id"]),
        )
        delivery = dict(row)
        delivery["attempt_count"] = attempt
    try:
        if sender is not None:
            sender(delivery)
        elif smtp_session is not None:
            _send_update_notice_email(delivery, smtp_session=smtp_session)
        else:
            _send_update_notice_email(delivery)
    except Exception as exc:
        with _connect(db_path) as conn:
            if attempt >= UPDATE_EMAIL_MAX_ATTEMPTS:
                conn.execute(
                    "UPDATE update_email_deliveries SET status = 'failed', last_error = ?, updated_at = ? WHERE id = ?",
                    (str(exc)[:500], _now(), delivery["id"]),
                )
            else:
                delay = UPDATE_EMAIL_RETRY_MINUTES[min(attempt - 1, len(UPDATE_EMAIL_RETRY_MINUTES) - 1)]
                next_attempt = (datetime.now(CN_TZ) + timedelta(minutes=delay)).isoformat()
                conn.execute(
                    "UPDATE update_email_deliveries SET status = 'pending', next_attempt_at = ?, last_error = ?, updated_at = ? WHERE id = ?",
                    (next_attempt, str(exc)[:500], _now(), delivery["id"]),
                )
            _refresh_email_campaign_status(conn, int(delivery["campaign_id"]))
    else:
        with _connect(db_path) as conn:
            conn.execute(
                "UPDATE update_email_deliveries SET status = 'sent', sent_at = ?, last_error = NULL, updated_at = ? WHERE id = ?",
                (_now(), _now(), delivery["id"]),
            )
            _refresh_email_campaign_status(conn, int(delivery["campaign_id"]))
    return True


def process_next_daily_top5_email(
    db_path: Path,
    *,
    sender: Callable[[dict[str, Any]], None] | None = None,
    smtp_session: "UpdateEmailSMTPSession | None" = None,
) -> bool:
    now = _now()
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT d.id, d.campaign_id, d.email, d.content_variant,
                   d.membership_active, d.attempt_count,
                   c.trade_date, c.report_id, c.report_json
            FROM daily_top5_email_deliveries d
            JOIN daily_top5_email_campaigns c ON c.id = d.campaign_id
            WHERE d.status IN ('pending', 'failed')
              AND d.attempt_count < ?
              AND NOT (d.status = 'failed' AND COALESCE(d.last_error, '') LIKE '[permanent] %')
              AND (d.next_attempt_at IS NULL OR d.next_attempt_at <= ?)
            ORDER BY d.id
            LIMIT 1
            """,
            (DAILY_TOP5_EMAIL_MAX_ATTEMPTS, now),
        ).fetchone()
        if not row:
            return False
        attempt = int(row["attempt_count"]) + 1
        conn.execute(
            "UPDATE daily_top5_email_deliveries SET status = 'sending', attempt_count = ?, updated_at = ? WHERE id = ?",
            (attempt, now, row["id"]),
        )
        conn.execute(
            "UPDATE daily_top5_email_campaigns SET status = 'sending', started_at = COALESCE(started_at, ?) WHERE id = ?",
            (now, row["campaign_id"]),
        )
        delivery = dict(row)
        delivery["attempt_count"] = attempt
    try:
        if sender is not None:
            sender(delivery)
        elif smtp_session is not None:
            _send_daily_top5_email(delivery, smtp_session=smtp_session)
        else:
            _send_daily_top5_email(delivery)
    except Exception as exc:
        error = _stored_email_error(exc)
        with _connect(db_path) as conn:
            if _is_permanent_email_error(error) or attempt >= DAILY_TOP5_EMAIL_MAX_ATTEMPTS:
                conn.execute(
                    """
                    UPDATE daily_top5_email_deliveries
                    SET status = 'failed', next_attempt_at = NULL, last_error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (error, _now(), delivery["id"]),
                )
            else:
                delay = DAILY_TOP5_EMAIL_RETRY_MINUTES[
                    min(attempt - 1, len(DAILY_TOP5_EMAIL_RETRY_MINUTES) - 1)
                ]
                next_attempt = (datetime.now(CN_TZ) + timedelta(minutes=delay)).isoformat()
                conn.execute(
                    """
                    UPDATE daily_top5_email_deliveries
                    SET status = 'pending', next_attempt_at = ?, last_error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (next_attempt, error, _now(), delivery["id"]),
                )
            _refresh_daily_top5_email_campaign_status(conn, int(delivery["campaign_id"]))
    else:
        with _connect(db_path) as conn:
            conn.execute(
                """
                UPDATE daily_top5_email_deliveries
                SET status = 'sent', sent_at = ?, last_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (_now(), _now(), delivery["id"]),
            )
            _refresh_daily_top5_email_campaign_status(conn, int(delivery["campaign_id"]))
    return True


def process_next_daily_top5_close_email(
    db_path: Path,
    *,
    cache_db: Path | None = None,
    provider: Any | None = None,
    sender: Callable[[dict[str, Any]], None] | None = None,
    smtp_session: "UpdateEmailSMTPSession | None" = None,
    now_dt: datetime | None = None,
) -> bool:
    current_dt = (now_dt or datetime.now(CN_TZ)).astimezone(CN_TZ)
    now = current_dt.isoformat()
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        calc_row = conn.execute(
            """
            SELECT *
            FROM daily_top5_close_email_campaigns
            WHERE calculation_status = 'pending'
              AND COALESCE(next_calculation_at, '') != ''
              AND next_calculation_at <= ?
            ORDER BY next_calculation_at, id
            LIMIT 1
            """,
            (now,),
        ).fetchone()
        if calc_row:
            attempt = int(calc_row["calculation_attempt_count"] or 0) + 1
            conn.execute(
                """
                UPDATE daily_top5_close_email_campaigns
                SET calculation_status = 'calculating',
                    calculation_attempt_count = ?,
                    calculation_started_at = ?
                WHERE id = ?
                """,
                (attempt, now, calc_row["id"]),
            )
            campaign = dict(calc_row)
            campaign["calculation_attempt_count"] = attempt
        else:
            campaign = None
    if campaign is not None:
        manual_override = bool(str(campaign.get("calculation_override_requested_at") or "").strip())
        cutoff_at = close_email_cutoff_at(str(campaign.get("trade_date") or ""))
        scheduled_at_text = str(campaign.get("next_calculation_at") or "").strip()
        try:
            scheduled_at = datetime.fromisoformat(scheduled_at_text).astimezone(CN_TZ)
        except (TypeError, ValueError):
            scheduled_at = None
        # A retry deliberately scheduled for 16:00 may be claimed a few
        # seconds late by the polling worker. Allow that already-earned final
        # attempt a short claim grace, but never let a never-attempted morning
        # task or a restarted stale task run after the cutoff automatically.
        final_attempt_grace = bool(
            int(campaign.get("calculation_attempt_count") or 0) > 1
            and scheduled_at == cutoff_at
            and current_dt <= cutoff_at + timedelta(minutes=1)
        )
        if current_dt > cutoff_at and not manual_override and not final_attempt_grace:
            with _connect(db_path) as conn:
                conn.execute(
                    """
                    UPDATE daily_top5_close_email_campaigns
                    SET status = 'failed', finished_at = ?,
                        calculation_status = 'failed', next_calculation_at = NULL,
                        calculation_override_requested_at = NULL,
                        calculation_last_error = ?
                    WHERE id = ?
                    """,
                    (
                        now,
                        _daily_top5_close_calculation_failure_message(
                            [{"code": "", "name": str(campaign.get("trade_date") or ""), "reason": "automatic_cutoff_elapsed"}],
                            fallback="收盘行情计算已超过自动重试截止时间，请管理员手动重试",
                        ),
                        campaign["id"],
                    ),
                )
            return True
        report = json.loads(str(campaign.get("report_json") or "{}"))
        snapshot, issues = collect_close_email_snapshot(
            report,
            cache_db=cache_db or db_path.parent / "market_data_cache.sqlite",
            provider=provider,
            quote_time=current_dt,
        )
        if snapshot is not None:
            with _connect(db_path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing_delivery_count = int(
                    conn.execute(
                        "SELECT COUNT(*) AS count FROM daily_top5_close_email_deliveries WHERE campaign_id = ?",
                        (campaign["id"],),
                    ).fetchone()["count"]
                )
                if existing_delivery_count == 0:
                    users = conn.execute(
                        """
                        SELECT id, email, email_verified, update_emails_enabled
                        FROM users
                        WHERE role = 'user'
                        ORDER BY id
                        """
                    ).fetchall()
                    for user in users:
                        email = str(user["email"] or "").strip().lower()
                        verified = int(user["email_verified"] or 0) == 1
                        opted_in = int(user["update_emails_enabled"] or 0) == 1
                        eligible = bool(email and verified and opted_in)
                        reason = None
                        if not email or not verified:
                            reason = "邮箱未验证"
                        elif not opted_in:
                            reason = "用户已关闭邮件推送"
                        conn.execute(
                            """
                            INSERT INTO daily_top5_close_email_deliveries (
                                campaign_id, user_id, email, content_variant, membership_active,
                                status, attempt_count, next_attempt_at, last_error, updated_at
                            ) VALUES (?, ?, ?, 'full', 0, ?, 0, ?, ?, ?)
                            """,
                            (
                                campaign["id"],
                                int(user["id"]),
                                email,
                                "pending" if eligible else "skipped",
                                now if eligible else None,
                                reason,
                                now,
                            ),
                        )
                conn.execute(
                    """
                    UPDATE daily_top5_close_email_campaigns
                    SET close_report_json = ?, calculation_status = 'ready',
                        calculation_ready_at = ?, calculation_override_requested_at = NULL,
                        calculation_last_error = NULL
                    WHERE id = ?
                    """,
                    (json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), now, campaign["id"]),
                )
                _refresh_daily_top5_close_email_campaign_status(conn, int(campaign["id"]))
            return True

        error = "quote_missing: " + "；".join(
            f"{item.get('name') or item.get('code') or '-'}:{item.get('reason') or 'quote_missing'}"
            for item in issues
        )[:500] or "收盘行情尚未齐备"
        next_retry = min(current_dt + timedelta(minutes=DAILY_TOP5_CLOSE_EMAIL_RETRY_MINUTES), cutoff_at)
        with _connect(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if not manual_override and current_dt < cutoff_at and next_retry >= current_dt:
                conn.execute(
                    """
                    UPDATE daily_top5_close_email_campaigns
                    SET calculation_status = 'pending',
                        next_calculation_at = ?,
                        calculation_last_error = ?
                    WHERE id = ?
                    """,
                    (next_retry.isoformat(), error, campaign["id"]),
                )
            else:
                conn.execute(
                    """
                    UPDATE daily_top5_close_email_campaigns
                    SET calculation_status = 'failed',
                        next_calculation_at = NULL,
                        calculation_override_requested_at = NULL,
                        calculation_last_error = ?
                    WHERE id = ?
                    """,
                    (error, campaign["id"]),
                )
            _refresh_daily_top5_close_email_campaign_status(conn, int(campaign["id"]))
        return True

    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT d.id, d.campaign_id, d.email, d.attempt_count, c.trade_date, c.close_report_json
            FROM daily_top5_close_email_deliveries d
            JOIN daily_top5_close_email_campaigns c ON c.id = d.campaign_id
            WHERE d.status = 'pending'
              AND (d.next_attempt_at IS NULL OR d.next_attempt_at <= ?)
            ORDER BY d.id
            LIMIT 1
            """,
            (now,),
        ).fetchone()
        if not row:
            return False
        attempt = int(row["attempt_count"]) + 1
        conn.execute(
            """
            UPDATE daily_top5_close_email_deliveries
            SET status = 'sending', attempt_count = ?, updated_at = ?
            WHERE id = ?
            """,
            (attempt, now, row["id"]),
        )
        conn.execute(
            """
            UPDATE daily_top5_close_email_campaigns
            SET status = 'sending', started_at = COALESCE(started_at, ?)
            WHERE id = ?
            """,
            (now, row["campaign_id"]),
        )
        delivery = dict(row)
        delivery["attempt_count"] = attempt
    try:
        if sender is not None:
            sender(delivery)
        elif smtp_session is not None:
            _send_daily_top5_close_email(delivery, smtp_session=smtp_session)
        else:
            _send_daily_top5_close_email(delivery)
    except Exception as exc:
        with _connect(db_path) as conn:
            if attempt >= UPDATE_EMAIL_MAX_ATTEMPTS:
                conn.execute(
                    """
                    UPDATE daily_top5_close_email_deliveries
                    SET status = 'failed', last_error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (str(exc)[:500], _now(), delivery["id"]),
                )
            else:
                delay = UPDATE_EMAIL_RETRY_MINUTES[min(attempt - 1, len(UPDATE_EMAIL_RETRY_MINUTES) - 1)]
                next_attempt = (datetime.now(CN_TZ) + timedelta(minutes=delay)).isoformat()
                conn.execute(
                    """
                    UPDATE daily_top5_close_email_deliveries
                    SET status = 'pending', next_attempt_at = ?, last_error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (next_attempt, str(exc)[:500], _now(), delivery["id"]),
                )
            _refresh_daily_top5_close_email_campaign_status(conn, int(delivery["campaign_id"]))
    else:
        with _connect(db_path) as conn:
            conn.execute(
                """
                UPDATE daily_top5_close_email_deliveries
                SET status = 'sent', sent_at = ?, last_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (_now(), _now(), delivery["id"]),
            )
            _refresh_daily_top5_close_email_campaign_status(conn, int(delivery["campaign_id"]))
    return True


def process_next_ai_report_email(
    db_path: Path,
    *,
    report_type: str | None = None,
    sender: Callable[[dict[str, Any]], None] | None = None,
    smtp_session: "UpdateEmailSMTPSession | None" = None,
) -> bool:
    if report_type is not None and report_type not in AI_REPORT_EMAIL_TYPES:
        raise AuthError("AI 报告邮件类型无效", 400)
    now = _now()
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        query = """
            SELECT d.id, d.campaign_id, d.email, d.content_variant,
                   d.membership_active, d.attempt_count,
                   c.report_type, c.run_id, c.report_date, c.report_json
            FROM ai_report_email_deliveries d
            JOIN ai_report_email_campaigns c ON c.id = d.campaign_id
            WHERE d.status = 'pending'
              AND (d.next_attempt_at IS NULL OR d.next_attempt_at <= ?)
        """
        params: list[object] = [now]
        if report_type is not None:
            query += " AND c.report_type = ?"
            params.append(report_type)
        query += """
            ORDER BY d.id
            LIMIT 1
        """
        row = conn.execute(query, params).fetchone()
        if not row:
            return False
        attempt = int(row["attempt_count"]) + 1
        conn.execute(
            "UPDATE ai_report_email_deliveries SET status = 'sending', attempt_count = ?, updated_at = ? WHERE id = ?",
            (attempt, now, row["id"]),
        )
        conn.execute(
            "UPDATE ai_report_email_campaigns SET status = 'sending', started_at = COALESCE(started_at, ?) WHERE id = ?",
            (now, row["campaign_id"]),
        )
        delivery = dict(row)
        delivery["attempt_count"] = attempt
    try:
        if sender is not None:
            sender(delivery)
        elif smtp_session is not None:
            _send_ai_report_email(delivery, smtp_session=smtp_session)
        else:
            _send_ai_report_email(delivery)
    except Exception as exc:
        with _connect(db_path) as conn:
            if attempt >= UPDATE_EMAIL_MAX_ATTEMPTS:
                conn.execute(
                    "UPDATE ai_report_email_deliveries SET status = 'failed', last_error = ?, updated_at = ? WHERE id = ?",
                    (str(exc)[:500], _now(), delivery["id"]),
                )
            else:
                delay = UPDATE_EMAIL_RETRY_MINUTES[min(attempt - 1, len(UPDATE_EMAIL_RETRY_MINUTES) - 1)]
                next_attempt = (datetime.now(CN_TZ) + timedelta(minutes=delay)).isoformat()
                conn.execute(
                    """
                    UPDATE ai_report_email_deliveries
                    SET status = 'pending', next_attempt_at = ?, last_error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (next_attempt, str(exc)[:500], _now(), delivery["id"]),
                )
            _refresh_ai_report_email_campaign_status(conn, int(delivery["campaign_id"]))
    else:
        with _connect(db_path) as conn:
            conn.execute(
                """
                UPDATE ai_report_email_deliveries
                SET status = 'sent', sent_at = ?, last_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (_now(), _now(), delivery["id"]),
            )
            _refresh_ai_report_email_campaign_status(conn, int(delivery["campaign_id"]))
    return True


def unpublish_update_notice(db_path: Path, *, notice_id: int) -> dict[str, Any]:
    with _connect(db_path) as conn:
        existing = conn.execute("SELECT * FROM update_notices WHERE id = ?", (notice_id,)).fetchone()
        if not existing:
            raise AuthError("更新公告不存在", 404)
        conn.execute(
            "UPDATE update_notices SET status = 'archived', updated_at = ? WHERE id = ?",
            (_now(), notice_id),
        )
        return _update_notice_payload(conn.execute("SELECT * FROM update_notices WHERE id = ?", (notice_id,)).fetchone())


def review_feedback(db_path: Path, *, feedback_id: int, status: str, admin_note: str = "") -> dict[str, Any]:
    status = status.strip()
    if status not in {"pending", "accepted", "rejected"}:
        raise AuthError("反馈状态不正确", 400)
    now = _now()
    reward_user_id = 0
    reward = 0
    with _connect(db_path) as conn:
        feedback = conn.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
        if not feedback:
            raise AuthError("反馈不存在", 404)
        if status == "accepted" and feedback["reward_credits"] <= 0:
            reward = FEEDBACK_REWARD_CREDITS
            reward_user_id = int(feedback["user_id"])
            _add_credits(conn, int(feedback["user_id"]), reward, "feedback_accepted", str(feedback_id))
        conn.execute(
            """
            UPDATE feedback
            SET status = ?, reward_credits = reward_credits + ?, admin_note = ?, reviewed_at = ?
            WHERE id = ?
            """,
            (status, reward, admin_note.strip()[:300], now, feedback_id),
        )
        updated = conn.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
        result = _feedback_payload(updated)
    if reward > 0 and reward_user_id:
        result["email_notification"] = notify_credit_added(
            db_path,
            user_id=reward_user_id,
            credits=reward,
            reason="你的反馈已被采纳，平台奖励免费使用次数。",
        )
    return result


def mark_order_paid(db_path: Path, *, order_id: int) -> dict[str, Any]:
    now = _now()
    notify_user_id = 0
    notify_credits = 0
    notify_reason = ""
    with _connect(db_path) as conn:
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order:
            raise AuthError("订单不存在", 404)
        product_type = str(order["product_type"] if "product_type" in order.keys() else "").strip()
        if product_type == "membership":
            raise AuthError("会员订单请使用确认开通操作", 400)
        if product_type == "credits":
            raise AuthError("人工次数订单请先提交付款信息，再使用确认到账操作", 400)
        if order["status"] != "paid":
            conn.execute("UPDATE orders SET status = 'paid', paid_at = ? WHERE id = ?", (now, order_id))
            _add_credits(conn, int(order["user_id"]), int(order["credits"]), "order_paid", str(order_id))
            notify_user_id = int(order["user_id"])
            notify_credits = int(order["credits"])
            notify_reason = f"你购买的「{order['plan_name']}」次数包已确认支付。"
        updated = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        result = _order_payload(updated)
    if notify_credits > 0 and notify_user_id:
        result["email_notification"] = notify_credit_added(
            db_path,
            user_id=notify_user_id,
            credits=notify_credits,
            reason=notify_reason,
        )
    return result


def mark_order_paid_by_order_no(
    db_path: Path,
    *,
    order_no: str,
    total_amount: str,
    provider_trade_no: str = "",
    payment_provider: str = "alipay",
    payer_email: str = "",
) -> dict[str, Any]:
    order_no = (order_no or "").strip()
    paid_amount_cents = _amount_yuan_to_cents(total_amount)
    payment_provider = (payment_provider or "unknown").strip()[:40]
    provider_trade_no = (provider_trade_no or "").strip()[:120]
    payer_email = (payer_email or "").strip().lower()
    provider_label = _payment_provider_label(payment_provider)
    notify_user_id = 0
    notify_credits = 0
    notify_reason = ""
    with _connect(db_path) as conn:
        if provider_trade_no:
            existing = conn.execute(
                """
                SELECT *
                FROM orders
                WHERE payment_provider = ? AND provider_trade_no = ?
                LIMIT 1
                """,
                (payment_provider, provider_trade_no),
            ).fetchone()
            if existing:
                if existing["order_no"] != order_no:
                    raise AuthError("该支付回调已绑定其他订单，请人工核对", 409)
                return _order_payload(existing)

        order = conn.execute("SELECT * FROM orders WHERE order_no = ?", (order_no,)).fetchone()
        if not order:
            raise AuthError("订单不存在", 404)
        product_type = str(order["product_type"] if "product_type" in order.keys() else "").strip()
        if product_type in {"credits", "membership"}:
            raise AuthError("人工核款订单不能通过自动支付回调确认", 400)
        user = _fetch_user_by_id(conn, int(order["user_id"]))
        user_email = str(user["email"] if "email" in user.keys() else "").strip().lower()
        if payer_email and user_email and payer_email != user_email:
            raise AuthError("支付表单邮箱与订单用户邮箱不一致", 400)
        if int(order["amount_cents"]) != paid_amount_cents:
            raise AuthError(f"{provider_label}通知金额与订单金额不一致", 400)
        if order["status"] != "paid":
            now = _now()
            conn.execute(
                """
                UPDATE orders
                SET status = 'paid',
                    paid_at = ?,
                    payment_provider = ?,
                    provider_trade_no = ?,
                    paid_amount_cents = ?
                WHERE id = ?
                """,
                (now, payment_provider, provider_trade_no, paid_amount_cents, order["id"]),
            )
            _add_credits(conn, int(order["user_id"]), int(order["credits"]), "order_paid", str(order["id"]))
            notify_user_id = int(order["user_id"])
            notify_credits = int(order["credits"])
            notify_reason = f"你购买的「{order['plan_name']}」次数包已通过{provider_label}支付成功。"
        updated = conn.execute("SELECT * FROM orders WHERE id = ?", (order["id"],)).fetchone()
        result = _order_payload(updated)
    if notify_credits > 0 and notify_user_id:
        result["email_notification"] = notify_credit_added(
            db_path,
            user_id=notify_user_id,
            credits=notify_credits,
            reason=notify_reason,
        )
    return result


def _payment_provider_label(provider: str) -> str:
    labels = {
        "alipay": "支付宝",
        "jinshuju": "金数据",
        "wechat": "微信",
    }
    return labels.get((provider or "").strip().lower(), "支付平台")


def notify_admin_membership_payment(*, order: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    try:
        admin_email = os.getenv("ADMIN_PAYMENT_NOTIFY_EMAIL", "").strip()
        if not admin_email:
            return {"sent": False, "skipped": True, "error": "ADMIN_PAYMENT_NOTIFY_EMAIL 未配置"}
        amount = int(order.get("amount_cents") or 0) / 100
        submitted_amount = int(order.get("submitted_amount_cents") or 0) / 100
        payment_method = _payment_provider_label(str(order.get("payment_method") or ""))
        plan_name = str(order.get("plan_name") or "会员套餐").strip() or "会员套餐"
        subject = f"【盈航】用户已付款待确认 - {plan_name} ¥{amount:.2f} - 订单号 {order.get('order_no')}"
        admin_url = os.getenv("ADMIN_DASHBOARD_URL", "").strip() or "/admin"
        user_label = user.get("username") or user.get("email") or user.get("phone") or f"用户 {user.get('id')}"
        text = (
            "有用户提交了会员付款信息，请核对支付宝/微信到账后再开通。\n\n"
            f"订单号：{order.get('order_no')}\n"
            f"用户：{user_label}\n"
            f"手机号/账号：{user.get('phone') or ''}\n"
            f"邮箱：{user.get('email') or ''}\n"
            f"套餐：{order.get('plan_name')}\n"
            f"应付金额：¥{amount:.2f}\n"
            f"支付方式：{payment_method}\n"
            f"付款人：{order.get('payer_name') or ''}\n"
            f"付款时间：{order.get('payer_paid_at') or ''}\n"
            f"实付金额：¥{submitted_amount:.2f}\n"
            f"付款备注：{order.get('payer_note') or ''}\n"
            f"管理后台：{admin_url}\n"
        )
        html = _light_email_document(f"""
          <h1 style="margin:0 0 20px;color:#1f2328;font-size:24px;line-height:1.35;">用户已付款待确认</h1>
          <p style="margin:0 0 20px;color:#1f2328;line-height:1.7;">请核对支付宝/微信到账后，再到管理台确认开通会员。</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>订单号：</strong>{_html_escape(str(order.get('order_no') or ''))}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>用户：</strong>{_html_escape(str(user_label))}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>账号：</strong>{_html_escape(str(user.get('phone') or ''))}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>邮箱：</strong>{_html_escape(str(user.get('email') or ''))}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>套餐：</strong>{_html_escape(str(order.get('plan_name') or ''))}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>应付金额：</strong>¥{amount:.2f}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>支付方式：</strong>{_html_escape(payment_method)}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>付款人：</strong>{_html_escape(str(order.get('payer_name') or ''))}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>付款时间：</strong>{_html_escape(str(order.get('payer_paid_at') or ''))}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>实付金额：</strong>¥{submitted_amount:.2f}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>付款备注：</strong>{_html_escape(str(order.get('payer_note') or ''))}</p>
          <p style="margin:20px 0 0;color:#1f2328;"><strong>管理后台：</strong><a href="{_html_escape(admin_url)}" style="color:#0969da;text-decoration:underline;">{_html_escape(admin_url)}</a></p>
        """, max_width=640)
        provider = os.getenv("EMAIL_PROVIDER", "smtp").strip().lower() or "smtp"
        if provider in {"log", "debug", "local"}:
            _write_email_debug_log(admin_email, text, None)
            return {"sent": False, "skipped": True, "provider": "log", "email": _mask_email(admin_email), "error": "EMAIL_PROVIDER=log，仅写入本地日志，未真实发送邮件"}
        _send_email_message(admin_email, subject=subject, text=text, html=html)
        return {"sent": True, "provider": provider, "email": _mask_email(admin_email)}
    except Exception as exc:
        return {"sent": False, "error": str(exc)}


def notify_admin_credit_payment(*, order: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    try:
        admin_email = os.getenv("ADMIN_PAYMENT_NOTIFY_EMAIL", "").strip()
        if not admin_email:
            return {"sent": False, "skipped": True, "error": "ADMIN_PAYMENT_NOTIFY_EMAIL 未配置"}
        amount = int(order.get("amount_cents") or 0) / 100
        submitted_amount = int(order.get("submitted_amount_cents") or 0) / 100
        payment_method = _payment_provider_label(str(order.get("payment_method") or ""))
        plan_name = str(order.get("plan_name") or "次数充值").strip() or "次数充值"
        user_label = user.get("username") or user.get("email") or user.get("phone") or f"用户 {user.get('id')}"
        admin_url = os.getenv("ADMIN_DASHBOARD_URL", "").strip() or "/admin"
        subject = f"【盈航】用户已付款待确认 - {plan_name} ¥{amount:.2f} - 订单号 {order.get('order_no')}"
        text = (
            "有用户提交了次数充值付款信息，请核对到账后再确认入账。\n\n"
            f"订单号：{order.get('order_no')}\n"
            f"用户：{user_label}\n"
            f"手机号/账号：{user.get('phone') or ''}\n"
            f"邮箱：{user.get('email') or ''}\n"
            f"购买次数：{order.get('credits')}\n"
            f"应付金额：¥{amount:.2f}\n"
            f"支付方式：{payment_method}\n"
            f"付款人：{order.get('payer_name') or ''}\n"
            f"付款时间：{order.get('payer_paid_at') or ''}\n"
            f"实付金额：¥{submitted_amount:.2f}\n"
            f"付款备注：{order.get('payer_note') or ''}\n"
            f"管理后台：{admin_url}\n"
        )
        html = _light_email_document(
            f"""
          <h1 style="margin:0 0 20px;color:#1f2328;font-size:24px;line-height:1.35;">用户已付款待确认</h1>
          <p style="margin:0 0 20px;color:#1f2328;line-height:1.7;">请核对到账后，再到管理台确认次数充值。</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>订单号：</strong>{_html_escape(str(order.get('order_no') or ''))}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>用户：</strong>{_html_escape(str(user_label))}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>账号：</strong>{_html_escape(str(user.get('phone') or ''))}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>邮箱：</strong>{_html_escape(str(user.get('email') or ''))}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>购买次数：</strong>{_html_escape(str(order.get('credits') or ''))}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>应付金额：</strong>¥{amount:.2f}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>支付方式：</strong>{_html_escape(payment_method)}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>付款人：</strong>{_html_escape(str(order.get('payer_name') or ''))}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>付款时间：</strong>{_html_escape(str(order.get('payer_paid_at') or ''))}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>实付金额：</strong>¥{submitted_amount:.2f}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>付款备注：</strong>{_html_escape(str(order.get('payer_note') or ''))}</p>
          <p style="margin:20px 0 0;color:#1f2328;"><strong>管理后台：</strong><a href="{_html_escape(admin_url)}" style="color:#0969da;text-decoration:underline;">{_html_escape(admin_url)}</a></p>
        """,
            max_width=640,
        )
        provider = os.getenv("EMAIL_PROVIDER", "smtp").strip().lower() or "smtp"
        if provider in {"log", "debug", "local"}:
            _write_email_debug_log(admin_email, text, None)
            return {"sent": False, "skipped": True, "provider": "log", "email": _mask_email(admin_email), "error": "EMAIL_PROVIDER=log，仅写入本地日志，未真实发送邮件"}
        _send_email_message(admin_email, subject=subject, text=text, html=html)
        return {"sent": True, "provider": provider, "email": _mask_email(admin_email)}
    except Exception as exc:
        return {"sent": False, "error": str(exc)}


def _membership_plans() -> list[dict[str, Any]]:
    plans = []
    for prefix, defaults in (
        ("MONTHLY", MONTHLY_MEMBERSHIP_PLAN),
        ("ANNUAL", ANNUAL_MEMBERSHIP_PLAN),
    ):
        plans.append(
            {
                "id": defaults["id"],
                "plan_name": os.getenv(f"PAYMENT_{prefix}_PLAN_NAME", str(defaults["plan_name"])).strip()
                or str(defaults["plan_name"]),
                "amount_cents": int(
                    os.getenv(f"PAYMENT_{prefix}_AMOUNT_CENTS", str(defaults["amount_cents"]))
                    or str(defaults["amount_cents"])
                ),
                "duration_days": int(
                    os.getenv(f"PAYMENT_{prefix}_DURATION_DAYS", str(defaults["duration_days"]))
                    or str(defaults["duration_days"])
                ),
            }
        )
    return plans


def _membership_plan(plan_id: str = "monthly_membership") -> dict[str, Any]:
    normalized_plan_id = (plan_id or "").strip()
    for plan in _membership_plans():
        if plan["id"] == normalized_plan_id:
            return plan
    raise AuthError("未知的会员套餐", 400)


def _normalize_payment_method(value: str) -> str:
    method = (value or "").strip().lower()
    aliases = {"支付宝": "alipay", "微信": "wechat", "weixin": "wechat"}
    method = aliases.get(method, method)
    if method not in {"alipay", "wechat"}:
        raise AuthError("请选择支付宝或微信付款", 400)
    return method


def _has_active_membership(user: sqlite3.Row | dict[str, Any]) -> bool:
    status = str(user["membership_status"] if "membership_status" in user.keys() else "").strip()
    expires_at = str(user["membership_expires_at"] if "membership_expires_at" in user.keys() else "").strip()
    if status != "active" or not expires_at:
        return False
    try:
        return datetime.fromisoformat(expires_at) > datetime.now(CN_TZ)
    except ValueError:
        return False


def _require_manageable_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    user = _fetch_user_by_id(conn, user_id)
    if user["role"] == "admin":
        raise AuthError("不能操作管理员账号", 403)
    return user


def adjust_user_credits(
    db_path: Path,
    *,
    user_id: int,
    delta: int,
    reason: str,
    request_id: str,
    admin_id: int | None = None,
) -> dict[str, Any]:
    if isinstance(delta, bool) or not isinstance(delta, int):
        raise AuthError("调整次数必须是整数", 400)
    reason = (reason or "").strip()
    request_id = (request_id or "").strip()
    if delta == 0:
        raise AuthError("调整次数不能为 0", 400)
    if abs(delta) > 10000:
        raise AuthError("单次调整次数过大，请拆分后重试", 400)
    if len(reason) < 2:
        raise AuthError("请填写调整次数原因", 400)
    if len(reason) > 300:
        raise AuthError("调整次数原因不能超过 300 字", 400)
    if not CREDIT_GRANT_REQUEST_ID_RE.fullmatch(request_id):
        raise AuthError("request_id 格式无效", 400)

    now = _now()
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM admin_credit_adjustments WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if existing:
            if int(existing["user_id"]) != user_id or int(existing["delta"]) != delta or str(existing["reason"]) != reason:
                raise AuthError("request_id 已用于其他调整请求", 409)
            user = _fetch_user_by_id(conn, user_id)
            return {
                "user": _user_payload(conn, user),
                "delta": int(existing["delta"]),
                "reason": str(existing["reason"]),
                "request_id": str(existing["request_id"]),
                "balance": int(existing["resulting_balance"]),
                "idempotent": True,
            }

        user = _require_manageable_user(conn, user_id)
        balance = _credit_balance(conn, user_id)
        next_balance = balance + delta
        if next_balance < 0:
            raise AuthError("扣减后余额不能小于 0", 400)
        ledger_reason = "admin_grant" if delta > 0 else "admin_deduct"
        related_id = f"admin-adjust:{request_id}"
        _add_credits(conn, user_id, delta, ledger_reason, related_id)
        conn.execute(
            """
            INSERT INTO admin_credit_adjustments (
                request_id, user_id, delta, reason, admin_id, resulting_balance, created_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (request_id, user_id, delta, reason, admin_id, next_balance, now, now),
        )
        refreshed = _fetch_user_by_id(conn, int(user["id"]))
        return {
            "user": _user_payload(conn, refreshed),
            "delta": delta,
            "reason": reason,
            "request_id": request_id,
            "balance": next_balance,
            "idempotent": False,
        }


def grant_user_credits(db_path: Path, *, user_id: int, credits: int, reason: str, admin_id: int | None = None) -> dict[str, Any]:
    credits = int(credits or 0)
    reason = (reason or "").strip()
    if credits <= 0:
        raise AuthError("增加次数必须大于 0", 400)
    if credits > 10000:
        raise AuthError("单次增加次数过大，请分批处理", 400)
    if len(reason) < 2:
        raise AuthError("请填写增加次数的原因", 400)

    with _connect(db_path) as conn:
        user = _fetch_user_by_id(conn, user_id)
        related_id = f"admin:{admin_id or ''};reason:{reason[:100]}"
        _add_credits(conn, user_id, credits, "admin_grant", related_id)
        refreshed = _fetch_user_by_id(conn, int(user["id"]))
        result = {"user": _user_payload(conn, refreshed), "credits_added": credits, "reason": reason}

    result["email_notification"] = notify_credit_added(db_path, user_id=user_id, credits=credits, reason=reason)
    return result


def grant_credits_to_all_users(
    db_path: Path,
    *,
    credits: int,
    reason: str,
    request_id: str,
    admin_id: int | None = None,
) -> dict[str, Any]:
    """Atomically grant credits to the users present when this campaign starts."""
    if isinstance(credits, bool) or not isinstance(credits, int):
        raise AuthError("增加次数必须是正整数", 400)
    if credits <= 0:
        raise AuthError("增加次数必须大于 0", 400)
    if credits > 10000:
        raise AuthError("单次增加次数过大，请分批处理", 400)
    reason = (reason or "").strip()
    if len(reason) < 2:
        raise AuthError("请填写增加次数的原因", 400)
    if len(reason) > 300:
        raise AuthError("增加次数的原因不能超过 300 个字", 400)
    request_id = (request_id or "").strip()
    if not CREDIT_GRANT_REQUEST_ID_RE.fullmatch(request_id):
        raise AuthError("request_id 格式无效", 400)

    now = _now()
    with _connect(db_path) as conn:
        inserted = conn.execute(
            """
            INSERT OR IGNORE INTO credit_grant_campaigns (
                request_id, credits, reason, status, eligible_count, granted_count,
                created_by, created_at
            ) VALUES (?, ?, ?, 'pending', 0, 0, ?, ?)
            """,
            (request_id, credits, reason, admin_id, now),
        ).rowcount
        campaign = conn.execute(
            "SELECT * FROM credit_grant_campaigns WHERE request_id = ?", (request_id,)
        ).fetchone()
        if not campaign:
            raise AuthError("批量增加次数任务创建失败", 500)
        if not inserted:
            if int(campaign["credits"]) != credits or str(campaign["reason"]) != reason:
                raise AuthError("request_id 已用于其他批量增加次数任务", 409)
            return {"campaign": _credit_grant_campaign_payload(campaign), "idempotent": True}

        user_rows = conn.execute("SELECT id FROM users ORDER BY id").fetchall()
        campaign_id = int(campaign["id"])
        related_id = f"credit-campaign:{campaign_id}"
        for user in user_rows:
            _add_credits(conn, int(user["id"]), credits, "admin_grant_all", related_id)
        affected = len(user_rows)
        conn.execute(
            """
            UPDATE credit_grant_campaigns
            SET status = 'completed', eligible_count = ?, granted_count = ?, completed_at = ?
            WHERE id = ?
            """,
            (affected, affected, now, campaign_id),
        )
        completed = conn.execute(
            "SELECT * FROM credit_grant_campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()
        return {"campaign": _credit_grant_campaign_payload(completed), "idempotent": False}


def normalize_phone(phone: str) -> str:
    phone = re.sub(r"\D", "", phone or "")
    if not PHONE_RE.match(phone):
        raise AuthError("请输入有效的中国大陆手机号", 400)
    return phone


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise AuthError("请输入有效邮箱地址", 400)
    return email


def normalize_username(username: str) -> str:
    username = (username or "").strip()
    if not USERNAME_RE.match(username):
        raise AuthError("账号名需以字母开头，4-32 位，仅支持字母、数字和下划线", 400)
    return username


def _validate_registration_agreement(accepted: object, version: object) -> None:
    if accepted is not True:
        raise AuthError("请完整阅读并同意用户注册协议、投资风险揭示书及 AI 服务免责声明", 400)
    if version != REGISTRATION_AGREEMENT_VERSION:
        raise AuthError("协议版本已更新，请重新打开协议并阅读确认", 409)


def _normalize_sms_purpose(purpose: str) -> str:
    value = (purpose or "login").strip().lower()
    return value if value in {"login"} else "login"


def _normalize_email_purpose(purpose: str) -> str:
    value = (purpose or "register").strip().lower()
    return value if value in {"register", "bind_email"} else "register"


def _invalidated_session_reason(conn: sqlite3.Connection, token: str) -> str:
    row = conn.execute(
        "SELECT reason FROM invalidated_sessions WHERE token = ?",
        (token,),
    ).fetchone()
    return str(row["reason"] or "") if row else ""


def get_current_user(db_path: Path, token: str) -> dict[str, Any] | None:
    if not token:
        return None
    with _connect(db_path) as conn:
        row = _session_user_row_strict(conn, token)
        if not row or row["status"] != "active":
            return None
        return _user_payload(conn, row)


def require_user(db_path: Path, token: str) -> dict[str, Any]:
    if not token:
        raise AuthError("请先登录后再使用", 401)
    with _connect(db_path) as conn:
        row = _session_user_row_strict(conn, token)
        if not row:
            if _invalidated_session_reason(conn, token) == "disabled":
                raise AuthError("账号已暂停，请联系管理员", 403)
            raise AuthError("请先登录后再使用", 401)
        if row["status"] != "active":
            raise AuthError("账号已暂停，请联系管理员", 403)
        return _user_payload(conn, row)


def require_admin(db_path: Path, token: str) -> dict[str, Any]:
    user = require_user(db_path, token)
    if user.get("role") != "admin":
        raise AuthError("需要管理员权限", 403)
    return user


def set_user_status(
    db_path: Path,
    *,
    user_id: int,
    status: str,
    admin_id: int | None = None,
    expected_identity: str = "",
) -> dict[str, Any]:
    normalized_status = (status or "").strip().lower()
    if normalized_status not in {"active", "disabled"}:
        raise AuthError("用户状态仅支持 active 或 disabled", 400)
    now = _now()
    with _connect(db_path) as conn:
        user = _require_manageable_user(conn, user_id)
        actual_identity = str(user["username"] or user["email"] or user["phone"] or f"用户 #{user_id}").strip()
        expected_identity = str(expected_identity or "").strip()
        if expected_identity and expected_identity.casefold() != actual_identity.casefold():
            raise AuthError("目标用户信息已变化，请刷新列表后重试", 409)
        if user["status"] != normalized_status:
            conn.execute("UPDATE users SET status = ? WHERE id = ?", (normalized_status, user_id))
        if normalized_status == "disabled":
            tokens = [
                str(row["token"])
                for row in conn.execute("SELECT token FROM sessions WHERE user_id = ?", (user_id,)).fetchall()
            ]
            for token in tokens:
                conn.execute(
                    """
                    INSERT INTO invalidated_sessions (token, user_id, reason, created_at)
                    VALUES (?, ?, 'disabled', ?)
                    ON CONFLICT(token) DO UPDATE SET reason = excluded.reason, created_at = excluded.created_at
                    """,
                    (token, user_id, now),
                )
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        refreshed = _fetch_user_by_id(conn, user_id)
        return {
            "user": {
                "id": int(refreshed["id"]),
                "username": str(refreshed["username"] or ""),
                "email": str(refreshed["email"] or ""),
                "phone": str(refreshed["phone"] or ""),
                "display_name": actual_identity,
                "status": str(refreshed["status"]),
                "credits": _credit_balance(conn, user_id),
            },
            "admin_id": admin_id,
        }

@contextmanager
def _connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _ensure_admin(conn: sqlite3.Connection) -> None:
    phone = os.getenv("ADMIN_PHONE", "").strip()
    password = os.getenv("ADMIN_PASSWORD", "").strip()
    if not phone or not password:
        return
    salt, password_hash = _hash_password(password)
    row = conn.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
    if row:
        conn.execute(
            """
            UPDATE users
            SET username = COALESCE(username, ?),
                password_hash = ?,
                password_salt = ?,
                role = 'admin',
                status = 'active'
            WHERE id = ?
            """,
            (phone, password_hash, salt, row["id"]),
        )
        return
    conn.execute(
        """
        INSERT INTO users (phone, username, password_hash, password_salt, role, invite_code, created_at)
        VALUES (?, ?, ?, ?, 'admin', ?, ?)
        """,
        (phone, phone, password_hash, salt, _new_invite_code(conn), _now()),
    )


def _validate_password(password: str) -> None:
    if len(password or "") < 8:
        raise AuthError("密码至少需要 8 位", 400)


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 180_000)
    return salt, digest.hex()


def _verify_password(password: str, salt: str, expected_hash: str) -> bool:
    _, actual = _hash_password(password, salt)
    return hmac.compare_digest(actual, expected_hash)


def _hash_sms_code(phone: str, code: str) -> str:
    secret = os.getenv("SMS_CODE_SECRET", "ai-trade-local-sms-secret")
    payload = f"{phone}:{code}:{secret}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _hash_email_code(email: str, code: str) -> str:
    secret = os.getenv("EMAIL_CODE_SECRET", os.getenv("SMS_CODE_SECRET", "ai-trade-local-email-secret"))
    payload = f"{email}:{code}:{secret}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _verify_sms_code(conn: sqlite3.Connection, phone: str, code: str, *, purpose: str) -> None:
    code = re.sub(r"\D", "", code or "")
    if len(code) != 6:
        raise AuthError("请输入 6 位短信验证码", 400)
    now = _now()
    row = conn.execute(
        """
        SELECT *
        FROM sms_codes
        WHERE phone = ? AND purpose = ? AND consumed = 0
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (phone, purpose),
    ).fetchone()
    if not row:
        raise AuthError("请先获取短信验证码", 400)
    if row["expires_at"] <= now:
        raise AuthError("验证码已过期，请重新获取", 400)
    if not hmac.compare_digest(row["code_hash"], _hash_sms_code(phone, code)):
        raise AuthError("验证码不正确", 401)
    conn.execute("UPDATE sms_codes SET consumed = 1 WHERE id = ?", (row["id"],))


def _verify_email_code(conn: sqlite3.Connection, email: str, code: str, *, purpose: str) -> None:
    code = re.sub(r"\D", "", code or "")
    if len(code) != 6:
        raise AuthError("请输入 6 位邮箱验证码", 400)
    now = _now()
    row = conn.execute(
        """
        SELECT *
        FROM email_codes
        WHERE email = ? AND purpose = ? AND consumed = 0
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (email, purpose),
    ).fetchone()
    if not row:
        raise AuthError("请先获取邮箱验证码", 400)
    if row["expires_at"] <= now:
        raise AuthError("邮箱验证码已过期，请重新获取", 400)
    if not hmac.compare_digest(row["code_hash"], _hash_email_code(email, code)):
        raise AuthError("邮箱验证码不正确", 401)
    conn.execute("UPDATE email_codes SET consumed = 1 WHERE id = ?", (row["id"],))


def _send_sms_code(phone: str, code: str, log_path: Path | None) -> dict[str, str]:
    provider = os.getenv("SMS_PROVIDER", "log").strip().lower() or "log"
    if provider in {"log", "debug", "local"}:
        _write_sms_debug_log(phone, code, log_path)
        return {"provider": "log", "debug_code": code}
    if provider == "aliyun":
        # Hook point for a production Aliyun SMS integration. Keep this explicit so
        # local deployments do not silently pretend to send paid SMS messages.
        raise AuthError("SMS_PROVIDER=aliyun 尚未配置发送实现，请先接入短信服务商 SDK 或 HTTP API", 501)
    raise AuthError(f"不支持的短信服务商：{provider}", 500)


def _send_email_code(email: str, code: str, log_path: Path | None) -> dict[str, str]:
    provider = os.getenv("EMAIL_PROVIDER", "smtp").strip().lower() or "smtp"
    if provider in {"log", "debug", "local"}:
        _write_email_debug_log(email, code, log_path)
        raise AuthError("邮箱验证码本地测试模式已关闭，请配置 EMAIL_PROVIDER=smtp 和 SMTP 邮件服务后发送。", 500)
    if provider in {"smtp", "outlook_graph"}:
        _send_smtp_email(email, code)
        return {"provider": provider}
    raise AuthError(f"不支持的邮件服务商：{provider}", 500)


def _send_smtp_email(email: str, code: str) -> None:
    subject = "盈航登录注册验证码"
    text = f"你的盈航验证码是：{code}\n\n验证码 {EMAIL_CODE_TTL_MINUTES} 分钟内有效。若不是你本人操作，请忽略这封邮件。\n"
    html = _light_email_document(f"""
      <h1 style="margin:0 0 20px;color:#1f2328;font-size:24px;line-height:1.35;">盈航验证码</h1>
      <p style="margin:0 0 12px;color:#1f2328;line-height:1.7;">你的验证码是：</p>
      <p style="margin:0 0 20px;color:#1f2328;font-size:32px;line-height:1.3;letter-spacing:6px;font-weight:700;">{_html_escape(code)}</p>
      <p style="margin:0;color:#1f2328;line-height:1.7;">验证码 {EMAIL_CODE_TTL_MINUTES} 分钟内有效。若不是你本人操作，请忽略这封邮件。</p>
    """, max_width=520)
    _send_email_message(email, subject=subject, text=text, html=html)


def notify_credit_added(db_path: Path, *, user_id: int, credits: int, reason: str) -> dict[str, Any]:
    try:
        with _connect(db_path) as conn:
            user = _fetch_user_by_id(conn, user_id)
            email = str(user["email"] if "email" in user.keys() else "").strip()
            username = str(user["username"] if "username" in user.keys() else "").strip() or "用户"
            balance = _credit_balance(conn, user_id)
        if not email:
            return {"sent": False, "skipped": True, "error": "用户未绑定邮箱"}
        reason = (reason or "平台为你增加了使用次数").strip()
        text = (
            f"{username}，你好：\n\n"
            f"你的盈航账号已增加 {credits} 次使用机会。\n"
            f"增加原因：{reason}\n"
            f"当前剩余次数：{balance} 次。\n\n"
            "如有疑问，请联系平台管理员。\n"
        )
        html = _light_email_document(f"""
          <h1 style="margin:0 0 20px;color:#1f2328;font-size:24px;line-height:1.35;">盈航使用次数已增加</h1>
          <p style="margin:0 0 16px;color:#1f2328;line-height:1.7;">{_html_escape(username)}，你好：</p>
          <p style="margin:0 0 16px;color:#1f2328;line-height:1.7;">你的盈航账号已增加 <strong style="color:#1f2328;font-size:20px;">{credits}</strong> 次使用机会。</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>增加原因：</strong>{_html_escape(reason)}</p>
          <p style="margin:8px 0;color:#1f2328;"><strong>当前剩余次数：</strong>{balance} 次。</p>
          <p style="margin:20px 0 0;color:#57606a;font-size:13px;line-height:1.6;">如有疑问，请联系平台管理员。</p>
        """, max_width=560)
        _send_email_message(email, subject="盈航使用次数已增加", text=text, html=html)
        return {"sent": True, "email": _mask_email(email)}
    except Exception as exc:
        return {"sent": False, "error": str(exc)}


def _smtp_message(
    email: str,
    *,
    subject: str,
    text: str,
    html: str | None = None,
    message_id: str = "",
    sender: str = "",
) -> EmailMessage:
    sender = sender.strip() or os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "")).strip()
    sender_name = os.getenv("SMTP_FROM_NAME", "盈航").strip()
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{sender_name} <{sender}>"
    message["To"] = email
    if message_id:
        clean_id = re.sub(r"[^A-Za-z0-9._-]", "-", message_id).strip("-")[:180]
        sender_domain = sender.rsplit("@", 1)[-1] if "@" in sender else "localhost"
        message["Message-ID"] = f"<{clean_id}@{sender_domain}>"
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    return message


def _smtp_connection_settings() -> tuple[str, int, str, str, str, bool]:
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "465").strip() or "465")
    username = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    sender = os.getenv("SMTP_FROM", username).strip()
    if not host or not username or not password or not sender:
        raise AuthError("SMTP 邮件服务未配置完整，请检查 SMTP_HOST/SMTP_USER/SMTP_PASSWORD/SMTP_FROM", 500)
    use_ssl = os.getenv("SMTP_USE_SSL", "1").strip().lower() not in {"0", "false", "no"}
    return host, port, username, password, sender, use_ssl


class UpdateEmailSMTPSession:
    """A single worker's reusable SMTP connection.

    Each message still has exactly one ``To`` recipient. If the connection becomes
    unusable, it is discarded and the message is retried once on a fresh connection;
    the persistent delivery retry policy remains handled by ``process_next_update_email``.
    """

    _cooldown_lock = threading.Lock()
    _cooldown_until = 0.0

    def __init__(self) -> None:
        self._server: smtplib.SMTP | smtplib.SMTP_SSL | None = None

    @classmethod
    def _disconnect_cooldown_seconds(cls) -> float:
        try:
            configured = float(os.getenv("SMTP_DISCONNECT_COOLDOWN_SECONDS", "15"))
        except ValueError:
            configured = 15.0
        return max(0.0, min(configured, 300.0))

    @classmethod
    def _wait_for_disconnect_cooldown(cls) -> None:
        with cls._cooldown_lock:
            delay = max(0.0, cls._cooldown_until - time.monotonic())
        if delay:
            time.sleep(delay)

    @classmethod
    def _record_disconnect(cls) -> None:
        cooldown = cls._disconnect_cooldown_seconds()
        if not cooldown:
            return
        deadline = time.monotonic() + cooldown
        with cls._cooldown_lock:
            cls._cooldown_until = max(cls._cooldown_until, deadline)

    def _connect(self) -> smtplib.SMTP | smtplib.SMTP_SSL:
        self._wait_for_disconnect_cooldown()
        host, port, username, password, _sender, use_ssl = _smtp_connection_settings()
        if use_ssl:
            server: smtplib.SMTP | smtplib.SMTP_SSL = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls()
        server.login(username, password)
        self._server = server
        return server

    def send(
        self,
        email: str,
        *,
        subject: str,
        text: str,
        html: str | None = None,
        message_id: str = "",
    ) -> None:
        provider = os.getenv("EMAIL_PROVIDER", "smtp").strip().lower() or "smtp"
        if provider == "outlook_graph":
            sender = os.getenv("OUTLOOK_GRAPH_FROM", "").strip()
            if not sender:
                raise AuthError("OUTLOOK_GRAPH_FROM 未配置", 500)
            message = _smtp_message(
                email,
                subject=subject,
                text=text,
                html=html,
                message_id=message_id,
                sender=sender,
            )
            send_outlook_mime(message.as_bytes())
            return
        if provider != "smtp":
            raise AuthError(f"不支持的邮件服务商：{provider}", 500)
        message = _smtp_message(email, subject=subject, text=text, html=html, message_id=message_id)
        for reconnect_attempt in range(2):
            try:
                server = self._server or self._connect()
                server.send_message(message)
                return
            except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, OSError, EOFError):
                self.close()
                self._record_disconnect()
                if reconnect_attempt:
                    raise

    def send_update_notice(self, delivery: dict[str, Any]) -> None:
        _send_update_notice_email(delivery, smtp_session=self)

    def close(self) -> None:
        server, self._server = self._server, None
        if server is None:
            return
        try:
            server.quit()
        except Exception:
            try:
                server.close()
            except Exception:
                pass


def _send_smtp_message(
    email: str,
    *,
    subject: str,
    text: str,
    html: str | None = None,
    message_id: str = "",
) -> None:
    host, port, username, password, _sender, use_ssl = _smtp_connection_settings()

    message = _smtp_message(email, subject=subject, text=text, html=html, message_id=message_id)

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=15) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(message)


def _send_email_message(
    email: str,
    *,
    subject: str,
    text: str,
    html: str | None = None,
    message_id: str = "",
) -> None:
    provider = os.getenv("EMAIL_PROVIDER", "smtp").strip().lower() or "smtp"
    if provider == "smtp":
        _send_smtp_message(email, subject=subject, text=text, html=html, message_id=message_id)
        return
    if provider == "outlook_graph":
        sender = os.getenv("OUTLOOK_GRAPH_FROM", "").strip()
        if not sender:
            raise AuthError("OUTLOOK_GRAPH_FROM 未配置", 500)
        message = _smtp_message(
            email,
            subject=subject,
            text=text,
            html=html,
            message_id=message_id,
            sender=sender,
        )
        send_outlook_mime(message.as_bytes())
        return
    raise AuthError(f"不支持的邮件服务商：{provider}", 500)


def send_email_provider_test(email: str) -> dict[str, Any]:
    recipient = email.strip().lower()
    if not EMAIL_RE.fullmatch(recipient):
        raise AuthError("测试收件邮箱格式不正确", 400)
    provider = os.getenv("EMAIL_PROVIDER", "smtp").strip().lower() or "smtp"
    if provider not in {"smtp", "outlook_graph"}:
        raise AuthError("当前邮件服务商不支持真实测试发送", 400)
    text = "这是一封来自盈航邮件管理后台的发件通道测试邮件。收到此邮件说明当前邮件服务配置有效。"
    html = _light_email_document(
        """
        <h1 style="margin:0 0 20px;color:#1f2328;font-size:24px;line-height:1.35;">盈航邮件通道测试</h1>
        <p style="margin:0;color:#1f2328;line-height:1.7;">这是一封来自盈航邮件管理后台的发件通道测试邮件。收到此邮件说明当前邮件服务配置有效。</p>
        """,
        max_width=560,
    )
    _send_email_message(recipient, subject="盈航邮件通道测试", text=text, html=html)
    return {"sent": True, "provider": provider, "email": _mask_email(recipient)}


def _html_escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _light_email_document(content_html: str, *, max_width: int = 640) -> str:
    """Wrap HTML email content in a conservative, explicitly light document."""
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <meta name="color-scheme" content="light">
    <meta name="supported-color-schemes" content="light">
    <style>:root {{ color-scheme: light; supported-color-schemes: light; }}</style>
  </head>
  <body bgcolor="#ffffff" style="margin:0;padding:0;background-color:#ffffff;color:#1f2328;font-family:Arial,'Microsoft YaHei',sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#ffffff" style="width:100%;background-color:#ffffff;color:#1f2328;">
      <tr>
        <td align="center" bgcolor="#ffffff" style="padding:24px 16px;background-color:#ffffff;color:#1f2328;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#ffffff" style="width:100%;max-width:{int(max_width)}px;background-color:#ffffff;color:#1f2328;">
            <tr>
              <td bgcolor="#ffffff" style="padding:0;background-color:#ffffff;color:#1f2328;font-size:16px;line-height:1.6;">
                {content_html}
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not domain:
        return email[:2] + "***"
    return f"{local[:2]}***@{domain}"


def _write_sms_debug_log(phone: str, code: str, log_path: Path | None) -> None:
    path = log_path or Path("work/sms_codes.log")
    path.parent.mkdir(parents=True, exist_ok=True)
    masked = f"{phone[:3]}****{phone[-4:]}"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{_now()} phone={masked} code={code}\n")


def _write_email_debug_log(email: str, code: str, log_path: Path | None) -> None:
    path = log_path or Path("work/email_codes.log")
    path.parent.mkdir(parents=True, exist_ok=True)
    local, _, domain = email.partition("@")
    masked = f"{local[:2]}***@{domain}"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{_now()} email={masked} code={code}\n")


def _new_invite_code(conn: sqlite3.Connection) -> str:
    for _ in range(20):
        code = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8].upper()
        if not conn.execute("SELECT id FROM users WHERE invite_code = ?", (code,)).fetchone():
            return code
    raise AuthError("邀请码生成失败，请重试", 500)


def _create_session(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now_dt = datetime.now(CN_TZ)
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (token, user_id, (now_dt + timedelta(days=SESSION_DAYS)).isoformat(), now_dt.isoformat()),
    )
    return token


def _fetch_user_by_phone(conn: sqlite3.Connection, phone: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()


def _fetch_user_by_username(conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def _fetch_user_by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def _fetch_user_by_login_account(conn: sqlite3.Connection, account: str) -> sqlite3.Row | None:
    if EMAIL_RE.match(account):
        return _fetch_user_by_email(conn, normalize_email(account))
    if account.isdigit():
        return _fetch_user_by_phone(conn, account)
    admin_phone = os.getenv("ADMIN_PHONE", "admin").strip()
    return _fetch_user_by_phone(conn, account) if account == admin_phone else _fetch_user_by_username(conn, account)


def _fetch_user_by_id(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise AuthError("用户不存在", 404)
    return row


def _fetch_user_by_invite_code(conn: sqlite3.Connection, invite_code: str) -> sqlite3.Row | None:
    if not invite_code:
        return None
    return conn.execute("SELECT * FROM users WHERE invite_code = ?", (invite_code.upper(),)).fetchone()


def _ip_registered_user(conn: sqlite3.Connection, ip: str) -> sqlite3.Row | None:
    if not ip:
        return None
    return conn.execute("SELECT * FROM users WHERE role = 'user' AND register_ip = ? LIMIT 1", (ip,)).fetchone()


def _feature_credit_cost(feature: str) -> int:
    return max(1, int(FEATURE_CREDIT_COSTS.get(str(feature or "").strip(), 1)))


def _add_credits(conn: sqlite3.Connection, user_id: int, delta: int, reason: str, related_id: str | None) -> None:
    conn.execute(
        "INSERT INTO credit_ledger (user_id, delta, reason, related_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, delta, reason, related_id, _now()),
    )


def _credit_balance(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute("SELECT COALESCE(SUM(delta), 0) AS balance FROM credit_ledger WHERE user_id = ?", (user_id,)).fetchone()
    return int(row["balance"] if row else 0)


def _record_usage(
    conn: sqlite3.Connection,
    user_id: int,
    feature: str,
    credits_spent: int,
    status: str,
    ip: str,
    related_id: str,
) -> None:
    conn.execute(
        """
        INSERT INTO usage_events (user_id, feature, credits_spent, status, related_id, ip, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, feature, credits_spent, status, related_id, ip, _now()),
    )


def _feature_charge_exists(conn: sqlite3.Connection, user_id: int, feature: str, related_id: str) -> bool:
    row = conn.execute(
        """
        SELECT id
        FROM usage_events
        WHERE user_id = ?
          AND feature = ?
          AND related_id = ?
          AND status IN ('charged', 'admin_free', 'membership_free')
        LIMIT 1
        """,
        (user_id, feature, related_id),
    ).fetchone()
    return row is not None


def _user_payload(conn: sqlite3.Connection, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    user_id = int(row["id"])
    referral_count = conn.execute(
        "SELECT COUNT(*) AS count FROM referrals WHERE referrer_user_id = ? AND status = 'completed'",
        (user_id,),
    ).fetchone()["count"]
    membership_expires_at = row["membership_expires_at"] if "membership_expires_at" in row.keys() else ""
    membership_active = _has_active_membership(row)
    email_verified = bool(row["email_verified"]) if "email_verified" in row.keys() else False
    email_binding_required = row["role"] != "admin" and not email_verified
    return {
        "id": user_id,
        "phone": row["phone"],
        "username": row["username"] if "username" in row.keys() else "",
        "email": row["email"] if "email" in row.keys() else "",
        "email_verified": email_verified,
        "email_binding_required": email_binding_required,
        "update_emails_enabled": bool(row["update_emails_enabled"]) if "update_emails_enabled" in row.keys() else True,
        "role": row["role"],
        "invite_code": row["invite_code"],
        "credits": _credit_balance(conn, user_id),
        "membership_plan": row["membership_plan"] if "membership_plan" in row.keys() else "",
        "membership_status": "active" if membership_active else (row["membership_status"] if "membership_status" in row.keys() else ""),
        "membership_expires_at": membership_expires_at,
        "membership_active": membership_active,
        "referral_count": int(referral_count),
        "created_at": row["created_at"],
    }


def _feedback_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "phone": row["phone"] if "phone" in row.keys() else "",
        "category": row["category"],
        "content": row["content"],
        "contact": row["contact"],
        "status": row["status"],
        "reward_credits": row["reward_credits"],
        "admin_note": row["admin_note"],
        "created_at": row["created_at"],
        "reviewed_at": row["reviewed_at"],
    }


def _credit_grant_campaign_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "request_id": str(row["request_id"]),
        "credits": int(row["credits"]),
        "reason": str(row["reason"]),
        "status": str(row["status"]),
        "eligible_count": int(row["eligible_count"]),
        "granted_count": int(row["granted_count"]),
        "created_by": int(row["created_by"]) if row["created_by"] is not None else None,
        "created_at": str(row["created_at"]),
        "completed_at": str(row["completed_at"] or ""),
    }


def _update_notice_rows(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM update_notices
        ORDER BY COALESCE(published_at, updated_at, created_at) DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def _update_notice_payload(row: sqlite3.Row, *, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    try:
        items = json.loads(row["items_json"] or "[]")
    except Exception:
        items = []
    if not isinstance(items, list):
        items = []
    payload = {
        "id": row["id"],
        "title": row["title"],
        "version": row["version"],
        "items": [str(item) for item in items if str(item).strip()],
        "summary": row["summary"] if "summary" in row.keys() else "",
        "content_markdown": row["content_markdown"] if "content_markdown" in row.keys() else "",
        "status": row["status"],
        "audience": row["audience"] if "audience" in row.keys() else "registered_users",
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "published_at": row["published_at"],
        "expires_at": row["expires_at"] if "expires_at" in row.keys() else None,
    }
    if conn is not None:
        campaign = conn.execute(
            "SELECT id FROM update_email_campaigns WHERE notice_id = ? ORDER BY id DESC LIMIT 1",
            (row["id"],),
        ).fetchone()
        payload["email_campaign"] = _email_campaign_payload(conn, int(campaign["id"])) if campaign else None
    return payload


def _create_update_email_campaign(
    conn: sqlite3.Connection, *, notice_id: int, request_id: str, admin_id: int | None
) -> dict[str, Any]:
    existing = conn.execute("SELECT id, notice_id FROM update_email_campaigns WHERE request_id = ?", (request_id,)).fetchone()
    if existing:
        if int(existing["notice_id"]) != int(notice_id):
            raise AuthError("request_id 已用于其他更新公告", 409)
        return _email_campaign_payload(conn, int(existing["id"]))
    now = _now()
    campaign_id = int(
        conn.execute(
            "INSERT INTO update_email_campaigns (notice_id, request_id, status, created_by, created_at) VALUES (?, ?, 'pending', ?, ?)",
            (notice_id, request_id, admin_id, now),
        ).lastrowid
    )
    users = conn.execute(
        """
        SELECT id, email, email_verified, update_emails_enabled
        FROM users
        WHERE role = 'user'
        ORDER BY id
        """
    ).fetchall()
    for user in users:
        email = str(user["email"] or "").strip().lower()
        eligible = bool(email and int(user["email_verified"] or 0) == 1 and int(user["update_emails_enabled"] or 0) == 1)
        reason = None
        if not eligible:
            reason = "邮箱未验证或用户已关闭产品更新邮件"
        conn.execute(
            """
            INSERT INTO update_email_deliveries (
                campaign_id, user_id, email, status, attempt_count, next_attempt_at, last_error, updated_at
            ) VALUES (?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (campaign_id, user["id"], email, "pending" if eligible else "skipped", now if eligible else None, reason, now),
        )
    _refresh_email_campaign_status(conn, campaign_id)
    return _email_campaign_payload(conn, campaign_id)


def _email_campaign_payload(conn: sqlite3.Connection, campaign_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM update_email_campaigns WHERE id = ?", (campaign_id,)).fetchone()
    if not row:
        raise AuthError("邮件推送任务不存在", 404)
    counts = {str(item["status"]): int(item["count"]) for item in conn.execute(
        "SELECT status, COUNT(*) AS count FROM update_email_deliveries WHERE campaign_id = ? GROUP BY status",
        (campaign_id,),
    ).fetchall()}
    return {
        "id": int(row["id"]),
        "notice_id": int(row["notice_id"]),
        "request_id": row["request_id"],
        "status": row["status"],
        "total": sum(counts.values()),
        "pending": counts.get("pending", 0),
        "sending": counts.get("sending", 0),
        "sent": counts.get("sent", 0),
        "failed": counts.get("failed", 0),
        "skipped": counts.get("skipped", 0),
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


def _refresh_email_campaign_status(conn: sqlite3.Connection, campaign_id: int) -> None:
    counts = {str(row["status"]): int(row["count"]) for row in conn.execute(
        "SELECT status, COUNT(*) AS count FROM update_email_deliveries WHERE campaign_id = ? GROUP BY status",
        (campaign_id,),
    ).fetchall()}
    if counts.get("sending"):
        status, finished = "sending", None
    elif counts.get("pending"):
        status, finished = "pending", None
    elif counts.get("failed"):
        status, finished = ("partial_failed" if counts.get("sent") else "failed"), _now()
    else:
        status, finished = "completed", _now()
    conn.execute(
        "UPDATE update_email_campaigns SET status = ?, finished_at = ? WHERE id = ?",
        (status, finished, campaign_id),
    )


def _pending_delivery_next_retry_at(
    conn: sqlite3.Connection,
    *,
    delivery_table: str,
    campaign_id: int,
) -> str | None:
    row = conn.execute(
        f"""
        SELECT MIN(next_attempt_at) AS next_retry_at
        FROM {delivery_table}
        WHERE campaign_id = ?
          AND status = 'pending'
          AND COALESCE(next_attempt_at, '') != ''
        """,
        (campaign_id,),
    ).fetchone()
    value = row["next_retry_at"] if row else None
    return str(value) if value else None


def _permanent_email_failure_count(
    conn: sqlite3.Connection,
    *,
    delivery_table: str,
    campaign_id: int,
) -> int:
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM {delivery_table}
        WHERE campaign_id = ? AND status = 'failed' AND last_error LIKE ?
        """,
        (campaign_id, f"{PERMANENT_EMAIL_ERROR_PREFIX}%"),
    ).fetchone()
    return int(row["count"] if row else 0)


def _daily_top5_email_campaign_payload(conn: sqlite3.Connection, campaign_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM daily_top5_email_campaigns WHERE id = ?", (campaign_id,)
    ).fetchone()
    if not row:
        raise AuthError("每日 TOP5 邮件任务不存在", 404)
    counts = {
        str(item["status"]): int(item["count"])
        for item in conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM daily_top5_email_deliveries
            WHERE campaign_id = ?
            GROUP BY status
            """,
            (campaign_id,),
        ).fetchall()
    }
    variants = {
        str(item["content_variant"]): int(item["count"])
        for item in conn.execute(
            """
            SELECT content_variant, COUNT(*) AS count
            FROM daily_top5_email_deliveries
            WHERE campaign_id = ? AND status != 'skipped'
            GROUP BY content_variant
            """,
            (campaign_id,),
        ).fetchall()
    }
    permanent_failed = _permanent_email_failure_count(
        conn,
        delivery_table="daily_top5_email_deliveries",
        campaign_id=campaign_id,
    )
    failed = counts.get("failed", 0)
    return {
        "id": int(row["id"]),
        "trade_date": str(row["trade_date"]),
        "report_id": str(row["report_id"]),
        "status": str(row["status"]),
        "total": sum(counts.values()),
        "pending": counts.get("pending", 0),
        "sending": counts.get("sending", 0),
        "sent": counts.get("sent", 0),
        "failed": failed,
        "permanent_failed": permanent_failed,
        "retryable_failed": max(0, failed - permanent_failed),
        "skipped": counts.get("skipped", 0),
        "full": variants.get("full", 0),
        "teaser": variants.get("teaser", 0),
        "next_retry_at": _pending_delivery_next_retry_at(
            conn,
            delivery_table="daily_top5_email_deliveries",
            campaign_id=campaign_id,
        ),
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


def _daily_top5_close_email_campaign_payload(conn: sqlite3.Connection, campaign_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM daily_top5_close_email_campaigns WHERE id = ?", (campaign_id,)
    ).fetchone()
    if not row:
        raise AuthError("每日 TOP5 收盘邮件任务不存在", 404)
    counts = {
        str(item["status"]): int(item["count"])
        for item in conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM daily_top5_close_email_deliveries
            WHERE campaign_id = ?
            GROUP BY status
            """,
            (campaign_id,),
        ).fetchall()
    }
    close_snapshot = _load_daily_top5_close_report_json(row["close_report_json"])
    return {
        "id": int(row["id"]),
        "trade_date": str(row["trade_date"]),
        "report_id": str(row["report_id"]),
        "status": str(row["status"]),
        "calculation_status": str(row["calculation_status"] or "pending"),
        "calculation_attempt_count": int(row["calculation_attempt_count"] or 0),
        "calculation_due_at": str(row["calculation_due_at"] or ""),
        "calculation_ready_at": str(row["calculation_ready_at"] or ""),
        "calculation_last_error": str(row["calculation_last_error"] or ""),
        "total": sum(counts.values()),
        "pending": counts.get("pending", 0),
        "sending": counts.get("sending", 0),
        "sent": counts.get("sent", 0),
        "failed": counts.get("failed", 0),
        "skipped": counts.get("skipped", 0),
        "full": sum(counts.values()) - counts.get("skipped", 0),
        "teaser": 0,
        "next_retry_at": _pending_delivery_next_retry_at(
            conn,
            delivery_table="daily_top5_close_email_deliveries",
            campaign_id=campaign_id,
        ) or str(row["next_calculation_at"] or ""),
        "quote_time": str(close_snapshot.get("quote_time") or ""),
        "created_at": str(row["created_at"]),
        "started_at": str(row["started_at"] or ""),
        "finished_at": str(row["finished_at"] or ""),
    }


def _load_daily_top5_close_report_json(value: object) -> dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _daily_top5_close_calculation_failure_message(
    issues: list[dict[str, str]] | None = None,
    *,
    prefix: str = "quote_missing",
    fallback: str = "收盘行情尚未齐备",
) -> str:
    detail = "；".join(
        f"{item.get('name') or item.get('code') or '-'}:{item.get('reason') or prefix}"
        for item in (issues or [])
    )[:500]
    return f"{prefix}: {detail}" if detail else fallback


def _has_complete_daily_top5_stocks(value: object) -> bool:
    required_fields = ("name", "code", "theme", "today_open_change", "reason", "observe_after_930")
    if not isinstance(value, list) or len(value) != 5:
        return False
    for stock in value:
        if not isinstance(stock, dict):
            return False
        try:
            rank = int(stock.get("rank"))
        except (TypeError, ValueError):
            return False
        if rank <= 0 or any(not str(stock.get(field) or "").strip() for field in required_fields):
            return False
    return True


def _has_complete_daily_top5_conclusion(conclusion: dict[str, Any]) -> bool:
    fields = (
        "strongest_stock_at_925",
        "strongest_theme_cluster",
        "most_over_expected_stock",
        "best_capacity_confirmation",
        "biggest_negative_feedback",
        "one_sentence_for_930",
    )
    return all(str(conclusion.get(field) or "").strip() for field in fields)


def _refresh_daily_top5_email_campaign_status(conn: sqlite3.Connection, campaign_id: int) -> None:
    counts = {
        str(row["status"]): int(row["count"])
        for row in conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM daily_top5_email_deliveries
            WHERE campaign_id = ?
            GROUP BY status
            """,
            (campaign_id,),
        ).fetchall()
    }
    if counts.get("sending"):
        status, finished = "sending", None
    elif counts.get("pending"):
        status, finished = "pending", None
    elif counts.get("failed"):
        status, finished = ("partial_failed" if counts.get("sent") else "failed"), _now()
    else:
        status, finished = "completed", _now()
    conn.execute(
        "UPDATE daily_top5_email_campaigns SET status = ?, finished_at = ? WHERE id = ?",
        (status, finished, campaign_id),
    )


def _refresh_daily_top5_close_email_campaign_status(conn: sqlite3.Connection, campaign_id: int) -> None:
    campaign = conn.execute(
        """
        SELECT calculation_status
        FROM daily_top5_close_email_campaigns
        WHERE id = ?
        """,
        (campaign_id,),
    ).fetchone()
    if not campaign:
        raise AuthError("每日 TOP5 收盘邮件任务不存在", 404)
    counts = {
        str(row["status"]): int(row["count"])
        for row in conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM daily_top5_close_email_deliveries
            WHERE campaign_id = ?
            GROUP BY status
            """,
            (campaign_id,),
        ).fetchall()
    }
    if sum(counts.values()) == 0:
        if str(campaign["calculation_status"] or "") == "failed":
            status, finished = "failed", _now()
        else:
            status, finished = "pending", None
    elif counts.get("sending"):
        status, finished = "sending", None
    elif counts.get("pending"):
        status, finished = "pending", None
    elif counts.get("failed"):
        status, finished = ("partial_failed" if counts.get("sent") else "failed"), _now()
    else:
        status, finished = "completed", _now()
    conn.execute(
        "UPDATE daily_top5_close_email_campaigns SET status = ?, finished_at = ? WHERE id = ?",
        (status, finished, campaign_id),
    )


def _ai_report_email_campaign_payload(conn: sqlite3.Connection, campaign_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM ai_report_email_campaigns WHERE id = ?", (campaign_id,)
    ).fetchone()
    if not row:
        raise AuthError("AI 报告邮件任务不存在", 404)
    counts = {
        str(item["status"]): int(item["count"])
        for item in conn.execute(
            "SELECT status, COUNT(*) AS count FROM ai_report_email_deliveries WHERE campaign_id = ? GROUP BY status",
            (campaign_id,),
        ).fetchall()
    }
    variants = {
        str(item["content_variant"]): int(item["count"])
        for item in conn.execute(
            """
            SELECT content_variant, COUNT(*) AS count
            FROM ai_report_email_deliveries
            WHERE campaign_id = ? AND status != 'skipped'
            GROUP BY content_variant
            """,
            (campaign_id,),
        ).fetchall()
    }
    return {
        "id": int(row["id"]),
        "report_type": str(row["report_type"]),
        "run_id": str(row["run_id"]),
        "report_date": str(row["report_date"]),
        "status": str(row["status"]),
        "total": sum(counts.values()),
        "pending": counts.get("pending", 0),
        "sending": counts.get("sending", 0),
        "sent": counts.get("sent", 0),
        "failed": counts.get("failed", 0),
        "skipped": counts.get("skipped", 0),
        "full": variants.get("full", 0),
        "teaser": variants.get("teaser", 0),
        "next_retry_at": _pending_delivery_next_retry_at(
            conn,
            delivery_table="ai_report_email_deliveries",
            campaign_id=campaign_id,
        ),
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


def _refresh_ai_report_email_campaign_status(conn: sqlite3.Connection, campaign_id: int) -> None:
    counts = {
        str(row["status"]): int(row["count"])
        for row in conn.execute(
            "SELECT status, COUNT(*) AS count FROM ai_report_email_deliveries WHERE campaign_id = ? GROUP BY status",
            (campaign_id,),
        ).fetchall()
    }
    if counts.get("sending"):
        status, finished = "sending", None
    elif counts.get("pending"):
        status, finished = "pending", None
    elif counts.get("failed"):
        status, finished = ("partial_failed" if counts.get("sent") else "failed"), _now()
    else:
        status, finished = "completed", _now()
    conn.execute(
        "UPDATE ai_report_email_campaigns SET status = ?, finished_at = ? WHERE id = ?",
        (status, finished, campaign_id),
    )


def _is_complete_ai_email_report(report_type: str, report: dict[str, Any]) -> bool:
    if report_type == "market_day":
        body = report.get("report") if isinstance(report.get("report"), dict) else report
        conclusion = str(body.get("oneLineConclusion") or "").strip()
        detail_keys = (
            "mainline", "marketMood", "marketBreadth", "strongestStocks", "secondaryLines",
            "rotationLines", "fakeOrWeakLines", "watchPoints", "keyRisks", "indices",
        )
        return bool(conclusion and any(body.get(key) for key in detail_keys))
    if report_type == "ai_research":
        title = str(report.get("title") or "").strip()
        summary = str(report.get("summary") or "").strip()
        detail_keys = (
            "markdown", "sections", "decision_cards", "evidence_table", "watchlist",
            "scenario_plan", "risk_calendar", "institutional_research", "sources",
        )
        return bool(title and summary and any(report.get(key) for key in detail_keys))
    return False


def _send_update_notice_email(
    delivery: dict[str, Any], *, smtp_session: UpdateEmailSMTPSession | None = None
) -> None:
    try:
        items = json.loads(str(delivery.get("items_json") or "[]"))
    except Exception:
        items = []
    items = [str(item) for item in items if str(item).strip()]
    title = str(delivery.get("title") or "产品更新")
    version = str(delivery.get("version") or "")
    summary = str(delivery.get("summary") or "").strip()
    content_markdown = str(delivery.get("content_markdown") or "").strip()
    if not content_markdown:
        content_markdown = "\n".join(f"- {item}" for item in items)
    site_url = os.getenv("PUBLIC_SITE_URL", "").strip().rstrip("/")
    if not site_url:
        raise AuthError("PUBLIC_SITE_URL 未配置", 500)
    text_summary = f"{summary}\n\n" if summary else ""
    text = f"盈航产品更新：{title}\n\n版本/日期：{version}\n\n{text_summary}{content_markdown}\n\n查看网站：{site_url}\n"
    summary_html = (
        f'<p style="margin:0 0 20px;color:#57606a;font-size:15px;line-height:1.7;">{_html_escape(summary)}</p>'
        if summary else ""
    )
    content_html = _safe_markdown_email_html(content_markdown)
    html = _light_email_document(f"""
      <p style="margin:0 0 8px;color:#57606a;font-size:13px;">盈航 · 产品更新</p>
      <h1 style="margin:0 0 12px;color:#1f2328;font-size:24px;line-height:1.35;">{_html_escape(title)}</h1>
      <p style="margin:0 0 20px;color:#57606a;font-size:14px;">{_html_escape(version)}</p>
      {summary_html}
      <div style="margin:0 0 24px;color:#1f2328;">{content_html}</div>
      <p style="margin:0 0 8px;color:#1f2328;"><a href="{_html_escape(site_url)}" style="color:#0969da;text-decoration:underline;">打开盈航查看</a></p>
      <p style="margin:0 0 20px;color:#57606a;font-size:13px;word-break:break-all;">{_html_escape(site_url)}</p>
      <p style="margin:0;color:#57606a;font-size:12px;line-height:1.6;">你可以登录盈航，在账户菜单中关闭邮件推送。</p>
    """, max_width=600)
    send = smtp_session.send if smtp_session is not None else _send_email_message
    send(str(delivery["email"]), subject=f"盈航产品更新｜{title}", text=text, html=html)


_MARKDOWN_INLINE_RE = re.compile(
    r"(`[^`\n]+`|\[[^\]\n]+\]\(https?://[^\s)]+\)|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|_[^_\n]+_)"
)


def _safe_markdown_inline_html(value: str) -> str:
    """Render a deliberately small inline Markdown subset without raw HTML."""
    parts: list[str] = []
    cursor = 0
    for match in _MARKDOWN_INLINE_RE.finditer(str(value)):
        parts.append(_html_escape(str(value)[cursor:match.start()]))
        token = match.group(0)
        if token.startswith("`"):
            parts.append(f'<code style="padding:2px 5px;background:#f6f8fa;border-radius:4px;">{_html_escape(token[1:-1])}</code>')
        elif token.startswith("["):
            label, href = token[1:].split("](", 1)
            href = href[:-1]
            parts.append(
                f'<a href="{_html_escape(href)}" style="color:#0969da;text-decoration:underline;">{_html_escape(label)}</a>'
            )
        elif token.startswith(("**", "__")):
            parts.append(f"<strong>{_html_escape(token[2:-2])}</strong>")
        else:
            parts.append(f"<em>{_html_escape(token[1:-1])}</em>")
        cursor = match.end()
    parts.append(_html_escape(str(value)[cursor:]))
    return "".join(parts)


def _safe_markdown_email_html(markdown: str) -> str:
    """Render email-safe Markdown; raw HTML and non-http(s) links stay escaped text."""
    lines = str(markdown or "").splitlines()
    html_parts: list[str] = []
    list_type = ""
    code_lines: list[str] | None = None

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            html_parts.append(f"</{list_type}>")
            list_type = ""

    for line in lines:
        if line.strip().startswith("```"):
            close_list()
            if code_lines is None:
                code_lines = []
            else:
                html_parts.append(
                    '<pre style="margin:12px 0;padding:14px;background:#f6f8fa;border-radius:6px;overflow:auto;white-space:pre-wrap;">'
                    f'<code>{_html_escape(chr(10).join(code_lines))}</code></pre>'
                )
                code_lines = None
            continue
        if code_lines is not None:
            code_lines.append(line)
            continue
        if not line.strip():
            close_list()
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line.strip())
        if heading:
            close_list()
            level = len(heading.group(1)) + 1
            html_parts.append(
                f'<h{level} style="margin:22px 0 10px;color:#1f2328;line-height:1.4;">'
                f'{_safe_markdown_inline_html(heading.group(2))}</h{level}>'
            )
            continue
        bullet = re.match(r"^\s*[-*+]\s+(.+)$", line)
        ordered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if bullet or ordered:
            wanted = "ul" if bullet else "ol"
            if list_type != wanted:
                close_list()
                list_type = wanted
                html_parts.append(f'<{wanted} style="margin:10px 0;padding-left:24px;color:#1f2328;">')
            html_parts.append(
                f'<li style="margin:7px 0;color:#1f2328;line-height:1.7;">{_safe_markdown_inline_html((bullet or ordered).group(1))}</li>'
            )
            continue
        close_list()
        quote = re.match(r"^\s*>\s?(.*)$", line)
        if quote:
            html_parts.append(
                '<blockquote style="margin:12px 0;padding:8px 14px;border-left:4px solid #d0d7de;color:#57606a;line-height:1.7;">'
                f'{_safe_markdown_inline_html(quote.group(1))}</blockquote>'
            )
        else:
            html_parts.append(
                f'<p style="margin:10px 0;color:#1f2328;line-height:1.7;">{_safe_markdown_inline_html(line.strip())}</p>'
            )
    close_list()
    if code_lines is not None:
        html_parts.append(
            '<pre style="margin:12px 0;padding:14px;background:#f6f8fa;border-radius:6px;overflow:auto;white-space:pre-wrap;">'
            f'<code>{_html_escape(chr(10).join(code_lines))}</code></pre>'
        )
    return "".join(html_parts)


def _send_daily_top5_email(
    delivery: dict[str, Any], *, smtp_session: UpdateEmailSMTPSession | None = None
) -> None:
    try:
        report = json.loads(str(delivery.get("report_json") or "{}"))
    except Exception as exc:
        raise AuthError("每日 TOP5 邮件报告快照损坏", 500) from exc
    if not isinstance(report, dict):
        raise AuthError("每日 TOP5 邮件报告快照损坏", 500)
    trade_date = str(delivery.get("trade_date") or report.get("trade_date") or "")
    analysis_time = str(report.get("analysis_time") or report.get("received_at") or "")
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    conclusion = report.get("global_conclusion") if isinstance(report.get("global_conclusion"), dict) else {}
    site_url = os.getenv("PUBLIC_SITE_URL", "").strip().rstrip("/")
    if not site_url:
        raise AuthError("PUBLIC_SITE_URL 未配置", 500)
    report_url = f"{site_url}/auction-strength?date={trade_date}"
    disclaimer = (
        "风险提示：本邮件内容由 AI 基于公开信息整理，仅供学习、研究与信息参考，"
        "不构成投资建议、证券推荐或收益承诺。信息可能存在延迟、遗漏或错误，投资有风险，请独立判断。"
    )
    teaser = str(summary.get("one_sentence") or "今日集合竞价强弱方向已经整理完成。").strip()
    is_full = str(delivery.get("content_variant") or "teaser") == "full"
    strong_stocks = report.get("top5_strong_stocks") if isinstance(report.get("top5_strong_stocks"), list) else []
    if not is_full:
        protected_tokens = {
            str(stock.get(field) or "").strip()
            for stock in strong_stocks
            if isinstance(stock, dict)
            for field in ("name", "code")
            if str(stock.get(field) or "").strip()
        }
        if any(token.casefold() in teaser.casefold() for token in protected_tokens):
            teaser = "今日集合竞价强弱方向已经整理完成。"

    if is_full:
        text_rows = []
        html_stock_sections = []
        for index, stock in enumerate(strong_stocks, start=1):
            if not isinstance(stock, dict):
                continue
            rank = stock.get("rank") or index
            name = str(stock.get("name") or "-")
            code = str(stock.get("code") or "-")
            theme = str(stock.get("theme") or "-")
            change = str(stock.get("today_open_change") or "-")
            reason = str(stock.get("reason") or "-")
            observe = str(stock.get("observe_after_930") or "-")
            text_rows.append(
                f"{rank}. {name}（{code}）｜题材：{theme}｜竞价涨幅：{change}\n"
                f"   入选理由：{reason}\n   9:30 后观察：{observe}"
            )
            html_stock_sections.append(f"""
              <div style="margin:0 0 24px;color:#1f2328;">
                <h3 style="margin:0 0 10px;color:#1f2328;font-size:18px;line-height:1.5;">{_html_escape(rank)}. {_html_escape(name)}（{_html_escape(code)}）</h3>
                <p style="margin:6px 0;color:#1f2328;line-height:1.7;"><strong>题材：</strong>{_html_escape(theme)}</p>
                <p style="margin:6px 0;color:#1f2328;line-height:1.7;"><strong>竞价涨幅：</strong>{_html_escape(change)}</p>
                <p style="margin:6px 0;color:#1f2328;line-height:1.7;"><strong>入选理由：</strong>{_html_escape(reason)}</p>
                <p style="margin:6px 0;color:#1f2328;line-height:1.7;"><strong>9:30 后观察：</strong>{_html_escape(observe)}</p>
              </div>
            """)
        conclusion_items = [
            ("最强个股", conclusion.get("strongest_stock_at_925")),
            ("最强题材", conclusion.get("strongest_theme_cluster")),
            ("超预期标的", conclusion.get("most_over_expected_stock")),
            ("容量确认", conclusion.get("best_capacity_confirmation")),
            ("负反馈", conclusion.get("biggest_negative_feedback")),
            ("9:30 全局结论", conclusion.get("one_sentence_for_930")),
        ]
        text_conclusion = "\n".join(f"- {label}：{value or '-'}" for label, value in conclusion_items)
        html_conclusion = "".join(
            f'<li style="margin:8px 0;color:#1f2328;line-height:1.7;"><strong>{_html_escape(label)}：</strong>{_html_escape(value or "-")}</li>'
            for label, value in conclusion_items
        )
        text = (
            f"盈航每日 TOP5｜{trade_date}\n生成时间：{analysis_time or '-'}\n\n"
            f"{teaser}\n\n今日强势标的\n" + "\n\n".join(text_rows) +
            f"\n\n全局结论\n{text_conclusion}\n\n查看网站：{report_url}\n\n{disclaimer}\n"
            "可登录盈航，在账户菜单中关闭邮件推送。"
        )
        body_html = f"""
          <p style="margin:0 0 24px;color:#1f2328;line-height:1.7;">{_html_escape(teaser)}</p>
          <h2 style="margin:0 0 16px;color:#1f2328;font-size:20px;line-height:1.4;">今日强势标的</h2>
          {''.join(html_stock_sections)}
          <h2 style="margin:28px 0 12px;color:#1f2328;font-size:20px;line-height:1.4;">全局结论</h2>
          <ul style="margin:0 0 20px;padding-left:24px;color:#1f2328;">{html_conclusion}</ul>
        """
    else:
        text = (
            f"盈航每日 TOP5｜{trade_date}\n\n今日 TOP5 已生成。\n{teaser}\n\n"
            "开通会员后，可在邮件中直接查看完整 5 只强势标的与全局结论。\n"
            f"打开网站：{report_url}\n\n{disclaimer}\n"
            "可登录盈航，在账户菜单中关闭邮件推送。"
        )
        body_html = f"""
          <h2 style="margin:0 0 12px;color:#1f2328;font-size:20px;line-height:1.4;">今日 TOP5 已生成</h2>
          <p style="margin:0 0 16px;color:#1f2328;line-height:1.7;">{_html_escape(teaser)}</p>
          <p style="margin:0 0 20px;color:#1f2328;line-height:1.7;">开通会员后，可在邮件中直接查看完整 5 只强势标的与全局结论。</p>
        """

    html = _light_email_document(f"""
      <p style="margin:0 0 8px;color:#57606a;font-size:13px;">盈航 · DAILY TOP 5</p>
      <h1 style="margin:0 0 8px;color:#1f2328;font-size:24px;line-height:1.35;">每日 TOP5｜{_html_escape(trade_date)}</h1>
      <p style="margin:0 0 24px;color:#57606a;font-size:13px;">生成时间：{_html_escape(analysis_time or '-')}</p>
      {body_html}
      <p style="margin:24px 0 8px;color:#1f2328;"><a href="{_html_escape(report_url)}" style="color:#0969da;text-decoration:underline;">打开盈航查看</a></p>
      <p style="margin:0 0 20px;color:#57606a;font-size:13px;word-break:break-all;">{_html_escape(report_url)}</p>
      <p style="margin:0 0 12px;color:#57606a;font-size:12px;line-height:1.6;">{_html_escape(disclaimer)}</p>
      <p style="margin:0;color:#57606a;font-size:12px;line-height:1.6;">可登录盈航，在账户菜单中关闭“邮件推送（产品更新与每日 AI 报告）”。</p>
    """, max_width=720)
    send = smtp_session.send if smtp_session is not None else _send_email_message
    send_kwargs: dict[str, Any] = {
        "subject": f"盈航每日 TOP5｜{trade_date}",
        "text": text,
        "html": html,
    }
    if delivery.get("campaign_id") is not None and delivery.get("id") is not None:
        send_kwargs["message_id"] = f"daily-top5-c{delivery['campaign_id']}-d{delivery['id']}"
    send(str(delivery["email"]), **send_kwargs)


def _send_daily_top5_close_email(
    delivery: dict[str, Any], *, smtp_session: UpdateEmailSMTPSession | None = None
) -> None:
    snapshot = _load_daily_top5_close_report_json(delivery.get("close_report_json"))
    rows = snapshot.get("top5_close_performance") if isinstance(snapshot.get("top5_close_performance"), list) else []
    trade_date = str(snapshot.get("trade_date") or delivery.get("trade_date") or "")
    quote_time = str(snapshot.get("quote_time") or "")
    site_url = os.getenv("PUBLIC_SITE_URL", "").strip().rstrip("/")
    if not site_url:
        raise AuthError("PUBLIC_SITE_URL 未配置", 500)
    report_url = f"{site_url}/auction-strength?date={trade_date}"
    disclaimer = (
        "风险提示：本邮件内容基于公开行情整理，仅供学习、研究与信息参考，不构成投资建议。"
    )
    text_rows = "\n".join(
        f"{int(item.get('rank') or 0)}. {item.get('name') or '-'} ({item.get('code') or '-'})  开盘 {float(item.get('open_price') or 0):.2f}  收盘 {float(item.get('close_price') or 0):.2f}  涨跌幅 {float(item.get('change_pct') or 0):+.2f}%  是否涨停 {'涨停' if bool(item.get('is_limit_up')) else '未涨停'}"
        for item in rows
        if isinstance(item, dict)
    )
    html_rows = "".join(
        f"""
        <tr>
          <td style="padding:8px;border:1px solid #d0d7de;">{int(item.get('rank') or 0)}</td>
          <td style="padding:8px;border:1px solid #d0d7de;">{_html_escape(str(item.get('name') or '-'))}</td>
          <td style="padding:8px;border:1px solid #d0d7de;">{_html_escape(str(item.get('code') or '-'))}</td>
          <td style="padding:8px;border:1px solid #d0d7de;">{float(item.get('open_price') or 0):.2f}</td>
          <td style="padding:8px;border:1px solid #d0d7de;">{float(item.get('close_price') or 0):.2f}</td>
          <td style="padding:8px;border:1px solid #d0d7de;">{float(item.get('change_pct') or 0):+.2f}%</td>
          <td style="padding:8px;border:1px solid #d0d7de;">{'涨停' if bool(item.get('is_limit_up')) else '未涨停'}</td>
        </tr>
        """
        for item in rows
        if isinstance(item, dict)
    )
    text = (
        f"盈航每日 TOP5 收盘表现｜{trade_date}\n"
        f"行情时间：{quote_time or '-'}\n\n"
        f"{text_rows}\n\n"
        f"查看报告：{report_url}\n\n{disclaimer}\n"
        "可登录盈航，在账户菜单中关闭邮件推送。"
    )
    html = _light_email_document(f"""
      <p style="margin:0 0 8px;color:#57606a;font-size:13px;">盈航 · DAILY TOP 5 CLOSE</p>
      <h1 style="margin:0 0 8px;color:#1f2328;font-size:24px;line-height:1.35;">每日 TOP5 收盘表现｜{_html_escape(trade_date)}</h1>
      <p style="margin:0 0 20px;color:#57606a;font-size:13px;">行情时间：{_html_escape(quote_time or '-')}</p>
      <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="width:100%;border-collapse:collapse;margin:0 0 20px;">
        <thead>
          <tr>
            <th style="padding:8px;border:1px solid #d0d7de;background:#f6f8fa;">排名</th>
            <th style="padding:8px;border:1px solid #d0d7de;background:#f6f8fa;">名称</th>
            <th style="padding:8px;border:1px solid #d0d7de;background:#f6f8fa;">代码</th>
            <th style="padding:8px;border:1px solid #d0d7de;background:#f6f8fa;">开盘价</th>
            <th style="padding:8px;border:1px solid #d0d7de;background:#f6f8fa;">收盘价</th>
            <th style="padding:8px;border:1px solid #d0d7de;background:#f6f8fa;">涨跌幅</th>
            <th style="padding:8px;border:1px solid #d0d7de;background:#f6f8fa;">是否涨停</th>
          </tr>
        </thead>
        <tbody>{html_rows}</tbody>
      </table>
      <p style="margin:24px 0 8px;color:#1f2328;"><a href="{_html_escape(report_url)}" style="color:#0969da;text-decoration:underline;">打开盈航查看报告</a></p>
      <p style="margin:0 0 20px;color:#57606a;font-size:13px;word-break:break-all;">{_html_escape(report_url)}</p>
      <p style="margin:0 0 12px;color:#57606a;font-size:12px;line-height:1.6;">{_html_escape(disclaimer)}</p>
      <p style="margin:0;color:#57606a;font-size:12px;line-height:1.6;">可登录盈航，在账户菜单中关闭邮件推送。</p>
    """, max_width=720)
    send = smtp_session.send if smtp_session is not None else _send_email_message
    send_kwargs: dict[str, Any] = {
        "subject": f"盈航每日 TOP5 收盘表现｜{trade_date}",
        "text": text,
        "html": html,
    }
    if delivery.get("campaign_id") is not None and delivery.get("id") is not None:
        send_kwargs["message_id"] = f"daily-top5-close-c{delivery['campaign_id']}-d{delivery['id']}"
    send(str(delivery["email"]), **send_kwargs)


_AI_REPORT_EMAIL_LABELS = {
    "oneLineConclusion": "一句话结论",
    "marketMood": "市场情绪",
    "marketStage": "市场阶段",
    "marketBreadth": "市场广度",
    "indices": "主要指数",
    "mainline": "最强主线",
    "strongestStocks": "强势个股",
    "secondaryLines": "次主线",
    "rotationLines": "轮动方向",
    "fakeOrWeakLines": "偏弱方向",
    "watchPoints": "后续观察",
    "keyRisks": "风险提示",
    "previousDayComparison": "与前一交易日对比",
    "informationCutoff": "信息截止时间",
    "audit": "数据审计",
    "sources": "信息来源",
    "markdown": "完整研报",
    "sections": "重点章节",
    "decision_cards": "决策卡片",
    "evidence_table": "证据与影响",
    "watchlist": "观察清单",
    "scenario_plan": "情景预案",
    "risk_calendar": "风险日历",
    "data_gaps": "数据缺口",
    "institutional_research": "海外及机构观点",
    "tags": "主题标签",
}


def _send_ai_report_email(
    delivery: dict[str, Any], *, smtp_session: UpdateEmailSMTPSession | None = None
) -> None:
    try:
        report = json.loads(str(delivery.get("report_json") or "{}"))
    except Exception as exc:
        raise AuthError("AI 报告邮件快照损坏", 500) from exc
    if not isinstance(report, dict):
        raise AuthError("AI 报告邮件快照损坏", 500)
    report_type = str(delivery.get("report_type") or "")
    if report_type not in AI_REPORT_EMAIL_TYPES:
        raise AuthError("AI 报告邮件类型无效", 500)
    report_date = str(delivery.get("report_date") or "")
    site_url = os.getenv("PUBLIC_SITE_URL", "").strip().rstrip("/")
    if not site_url:
        raise AuthError("PUBLIC_SITE_URL 未配置", 500)
    if report_type == "market_day":
        product_name = "AI 当日行情"
        route = "/market-day"
        teaser = "今日市场行情总结已生成，可登录盈航查看市场主线、强弱方向与后续关注重点。"
    else:
        product_name = "AI 研报"
        route = "/ai-research"
        teaser = "今日 AI 研报已生成，可登录盈航查看国内外重要信息及其对 A 股的影响。"
    report_url = f"{site_url}{route}?date={report_date}"
    is_full = str(delivery.get("content_variant") or "teaser") == "full"
    disclaimer = (
        "风险提示：本邮件内容由 AI 基于公开信息整理，仅供学习、研究与信息参考，"
        "不构成投资建议、证券推荐或收益承诺。信息可能存在延迟、遗漏或错误，投资有风险，请独立判断。"
    )

    if is_full:
        title, summary, sections = _ai_report_email_content(report_type, report)
        text_sections = "\n\n".join(
            f"{label}\n{_email_value_text(value)}" for label, value in sections if _email_value_text(value)
        )
        html_sections = "".join(
            f'<h2 style="margin:24px 0 10px;color:#1f2328;font-size:19px;line-height:1.4;">{_html_escape(label)}</h2>'
            f'{_email_value_html(value)}'
            for label, value in sections
            if _email_value_text(value)
        )
        text = (
            f"盈航{product_name}｜{report_date}\n\n{title}\n\n{summary}\n\n{text_sections}\n\n"
            f"打开网站：{report_url}\n\n{disclaimer}\n可登录盈航，在账户菜单中关闭邮件推送。"
        )
        body_html = f"""
          <h2 style="margin:0 0 10px;color:#1f2328;font-size:20px;line-height:1.4;">{_html_escape(title)}</h2>
          <p style="margin:0 0 20px;color:#1f2328;line-height:1.7;">{_html_escape(summary)}</p>
          {html_sections}
        """
    else:
        text = (
            f"盈航{product_name}｜{report_date}\n\n{teaser}\n\n"
            f"开通会员后，可直接在邮件中阅读完整报告。\n打开网站：{report_url}\n\n{disclaimer}\n"
            "可登录盈航，在账户菜单中关闭邮件推送。"
        )
        body_html = f"""
          <h2 style="margin:0 0 12px;color:#1f2328;font-size:20px;line-height:1.4;">{_html_escape(product_name)}已生成</h2>
          <p style="margin:0 0 16px;color:#1f2328;line-height:1.7;">{_html_escape(teaser)}</p>
          <p style="margin:0 0 20px;color:#1f2328;line-height:1.7;">开通会员后，可直接在邮件中阅读完整报告。</p>
        """

    html = _light_email_document(f"""
      <p style="margin:0 0 8px;color:#57606a;font-size:13px;">盈航 · {_html_escape(product_name)}</p>
      <h1 style="margin:0 0 8px;color:#1f2328;font-size:24px;line-height:1.35;">{_html_escape(product_name)}｜{_html_escape(report_date)}</h1>
      <p style="margin:0 0 24px;color:#57606a;font-size:13px;">报告已生成</p>
      {body_html}
      <p style="margin:24px 0 8px;color:#1f2328;"><a href="{_html_escape(report_url)}" style="color:#0969da;text-decoration:underline;">打开盈航查看</a></p>
      <p style="margin:0 0 20px;color:#57606a;font-size:13px;word-break:break-all;">{_html_escape(report_url)}</p>
      <p style="margin:0 0 12px;color:#57606a;font-size:12px;line-height:1.6;">{_html_escape(disclaimer)}</p>
      <p style="margin:0;color:#57606a;font-size:12px;line-height:1.6;">可登录盈航，在账户菜单中关闭邮件推送。</p>
    """, max_width=720)
    send = smtp_session.send if smtp_session is not None else _send_email_message
    send(
        str(delivery["email"]),
        subject=f"盈航{product_name}｜{report_date}",
        text=text,
        html=html,
    )


def _ai_report_email_content(
    report_type: str, report: dict[str, Any]
) -> tuple[str, str, list[tuple[str, object]]]:
    if report_type == "market_day":
        body = report.get("report") if isinstance(report.get("report"), dict) else report
        title = f"{report.get('market_date') or report.get('marketDate') or body.get('marketDate') or ''} 市场复盘"
        summary = str(body.get("oneLineConclusion") or "今日市场行情已完成整理。")
        keys = (
            "marketMood", "marketStage", "marketBreadth", "indices", "mainline",
            "strongestStocks", "secondaryLines", "rotationLines", "fakeOrWeakLines",
            "watchPoints", "keyRisks", "previousDayComparison", "informationCutoff", "audit", "sources",
        )
    else:
        body = report
        title = str(report.get("title") or "AI 研报")
        summary = str(report.get("summary") or "今日重要信息已完成整理。")
        keys = (
            "tags", "markdown", "sections", "decision_cards", "evidence_table",
            "watchlist", "scenario_plan", "risk_calendar", "institutional_research",
            "data_gaps", "sources",
        )
    return title, summary, [(_AI_REPORT_EMAIL_LABELS.get(key, key), body.get(key)) for key in keys if body.get(key)]


def _email_value_text(value: object, *, depth: int = 0) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if _is_sensitive_ai_email_key(key):
                continue
            rendered = _email_value_text(item, depth=depth + 1)
            if rendered:
                label = _AI_REPORT_EMAIL_LABELS.get(str(key), str(key))
                indent = "  " * depth
                lines.append(f"{indent}{label}：{rendered}")
        return "\n".join(lines)
    if isinstance(value, list):
        lines = []
        for index, item in enumerate(value, start=1):
            rendered = _email_value_text(item, depth=depth + 1)
            if rendered:
                lines.append(f"{index}. {rendered}")
        return "\n".join(lines)
    return str(value)


def _is_sensitive_ai_email_key(value: object) -> bool:
    """Keep ingestion metadata and credentials out of recursively rendered report fields."""
    key = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    exact = {
        "headers",
        "payload",
        "raw_payload",
        "source_ip",
        "request_id",
        "authorization",
        "proxy_authorization",
        "cookie",
        "set_cookie",
        "password",
        "secret",
        "token",
        "credential",
        "api_key",
        "access_token",
        "refresh_token",
        "client_secret",
    }
    if key in exact:
        return True
    return bool(
        key.endswith(("_api_key", "_access_token", "_refresh_token", "_client_secret", "_password", "_secret", "_token", "_credential"))
        or key.startswith(("api_key_", "access_token_", "refresh_token_", "client_secret_", "password_", "secret_", "credential_"))
    )


def _email_value_html(value: object) -> str:
    text = _email_value_text(value)
    return (
        '<div style="margin:0 0 16px;color:#1f2328;font-size:14px;line-height:1.75;white-space:pre-wrap;word-break:break-word;">'
        f'{_html_escape(text)}</div>'
    )


def _order_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "order_no": row["order_no"],
        "user_id": row["user_id"],
        "plan_name": row["plan_name"],
        "credits": row["credits"],
        "amount_cents": row["amount_cents"],
        "status": row["status"],
        "paid_at": row["paid_at"],
        "created_at": row["created_at"],
        "payment_provider": row["payment_provider"] if "payment_provider" in row.keys() else "",
        "provider_trade_no": row["provider_trade_no"] if "provider_trade_no" in row.keys() else "",
        "paid_amount_cents": row["paid_amount_cents"] if "paid_amount_cents" in row.keys() else None,
        "product_type": row["product_type"] if "product_type" in row.keys() else "credits",
        "package_id": row["package_id"] if "package_id" in row.keys() else "",
        "duration_days": row["duration_days"] if "duration_days" in row.keys() else None,
        "payment_method": row["payment_method"] if "payment_method" in row.keys() else "",
        "payment_submit_status": row["payment_submit_status"] if "payment_submit_status" in row.keys() else "",
        "payer_name": row["payer_name"] if "payer_name" in row.keys() else "",
        "payer_note": row["payer_note"] if "payer_note" in row.keys() else "",
        "payer_paid_at": row["payer_paid_at"] if "payer_paid_at" in row.keys() else "",
        "submitted_amount_cents": row["submitted_amount_cents"] if "submitted_amount_cents" in row.keys() else None,
        "submitted_at": row["submitted_at"] if "submitted_at" in row.keys() else "",
        "admin_id": row["admin_id"] if "admin_id" in row.keys() else None,
        "admin_note": row["admin_note"] if "admin_note" in row.keys() else "",
        "confirmed_at": row["confirmed_at"] if "confirmed_at" in row.keys() else "",
        "rejected_at": row["rejected_at"] if "rejected_at" in row.keys() else "",
    }


def _now() -> str:
    return datetime.now(CN_TZ).isoformat()


def _update_notice_items_from_markdown(markdown: str, *, fallback: str) -> list[str]:
    """Keep the legacy items contract useful while Markdown remains the source of truth."""
    items: list[str] = []
    for line in str(markdown or "").splitlines():
        match = re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)(.+)$", line)
        if not match:
            continue
        value = match.group(1).strip()
        value = re.sub(r"\[([^\]]+)\]\(https?://[^\s)]+\)", r"\1", value)
        value = re.sub(r"(?:\*\*|__)(.+?)(?:\*\*|__)", r"\1", value)
        value = re.sub(r"[`*_]", "", value).strip()
        if value:
            items.append(value)
    return items or [fallback]


def _normalize_update_notice_input(
    title: str,
    version: str,
    items: list[Any],
    summary: str,
    content_markdown: str,
    audience: str,
    expires_at: str,
    status: str,
) -> tuple[str, str, list[str], str, str, str, str, str]:
    title = str(title or "").strip()
    version = str(version or "").strip()
    summary = str(summary or "").strip()
    content_markdown = str(content_markdown or "").strip()
    audience = str(audience or "registered_users").strip() or "registered_users"
    expires_at = str(expires_at or "").strip()
    status = str(status or "draft").strip()
    if status not in {"draft", "published", "archived"}:
        raise AuthError("更新公告状态不正确", 400)
    if not title:
        raise AuthError("更新公告标题不能为空", 400)
    if not version:
        raise AuthError("更新公告版本不能为空", 400)
    if audience != "registered_users":
        raise AuthError("更新公告受众不正确", 400)
    if not isinstance(items, list):
        raise AuthError("更新公告内容必须是列表", 400)
    if len(title) > 200 or len(version) > 80 or len(summary) > 5000 or len(content_markdown) > 200000:
        raise AuthError("更新公告内容过长，请精简后重试", 400)
    normalized_items = [str(item).strip() for item in items if str(item).strip()]
    if not normalized_items and content_markdown:
        normalized_items = _update_notice_items_from_markdown(content_markdown, fallback=summary or title)
    if len(normalized_items) > 1000 or any(len(item) > 20000 for item in normalized_items):
        raise AuthError("更新公告条目过多或单条内容过长", 400)
    if not normalized_items and not content_markdown:
        raise AuthError("更新公告内容不能为空", 400)
    if not summary:
        summary = normalized_items[0] if normalized_items else title
    if not content_markdown:
        content_markdown = "\n".join(f"- {item}" for item in normalized_items)
    return title, version, normalized_items, summary, content_markdown, audience, expires_at, status


def _amount_yuan_to_cents(value: str) -> int:
    try:
        amount = Decimal(str(value or "0").strip())
    except Exception as exc:
        raise AuthError("支付金额格式不正确", 400) from exc
    if amount < 0:
        raise AuthError("支付金额不正确", 400)
    return int((amount * Decimal("100")).quantize(Decimal("1")))
