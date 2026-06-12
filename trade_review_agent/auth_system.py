from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


CN_TZ = ZoneInfo("Asia/Shanghai")
PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
SESSION_DAYS = 30
INITIAL_FREE_CREDITS = 1
REFERRAL_REWARD_CREDITS = 5
FEEDBACK_REWARD_CREDITS = 10
SMS_CODE_TTL_MINUTES = 5
SMS_RESEND_SECONDS = 60
EMAIL_CODE_TTL_MINUTES = 10
EMAIL_RESEND_SECONDS = 60


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

            CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_events(created_at);
            CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback(status);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
            CREATE INDEX IF NOT EXISTS idx_sms_codes_phone ON sms_codes(phone, purpose, created_at);
            CREATE INDEX IF NOT EXISTS idx_email_codes_email ON email_codes(email, purpose, created_at);
            """
        )
        _ensure_user_columns(conn)
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
        if provider_result.get("debug_code"):
            payload["debug_code"] = provider_result["debug_code"]
        return payload


def register_user(db_path: Path, *, phone: str, code: str, invite_code: str = "", ip: str = "") -> dict[str, Any]:
    phone = normalize_phone(phone)
    invite_code = invite_code.strip()
    now = _now()
    with _connect(db_path) as conn:
        _verify_sms_code(conn, phone, code, purpose="login")
        existing_ip = _ip_registered_user(conn, ip)
        if existing_ip:
            raise AuthError("当前 IP 已注册过账号，请直接登录或联系管理员", 409)
        if _fetch_user_by_phone(conn, phone):
            raise AuthError("手机号已注册，请直接登录", 409)

        referrer = _fetch_user_by_invite_code(conn, invite_code) if invite_code else None
        salt, password_hash = _hash_password(secrets.token_urlsafe(24))
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
) -> dict[str, Any]:
    username = normalize_username(username)
    email = normalize_email(email)
    _validate_password(password)
    invite_code = invite_code.strip()
    now = _now()
    with _connect(db_path) as conn:
        _verify_email_code(conn, email, email_code, purpose="register")
        existing_ip = _ip_registered_user(conn, ip)
        if existing_ip:
            raise AuthError("当前 IP 已注册过账号，请直接登录或联系管理员", 409)
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

        balance = _credit_balance(conn, user_id)
        if balance <= 0:
            _record_usage(conn, user_id, feature, 0, "blocked_no_credits", ip, related_id)
            raise AuthError("免费次数已用完，请邀请新用户注册登录获取次数，或购买次数后继续使用", 402)
        _add_credits(conn, user_id, -1, f"use_{feature}", related_id or None)
        _record_usage(conn, user_id, feature, 1, "charged", ip, related_id)
        return _user_payload(conn, user)


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


def create_order(db_path: Path, *, user_id: int, plan_name: str, credits: int, amount_cents: int) -> dict[str, Any]:
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
            SELECT o.*, u.phone
            FROM orders o
            JOIN users u ON u.id = o.user_id
            ORDER BY o.created_at DESC
            LIMIT 50
            """
        ).fetchall()
        top_users = conn.execute(
            """
            SELECT u.id, u.phone, u.role, u.created_at, COALESCE(SUM(e.credits_spent), 0) AS used_count,
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
            "orders": [_order_payload(row) | {"phone": row["phone"]} for row in orders],
            "top_users": [dict(row) for row in top_users],
        }


def review_feedback(db_path: Path, *, feedback_id: int, status: str, admin_note: str = "") -> dict[str, Any]:
    status = status.strip()
    if status not in {"pending", "accepted", "rejected"}:
        raise AuthError("反馈状态不正确", 400)
    now = _now()
    with _connect(db_path) as conn:
        feedback = conn.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
        if not feedback:
            raise AuthError("反馈不存在", 404)
        reward = 0
        if status == "accepted" and feedback["reward_credits"] <= 0:
            reward = FEEDBACK_REWARD_CREDITS
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
        return _feedback_payload(updated)


def mark_order_paid(db_path: Path, *, order_id: int) -> dict[str, Any]:
    now = _now()
    with _connect(db_path) as conn:
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order:
            raise AuthError("订单不存在", 404)
        if order["status"] != "paid":
            conn.execute("UPDATE orders SET status = 'paid', paid_at = ? WHERE id = ?", (now, order_id))
            _add_credits(conn, int(order["user_id"]), int(order["credits"]), "order_paid", str(order_id))
        updated = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return _order_payload(updated)


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


def _normalize_sms_purpose(purpose: str) -> str:
    value = (purpose or "login").strip().lower()
    return value if value in {"login"} else "login"


def _normalize_email_purpose(purpose: str) -> str:
    value = (purpose or "register").strip().lower()
    return value if value in {"register"} else "register"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_admin(conn: sqlite3.Connection) -> None:
    phone = os.getenv("ADMIN_PHONE", "admin").strip()
    password = os.getenv("ADMIN_PASSWORD", "admin123456").strip()
    row = conn.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
    if row:
        conn.execute("UPDATE users SET username = COALESCE(username, ?) WHERE id = ?", (phone, row["id"]))
        return
    salt, password_hash = _hash_password(password)
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
    provider = os.getenv("EMAIL_PROVIDER", "log").strip().lower() or "log"
    if provider in {"log", "debug", "local"}:
        _write_email_debug_log(email, code, log_path)
        return {"provider": "log", "debug_code": code}
    if provider == "smtp":
        _send_smtp_email(email, code)
        return {"provider": "smtp"}
    raise AuthError(f"不支持的邮件服务商：{provider}", 500)


def _send_smtp_email(email: str, code: str) -> None:
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "465").strip() or "465")
    username = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    sender = os.getenv("SMTP_FROM", username).strip()
    sender_name = os.getenv("SMTP_FROM_NAME", "盈航").strip()
    if not host or not username or not password or not sender:
        raise AuthError("SMTP 邮件服务未配置完整，请检查 SMTP_HOST/SMTP_USER/SMTP_PASSWORD/SMTP_FROM", 500)

    message = EmailMessage()
    message["Subject"] = "盈航登录注册验证码"
    message["From"] = f"{sender_name} <{sender}>"
    message["To"] = email
    message.set_content(
        f"你的盈航验证码是：{code}\n\n验证码 {EMAIL_CODE_TTL_MINUTES} 分钟内有效。若不是你本人操作，请忽略这封邮件。\n"
    )
    message.add_alternative(
        f"""
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
        """,
        subtype="html",
    )

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


def _user_payload(conn: sqlite3.Connection, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    user_id = int(row["id"])
    referral_count = conn.execute(
        "SELECT COUNT(*) AS count FROM referrals WHERE referrer_user_id = ? AND status = 'completed'",
        (user_id,),
    ).fetchone()["count"]
    return {
        "id": user_id,
        "phone": row["phone"],
        "username": row["username"] if "username" in row.keys() else "",
        "email": row["email"] if "email" in row.keys() else "",
        "role": row["role"],
        "invite_code": row["invite_code"],
        "credits": _credit_balance(conn, user_id),
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
    }


def _now() -> str:
    return datetime.now(CN_TZ).isoformat()
