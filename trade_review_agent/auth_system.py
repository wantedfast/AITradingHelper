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
from typing import Any, Iterator
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
SESSION_DAYS = 30
INITIAL_FREE_CREDITS = 5
REFERRAL_REWARD_CREDITS = 5
INVITEE_BONUS_CREDITS = 2
FEEDBACK_REWARD_CREDITS = 10
SMS_CODE_TTL_MINUTES = 5
SMS_RESEND_SECONDS = 60
EMAIL_CODE_TTL_MINUTES = 10
EMAIL_RESEND_SECONDS = 60
CREDIT_PACKAGES = {
    "pack_10": {"plan_name": "10 次使用包", "credits": 10, "amount_cents": 990},
    "pack_50": {"plan_name": "50 次使用包", "credits": 50, "amount_cents": 3990},
    "pack_120": {"plan_name": "120 次使用包", "credits": 120, "amount_cents": 7990},
}
MONTHLY_MEMBERSHIP_PLAN = {
    "id": "monthly_membership",
    "plan_name": os.getenv("PAYMENT_MONTHLY_PLAN_NAME", "月度会员"),
    "amount_cents": int(os.getenv("PAYMENT_MONTHLY_AMOUNT_CENTS", "5900") or "5900"),
    "duration_days": 31,
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
            CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback(status);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
            CREATE INDEX IF NOT EXISTS idx_update_notices_status ON update_notices(status, published_at);
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
        if EMAIL_RE.match(account):
            user = _fetch_user_by_email(conn, normalize_email(account))
        elif account.isdigit():
            user = _fetch_user_by_phone(conn, account)
        else:
            admin_phone = os.getenv("ADMIN_PHONE", "admin").strip()
            user = _fetch_user_by_phone(conn, account) if account == admin_phone else _fetch_user_by_username(conn, account)
        if not user or not _verify_password(password, user["password_salt"], user["password_hash"]):
            raise AuthError("账号/邮箱或密码错误", 401)
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

        balance = _credit_balance(conn, user_id)
        if balance <= 0:
            _record_usage(conn, user_id, feature, 0, "blocked_no_credits", ip, related_id)
            raise AuthError("免费次数已用完，请邀请新用户注册登录获取次数，或购买次数后继续使用", 402)
        _add_credits(conn, user_id, -1, f"use_{feature}", related_id or None)
        _record_usage(conn, user_id, feature, 1, "charged", ip, related_id)
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

        balance = _credit_balance(conn, user_id)
        if balance <= 0:
            _record_usage(conn, user_id, feature, 0, "blocked_no_credits", ip, related_id)
            raise AuthError("免费次数已用完，请邀请新用户注册登录获取次数，或购买次数后继续使用", 402)
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

        balance = _credit_balance(conn, user_id)
        if balance < cost:
            _record_usage(conn, user_id, feature, 0, "blocked_no_credits", ip, related_id)
            raise AuthError("免费次数已用完，请邀请新用户注册登录获取次数，或购买次数后继续使用", 402)
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
    plan = _membership_plan()
    return [
        {
            **plan,
            "alipay_qr_url": os.getenv("PAYMENT_ALIPAY_QR_URL", "/pay/alipay-qr.png").strip(),
            "wechat_qr_url": os.getenv("PAYMENT_WECHAT_QR_URL", "/pay/wechat-qr.png").strip(),
        }
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
    plan = _membership_plan()
    if plan_id and plan_id != plan["id"]:
        raise AuthError("未知的会员套餐", 400)
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
    start_date = (datetime.now(CN_TZ).date() - timedelta(days=days - 1)).isoformat()
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
        return {
            "totals": totals,
            "usage_by_day": [dict(row) for row in usage_rows],
            "new_users_by_day": [dict(row) for row in user_rows],
            "feedback": [_feedback_payload(row) for row in feedback_rows],
            "orders": [_order_payload(row) | {"phone": row["phone"], "username": row["username"], "email": row["email"]} for row in orders],
            "top_users": [dict(row) for row in top_users],
            "update_notices": [_update_notice_payload(row) for row in _update_notice_rows(conn)],
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
        return [_update_notice_payload(row) for row in _update_notice_rows(conn, limit=limit)]


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


def publish_update_notice(db_path: Path, *, notice_id: int) -> dict[str, Any]:
    with _connect(db_path) as conn:
        existing = conn.execute("SELECT * FROM update_notices WHERE id = ?", (notice_id,)).fetchone()
        if not existing:
            raise AuthError("更新公告不存在", 404)
        now = _now()
        conn.execute(
            """
            UPDATE update_notices
            SET status = 'published', published_at = COALESCE(published_at, ?), updated_at = ?
            WHERE id = ?
            """,
            (now, now, notice_id),
        )
        return _update_notice_payload(conn.execute("SELECT * FROM update_notices WHERE id = ?", (notice_id,)).fetchone())


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
        subject = f"【盈航】用户已付款待确认 - 59元/月会员 - 订单号 {order.get('order_no')}"
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
        html = f"""
        <html>
          <body style="font-family:Arial,'Microsoft YaHei',sans-serif;background:#050505;color:#f4f0e8;padding:24px;">
            <div style="max-width:640px;margin:auto;border:1px solid #c9a64655;border-radius:16px;padding:24px;background:#111;">
              <h2 style="margin:0 0 16px;color:#f5d77a;">用户已付款待确认</h2>
              <p>请核对支付宝/微信到账后，再到管理台确认开通会员。</p>
              <p><strong>订单号：</strong>{_html_escape(str(order.get('order_no') or ''))}</p>
              <p><strong>用户：</strong>{_html_escape(str(user_label))}</p>
              <p><strong>账号：</strong>{_html_escape(str(user.get('phone') or ''))}</p>
              <p><strong>邮箱：</strong>{_html_escape(str(user.get('email') or ''))}</p>
              <p><strong>套餐：</strong>{_html_escape(str(order.get('plan_name') or ''))}</p>
              <p><strong>应付金额：</strong>¥{amount:.2f}</p>
              <p><strong>支付方式：</strong>{_html_escape(payment_method)}</p>
              <p><strong>付款人：</strong>{_html_escape(str(order.get('payer_name') or ''))}</p>
              <p><strong>付款时间：</strong>{_html_escape(str(order.get('payer_paid_at') or ''))}</p>
              <p><strong>实付金额：</strong>¥{submitted_amount:.2f}</p>
              <p><strong>付款备注：</strong>{_html_escape(str(order.get('payer_note') or ''))}</p>
              <p><strong>管理后台：</strong>{_html_escape(admin_url)}</p>
            </div>
          </body>
        </html>
        """
        provider = os.getenv("EMAIL_PROVIDER", "smtp").strip().lower() or "smtp"
        if provider in {"log", "debug", "local"}:
            _write_email_debug_log(admin_email, text, None)
            return {"sent": False, "skipped": True, "provider": "log", "email": _mask_email(admin_email), "error": "EMAIL_PROVIDER=log，仅写入本地日志，未真实发送邮件"}
        _send_smtp_message(admin_email, subject=subject, text=text, html=html)
        return {"sent": True, "provider": "smtp", "email": _mask_email(admin_email)}
    except Exception as exc:
        return {"sent": False, "error": str(exc)}


def _membership_plan() -> dict[str, Any]:
    return {
        "id": "monthly_membership",
        "plan_name": os.getenv("PAYMENT_MONTHLY_PLAN_NAME", MONTHLY_MEMBERSHIP_PLAN["plan_name"]).strip() or "月度会员",
        "amount_cents": int(os.getenv("PAYMENT_MONTHLY_AMOUNT_CENTS", str(MONTHLY_MEMBERSHIP_PLAN["amount_cents"])) or "5900"),
        "duration_days": int(os.getenv("PAYMENT_MONTHLY_DURATION_DAYS", str(MONTHLY_MEMBERSHIP_PLAN["duration_days"])) or "31"),
    }


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
    return value if value in {"register"} else "register"


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
    html = f"""
        <html>
          <body style="font-family:Arial,'Microsoft YaHei',sans-serif;background:#050505;color:#f4f0e8;padding:24px;">
            <div style="max-width:520px;margin:auto;border:1px solid #c9a64655;border-radius:16px;padding:24px;background:#111;">
              <h2 style="margin:0 0 16px;color:#f5d77a;">盈航验证码</h2>
              <p>你的验证码是：</p>
              <p style="font-size:32px;letter-spacing:6px;font-weight:800;color:#f5d77a;">{code}</p>
              <p>验证码 {EMAIL_CODE_TTL_MINUTES} 分钟内有效。若不是你本人操作，请忽略这封邮件。</p>
            </div>
          </body>
        </html>
        """
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
        html = f"""
        <html>
          <body style="font-family:Arial,'Microsoft YaHei',sans-serif;background:#050505;color:#f4f0e8;padding:24px;">
            <div style="max-width:560px;margin:auto;border:1px solid #c9a64655;border-radius:16px;padding:24px;background:#111;">
              <h2 style="margin:0 0 16px;color:#f5d77a;">盈航使用次数已增加</h2>
              <p>{username}，你好：</p>
              <p>你的盈航账号已增加 <strong style="color:#f5d77a;font-size:20px;">{credits}</strong> 次使用机会。</p>
              <p><strong>增加原因：</strong>{_html_escape(reason)}</p>
              <p><strong>当前剩余次数：</strong>{balance} 次。</p>
              <p style="color:#aaa;font-size:13px;">如有疑问，请联系平台管理员。</p>
            </div>
          </body>
        </html>
        """
        _send_smtp_message(email, subject="盈航使用次数已增加", text=text, html=html)
        return {"sent": True, "email": _mask_email(email)}
    except Exception as exc:
        return {"sent": False, "error": str(exc)}


def _send_smtp_message(email: str, *, subject: str, text: str, html: str | None = None) -> None:
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "465").strip() or "465")
    username = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    sender = os.getenv("SMTP_FROM", username).strip()
    sender_name = os.getenv("SMTP_FROM_NAME", "盈航").strip()
    if not host or not username or not password or not sender:
        raise AuthError("SMTP 邮件服务未配置完整，请检查 SMTP_HOST/SMTP_USER/SMTP_PASSWORD/SMTP_FROM", 500)

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{sender_name} <{sender}>"
    message["To"] = email
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")

    use_ssl = os.getenv("SMTP_USE_SSL", "1").strip().lower() not in {"0", "false", "no"}
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
          AND status IN ('charged', 'admin_free')
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
    return {
        "id": user_id,
        "phone": row["phone"],
        "username": row["username"] if "username" in row.keys() else "",
        "email": row["email"] if "email" in row.keys() else "",
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


def _update_notice_payload(row: sqlite3.Row) -> dict[str, Any]:
    try:
        items = json.loads(row["items_json"] or "[]")
    except Exception:
        items = []
    if not isinstance(items, list):
        items = []
    return {
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
