from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import smtplib
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

from trade_review_agent.legal_agreements import (
    REGISTRATION_AGREEMENT_TYPE,
    REGISTRATION_AGREEMENT_VERSION,
    registration_agreement_payload,
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
                status TEXT NOT NULL DEFAULT 'draft',
                created_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                published_at TEXT,
                FOREIGN KEY (created_by) REFERENCES users(id)
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
            CREATE UNIQUE INDEX IF NOT EXISTS idx_credit_ledger_grant_campaign_user
                ON credit_ledger(user_id, related_id) WHERE reason = 'admin_grant_all';
            CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback(status);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
            CREATE INDEX IF NOT EXISTS idx_update_notices_status ON update_notices(status, published_at);
            CREATE INDEX IF NOT EXISTS idx_update_email_campaigns_notice ON update_email_campaigns(notice_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_update_email_deliveries_queue ON update_email_deliveries(status, next_attempt_at, id);
            CREATE INDEX IF NOT EXISTS idx_daily_top5_email_deliveries_queue
                ON daily_top5_email_deliveries(status, next_attempt_at, id);
            CREATE INDEX IF NOT EXISTS idx_sms_codes_phone ON sms_codes(phone, purpose, created_at);
            CREATE INDEX IF NOT EXISTS idx_email_codes_email ON email_codes(email, purpose, created_at);
            CREATE INDEX IF NOT EXISTS idx_agreement_acceptances_user ON agreement_acceptances(user_id, accepted_at);
            """
        )
        _ensure_user_columns(conn)
        _ensure_order_columns(conn)
        conn.executescript(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username) WHERE username IS NOT NULL AND username != '';
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL AND email != '';
            """
        )
        _ensure_admin(conn)


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


def get_current_user(db_path: Path, token: str) -> dict[str, Any] | None:
    if not token:
        return None
    now = _now()
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT u.*
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > ? AND u.status = 'active'
            """,
            (token, now),
        ).fetchone()
        if not row:
            return None
        return _user_payload(conn, row)


def require_user(db_path: Path, token: str) -> dict[str, Any]:
    user = get_current_user(db_path, token)
    if not user:
        raise AuthError("请先登录后再使用", 401)
    return user


def require_admin(db_path: Path, token: str) -> dict[str, Any]:
    user = require_user(db_path, token)
    if user.get("role") != "admin":
        raise AuthError("需要管理员权限", 403)
    return user


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


def membership_plans() -> list[dict[str, Any]]:
    return [
        {
            **plan,
            "alipay_qr_url": os.getenv("PAYMENT_ALIPAY_QR_URL", "/pay/alipay-qr.png").strip(),
            "wechat_qr_url": os.getenv("PAYMENT_WECHAT_QR_URL", "/pay/wechat-qr.png").strip(),
        }
        for plan in _membership_plans()
    ]


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
        conn.execute(
            """
            UPDATE orders
            SET status = 'paid',
                paid_at = ?,
                confirmed_at = ?,
                admin_id = ?,
                admin_note = ?
            WHERE id = ?
            """,
            (now, now, admin_id, admin_note, order_id),
        )
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
        return {
            "totals": totals,
            "usage_by_day": [dict(row) for row in usage_rows],
            "new_users_by_day": [dict(row) for row in user_rows],
            "feedback": [_feedback_payload(row) for row in feedback_rows],
            "orders": [_order_payload(row) | {"phone": row["phone"], "username": row["username"], "email": row["email"]} for row in orders],
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
        }


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
    status: str = "draft",
) -> dict[str, Any]:
    title, version, items, status = _normalize_update_notice_input(title, version, items, status)
    now = _now()
    published_at = now if status == "published" else None
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO update_notices (title, version, items_json, status, created_by, created_at, updated_at, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, version, json.dumps(items, ensure_ascii=False), status, admin_id, now, now, published_at),
        )
        return _update_notice_payload(conn.execute("SELECT * FROM update_notices WHERE id = ?", (cursor.lastrowid,)).fetchone())


def update_update_notice(
    db_path: Path,
    *,
    notice_id: int,
    title: str,
    version: str,
    items: list[Any],
) -> dict[str, Any]:
    title, version, items, _ = _normalize_update_notice_input(title, version, items, "draft")
    with _connect(db_path) as conn:
        existing = conn.execute("SELECT * FROM update_notices WHERE id = ?", (notice_id,)).fetchone()
        if not existing:
            raise AuthError("更新公告不存在", 404)
        conn.execute(
            """
            UPDATE update_notices
            SET title = ?, version = ?, items_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (title, version, json.dumps(items, ensure_ascii=False), _now(), notice_id),
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
            """,
            (now, now, campaign_id),
        )
        if cursor.rowcount:
            conn.execute(
                "UPDATE daily_top5_email_campaigns SET status = 'pending', finished_at = NULL WHERE id = ?",
                (campaign_id,),
            )
        return _daily_top5_email_campaign_payload(conn, campaign_id)


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
        cursor = conn.execute(
            """
            UPDATE daily_top5_email_deliveries
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
        row = conn.execute(
            """
            SELECT d.id, d.campaign_id, d.email, d.attempt_count,
                   n.title, n.version, n.items_json
            FROM update_email_deliveries d
            JOIN update_email_campaigns c ON c.id = d.campaign_id
            JOIN update_notices n ON n.id = c.notice_id
            WHERE d.status = 'pending' AND (d.next_attempt_at IS NULL OR d.next_attempt_at <= ?)
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
        with _connect(db_path) as conn:
            if attempt >= UPDATE_EMAIL_MAX_ATTEMPTS:
                conn.execute(
                    "UPDATE daily_top5_email_deliveries SET status = 'failed', last_error = ?, updated_at = ? WHERE id = ?",
                    (str(exc)[:500], _now(), delivery["id"]),
                )
            else:
                delay = UPDATE_EMAIL_RETRY_MINUTES[min(attempt - 1, len(UPDATE_EMAIL_RETRY_MINUTES) - 1)]
                next_attempt = (datetime.now(CN_TZ) + timedelta(minutes=delay)).isoformat()
                conn.execute(
                    """
                    UPDATE daily_top5_email_deliveries
                    SET status = 'pending', next_attempt_at = ?, last_error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (next_attempt, str(exc)[:500], _now(), delivery["id"]),
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


def unpublish_update_notice(db_path: Path, *, notice_id: int) -> dict[str, Any]:
    with _connect(db_path) as conn:
        existing = conn.execute("SELECT * FROM update_notices WHERE id = ?", (notice_id,)).fetchone()
        if not existing:
            raise AuthError("更新公告不存在", 404)
        conn.execute(
            "UPDATE update_notices SET status = 'draft', updated_at = ? WHERE id = ?",
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
        if (order["product_type"] if "product_type" in order.keys() else "") == "membership":
            raise AuthError("会员订单请使用确认开通操作", 400)
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
        _send_smtp_message(admin_email, subject=subject, text=text, html=html)
        return {"sent": True, "provider": "smtp", "email": _mask_email(admin_email)}
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
    if provider == "smtp":
        _send_smtp_email(email, code)
        return {"provider": "smtp"}
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
    _send_smtp_message(email, subject=subject, text=text, html=html)


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
        _send_smtp_message(email, subject="盈航使用次数已增加", text=text, html=html)
        return {"sent": True, "email": _mask_email(email)}
    except Exception as exc:
        return {"sent": False, "error": str(exc)}


def _smtp_message(email: str, *, subject: str, text: str, html: str | None = None) -> EmailMessage:
    sender = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "")).strip()
    sender_name = os.getenv("SMTP_FROM_NAME", "盈航").strip()
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{sender_name} <{sender}>"
    message["To"] = email
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

    def __init__(self) -> None:
        self._server: smtplib.SMTP | smtplib.SMTP_SSL | None = None

    def _connect(self) -> smtplib.SMTP | smtplib.SMTP_SSL:
        host, port, username, password, _sender, use_ssl = _smtp_connection_settings()
        if use_ssl:
            server: smtplib.SMTP | smtplib.SMTP_SSL = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls()
        server.login(username, password)
        self._server = server
        return server

    def send(self, email: str, *, subject: str, text: str, html: str | None = None) -> None:
        message = _smtp_message(email, subject=subject, text=text, html=html)
        for reconnect_attempt in range(2):
            try:
                server = self._server or self._connect()
                server.send_message(message)
                return
            except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, OSError, EOFError):
                self.close()
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


def _send_smtp_message(email: str, *, subject: str, text: str, html: str | None = None) -> None:
    host, port, username, password, _sender, use_ssl = _smtp_connection_settings()

    message = _smtp_message(email, subject=subject, text=text, html=html)

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=15) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(message)


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
        "status": row["status"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "published_at": row["published_at"],
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
    users = conn.execute("SELECT id, email, email_verified, update_emails_enabled FROM users ORDER BY id").fetchall()
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
    return {
        "id": int(row["id"]),
        "trade_date": str(row["trade_date"]),
        "report_id": str(row["report_id"]),
        "status": str(row["status"]),
        "total": sum(counts.values()),
        "pending": counts.get("pending", 0),
        "sending": counts.get("sending", 0),
        "sent": counts.get("sent", 0),
        "failed": counts.get("failed", 0),
        "skipped": counts.get("skipped", 0),
        "full": variants.get("full", 0),
        "teaser": variants.get("teaser", 0),
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


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
    site_url = os.getenv("PUBLIC_SITE_URL", "").strip().rstrip("/")
    if not site_url:
        raise AuthError("PUBLIC_SITE_URL 未配置", 500)
    text_items = "\n".join(f"- {item}" for item in items)
    text = f"盈航产品更新：{title}\n\n版本/日期：{version}\n\n{text_items}\n\n查看网站：{site_url}\n"
    html_items = "".join(
        f'<li style="margin:8px 0;color:#1f2328;line-height:1.7;">{_html_escape(item)}</li>' for item in items
    )
    html = _light_email_document(f"""
      <p style="margin:0 0 8px;color:#57606a;font-size:13px;">盈航 · 产品更新</p>
      <h1 style="margin:0 0 12px;color:#1f2328;font-size:24px;line-height:1.35;">{_html_escape(title)}</h1>
      <p style="margin:0 0 20px;color:#57606a;font-size:14px;">{_html_escape(version)}</p>
      <ul style="margin:0 0 20px;padding-left:24px;color:#1f2328;">{html_items}</ul>
      <p style="margin:0 0 8px;color:#1f2328;"><a href="{_html_escape(site_url)}" style="color:#0969da;text-decoration:underline;">打开盈航查看</a></p>
      <p style="margin:0 0 20px;color:#57606a;font-size:13px;word-break:break-all;">{_html_escape(site_url)}</p>
      <p style="margin:0;color:#57606a;font-size:12px;line-height:1.6;">你可以登录盈航，在账户菜单中关闭产品更新邮件。</p>
    """, max_width=600)
    send = smtp_session.send if smtp_session is not None else _send_smtp_message
    send(str(delivery["email"]), subject=f"盈航产品更新｜{title}", text=text, html=html)


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
      <p style="margin:0;color:#57606a;font-size:12px;line-height:1.6;">可登录盈航，在账户菜单中关闭“邮件推送（产品更新与每日 TOP5）”。</p>
    """, max_width=720)
    send = smtp_session.send if smtp_session is not None else _send_smtp_message
    send(str(delivery["email"]), subject=f"盈航每日 TOP5｜{trade_date}", text=text, html=html)


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


def _normalize_update_notice_input(
    title: str,
    version: str,
    items: list[Any],
    status: str,
) -> tuple[str, str, list[str], str]:
    title = str(title or "").strip()[:80]
    version = str(version or "").strip()[:40]
    status = str(status or "draft").strip()
    if status not in {"draft", "published"}:
        raise AuthError("更新公告状态不正确", 400)
    if not title:
        raise AuthError("更新公告标题不能为空", 400)
    if not version:
        raise AuthError("更新公告版本不能为空", 400)
    if not isinstance(items, list):
        raise AuthError("更新公告内容必须是列表", 400)
    normalized_items = [str(item).strip()[:240] for item in items if str(item).strip()]
    if not normalized_items:
        raise AuthError("更新公告内容不能为空", 400)
    return title, version, normalized_items[:12], status


def _amount_yuan_to_cents(value: str) -> int:
    try:
        amount = Decimal(str(value or "0").strip())
    except Exception as exc:
        raise AuthError("支付金额格式不正确", 400) from exc
    if amount < 0:
        raise AuthError("支付金额不正确", 400)
    return int((amount * Decimal("100")).quantize(Decimal("1")))
