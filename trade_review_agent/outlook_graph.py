from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests
from cryptography.fernet import Fernet, InvalidToken


CN_TZ = ZoneInfo("Asia/Shanghai")
GRAPH_SCOPE = "openid offline_access Mail.Send"
SUPPORTED_PROVIDERS = {"smtp", "outlook_graph", "log"}
_RUNTIME_DB_PATH: Path | None = None
_TOKEN_LOCK = threading.Lock()


class OutlookGraphError(RuntimeError):
    def __init__(self, message: str, *, reconnect_required: bool = False, retryable: bool = False) -> None:
        super().__init__(message)
        self.reconnect_required = reconnect_required
        self.retryable = retryable


@dataclass(frozen=True)
class OutlookGraphConfig:
    client_id: str
    client_secret: str
    tenant: str
    redirect_uri: str
    sender: str
    encryption_key: str


def _now() -> str:
    return datetime.now(CN_TZ).isoformat()


@contextmanager
def _connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _config() -> OutlookGraphConfig:
    return OutlookGraphConfig(
        client_id=os.getenv("OUTLOOK_GRAPH_CLIENT_ID", "").strip(),
        client_secret=os.getenv("OUTLOOK_GRAPH_CLIENT_SECRET", "").strip(),
        tenant=os.getenv("OUTLOOK_GRAPH_TENANT", "consumers").strip() or "consumers",
        redirect_uri=os.getenv("OUTLOOK_GRAPH_REDIRECT_URI", "").strip(),
        sender=os.getenv("OUTLOOK_GRAPH_FROM", "").strip(),
        encryption_key=os.getenv("OUTLOOK_GRAPH_TOKEN_ENCRYPTION_KEY", "").strip(),
    )


def _configured(config: OutlookGraphConfig | None = None) -> bool:
    value = config or _config()
    return bool(value.client_id and value.sender and value.encryption_key)


def _fernet(config: OutlookGraphConfig | None = None) -> Fernet:
    value = config or _config()
    if not value.encryption_key:
        raise OutlookGraphError("Outlook Graph 令牌加密密钥未配置")
    try:
        return Fernet(value.encryption_key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise OutlookGraphError("Outlook Graph 令牌加密密钥格式无效") from exc


def _encrypt(value: str, config: OutlookGraphConfig | None = None) -> str:
    return _fernet(config).encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt(value: str, config: OutlookGraphConfig | None = None) -> str:
    try:
        return _fernet(config).decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise OutlookGraphError("Outlook Graph 授权凭据无法解密，请重新连接", reconnect_required=True) from exc


def _mask_email(value: str) -> str:
    if "@" not in value:
        return ""
    local, domain = value.split("@", 1)
    visible = local[:2]
    return f"{visible}{'*' * max(len(local) - len(visible), 2)}@{domain}"


def _smtp_configured() -> bool:
    return bool(
        os.getenv("SMTP_HOST", "").strip()
        and os.getenv("SMTP_USER", "").strip()
        and os.getenv("SMTP_PASSWORD", "").strip()
        and os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "")).strip()
    )


def _assert_active_admin(conn: sqlite3.Connection, admin_user_id: int) -> None:
    row = conn.execute("SELECT role, status FROM users WHERE id = ?", (int(admin_user_id),)).fetchone()
    if not row or str(row["role"] or "") != "admin" or str(row["status"] or "") != "active":
        raise OutlookGraphError("发起 Outlook 授权的管理员已失效，请由当前管理员重新连接")


def init_outlook_graph_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS email_provider_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            active_provider TEXT NOT NULL DEFAULT 'smtp',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS outlook_graph_credentials (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            access_token_encrypted TEXT NOT NULL,
            refresh_token_encrypted TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT '',
            connected_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            reconnect_required INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS outlook_graph_oauth_states (
            state_hash TEXT PRIMARY KEY,
            code_verifier_encrypted TEXT NOT NULL,
            admin_user_id INTEGER NOT NULL,
            redirect_path TEXT NOT NULL DEFAULT '/admin/emails',
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS outlook_graph_device_codes (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            device_code_encrypted TEXT NOT NULL,
            admin_user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            interval_seconds INTEGER NOT NULL DEFAULT 5,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_outlook_graph_oauth_states_expiry
            ON outlook_graph_oauth_states(expires_at, used_at);
        """
    )
    configured_default = os.getenv("EMAIL_PROVIDER", "smtp").strip().lower() or "smtp"
    if configured_default not in SUPPORTED_PROVIDERS:
        configured_default = "smtp"
    conn.execute(
        "INSERT OR IGNORE INTO email_provider_settings (id, active_provider, updated_at) VALUES (1, ?, ?)",
        (configured_default, _now()),
    )


def configure_outlook_graph_runtime(db_path: Path) -> None:
    global _RUNTIME_DB_PATH
    _RUNTIME_DB_PATH = Path(db_path)
    with _connect(_RUNTIME_DB_PATH) as conn:
        row = conn.execute("SELECT active_provider FROM email_provider_settings WHERE id = 1").fetchone()
    if row and str(row["active_provider"] or "") in SUPPORTED_PROVIDERS:
        os.environ["EMAIL_PROVIDER"] = str(row["active_provider"])


def _runtime_db_path() -> Path:
    if _RUNTIME_DB_PATH is None:
        raise OutlookGraphError("Outlook Graph 运行时尚未初始化")
    return _RUNTIME_DB_PATH


def provider_status(db_path: Path, *, worker_count: int | None = None) -> dict[str, Any]:
    config = _config()
    with _connect(db_path) as conn:
        setting = conn.execute("SELECT active_provider, updated_at FROM email_provider_settings WHERE id = 1").fetchone()
        credential = conn.execute(
            "SELECT connected_at, updated_at, reconnect_required, last_error FROM outlook_graph_credentials WHERE id = 1"
        ).fetchone()
    active = str(setting["active_provider"] if setting else os.getenv("EMAIL_PROVIDER", "smtp"))
    payload: dict[str, Any] = {
        "provider": active if active in SUPPORTED_PROVIDERS else "smtp",
        "smtp": {
            "configured": _smtp_configured(),
            "from_masked": _mask_email(os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "")).strip()),
        },
        "outlook": {
            "configured": _configured(config),
            "connected": bool(credential and not int(credential["reconnect_required"] or 0)),
            "account_masked": _mask_email(config.sender),
            "connected_at": str(credential["connected_at"] or "") if credential else "",
            "updated_at": str(credential["updated_at"] or "") if credential else "",
            "reconnect_required": bool(credential and int(credential["reconnect_required"] or 0)),
            "last_error": str(credential["last_error"] or "") if credential else "",
        },
    }
    if worker_count is not None:
        payload["worker_count"] = int(worker_count)
    return payload


def begin_outlook_connection(db_path: Path, *, admin_user_id: int, redirect_path: str = "/admin/emails") -> dict[str, str]:
    config = _config()
    if not _configured(config):
        raise OutlookGraphError("Outlook Graph 尚未配置完整，请检查 CLIENT_ID、FROM 和令牌加密密钥")
    if not config.redirect_uri:
        return begin_outlook_device_connection(db_path, admin_user_id=admin_user_id)
    safe_redirect_path = redirect_path if redirect_path == "/admin/emails" else "/admin/emails"
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    now_dt = datetime.now(CN_TZ)
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM outlook_graph_oauth_states WHERE expires_at < ? OR used_at IS NOT NULL", (now_dt.isoformat(),))
        conn.execute(
            """
            INSERT INTO outlook_graph_oauth_states (
                state_hash, code_verifier_encrypted, admin_user_id, redirect_path, expires_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                hashlib.sha256(state.encode("utf-8")).hexdigest(),
                _encrypt(verifier, config),
                int(admin_user_id),
                safe_redirect_path,
                (now_dt + timedelta(minutes=10)).isoformat(),
                now_dt.isoformat(),
            ),
        )
    query = urlencode(
        {
            "client_id": config.client_id,
            "response_type": "code",
            "redirect_uri": config.redirect_uri,
            "response_mode": "query",
            "scope": GRAPH_SCOPE,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    return {
        "mode": "authorization_code",
        "authorization_url": f"https://login.microsoftonline.com/{config.tenant}/oauth2/v2.0/authorize?{query}",
        "expires_at": (now_dt + timedelta(minutes=10)).isoformat(),
    }


def begin_outlook_device_connection(db_path: Path, *, admin_user_id: int) -> dict[str, str]:
    config = _config()
    if not _configured(config):
        raise OutlookGraphError("Outlook Graph 尚未配置完整，请检查 CLIENT_ID、FROM 和令牌加密密钥")
    try:
        response = requests.post(
            f"https://login.microsoftonline.com/{config.tenant}/oauth2/v2.0/devicecode",
            data={"client_id": config.client_id, "scope": GRAPH_SCOPE},
            timeout=20,
        )
    except requests.RequestException as exc:
        raise OutlookGraphError("连接微软设备授权服务失败，请稍后重试", retryable=True) from exc
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code >= 400 or not str(payload.get("device_code") or ""):
        raise OutlookGraphError(_safe_oauth_error(payload, fallback="微软设备授权初始化失败"))
    now_dt = datetime.now(CN_TZ)
    expires_in = max(int(payload.get("expires_in") or 900), 60)
    interval = max(min(int(payload.get("interval") or 5), 30), 3)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO outlook_graph_device_codes (
                id, device_code_encrypted, admin_user_id, expires_at, interval_seconds, created_at
            ) VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                device_code_encrypted = excluded.device_code_encrypted,
                admin_user_id = excluded.admin_user_id,
                expires_at = excluded.expires_at,
                interval_seconds = excluded.interval_seconds,
                created_at = excluded.created_at
            """,
            (
                _encrypt(str(payload["device_code"]), config),
                int(admin_user_id),
                (now_dt + timedelta(seconds=expires_in)).isoformat(),
                interval,
                now_dt.isoformat(),
            ),
        )
    verification_uri = str(payload.get("verification_uri") or payload.get("verification_url") or "https://microsoft.com/devicelogin")
    return {
        "mode": "device_code",
        "verification_uri": verification_uri,
        "user_code": str(payload.get("user_code") or ""),
        "expires_at": (now_dt + timedelta(seconds=expires_in)).isoformat(),
        "interval_seconds": str(interval),
    }


def _safe_oauth_error(payload: dict[str, Any], *, fallback: str) -> str:
    code = str(payload.get("error") or "").strip()
    if code:
        return f"{fallback}（{code[:80]}）"
    return fallback


def _token_request(config: OutlookGraphConfig, form: dict[str, str]) -> dict[str, Any]:
    request_form = dict(form)
    request_form["client_id"] = config.client_id
    if config.client_secret:
        request_form["client_secret"] = config.client_secret
    try:
        response = requests.post(
            f"https://login.microsoftonline.com/{config.tenant}/oauth2/v2.0/token",
            data=request_form,
            timeout=20,
        )
    except requests.RequestException as exc:
        raise OutlookGraphError("连接微软授权服务失败，请稍后重试", retryable=True) from exc
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code >= 400:
        reconnect = str(payload.get("error") or "") in {"invalid_grant", "interaction_required"}
        raise OutlookGraphError(
            _safe_oauth_error(payload, fallback="微软授权失败，请重新连接" if reconnect else "微软授权服务暂时不可用"),
            reconnect_required=reconnect,
            retryable=response.status_code >= 500 or response.status_code == 429,
        )
    if not str(payload.get("access_token") or ""):
        raise OutlookGraphError("微软授权响应缺少访问令牌")
    return payload


def _store_token_payload(db_path: Path, payload: dict[str, Any], *, require_refresh_token: bool = True) -> None:
    config = _config()
    refresh_token = str(payload.get("refresh_token") or "")
    if require_refresh_token and not refresh_token:
        raise OutlookGraphError("微软未返回长期授权令牌，请确认已授予 offline_access")
    expires_at = (datetime.now(CN_TZ) + timedelta(seconds=max(int(payload.get("expires_in") or 3600), 60))).isoformat()
    with _connect(db_path) as conn:
        existing = conn.execute("SELECT refresh_token_encrypted FROM outlook_graph_credentials WHERE id = 1").fetchone()
        if not refresh_token and existing:
            refresh_token = _decrypt(str(existing["refresh_token_encrypted"]), config)
        if not refresh_token:
            raise OutlookGraphError("微软未返回长期授权令牌，请重新连接")
        conn.execute(
            """
            INSERT INTO outlook_graph_credentials (
                id, access_token_encrypted, refresh_token_encrypted, expires_at, scope,
                connected_at, updated_at, reconnect_required, last_error
            ) VALUES (1, ?, ?, ?, ?, ?, ?, 0, '')
            ON CONFLICT(id) DO UPDATE SET
                access_token_encrypted = excluded.access_token_encrypted,
                refresh_token_encrypted = excluded.refresh_token_encrypted,
                expires_at = excluded.expires_at,
                scope = excluded.scope,
                connected_at = excluded.connected_at,
                updated_at = excluded.updated_at,
                reconnect_required = 0,
                last_error = ''
            """,
            (
                _encrypt(str(payload["access_token"]), config),
                _encrypt(refresh_token, config),
                expires_at,
                str(payload.get("scope") or GRAPH_SCOPE),
                _now(),
                _now(),
            ),
        )


def complete_outlook_connection(db_path: Path, *, state: str, code: str) -> str:
    config = _config()
    if not _configured(config) or not state or not code:
        raise OutlookGraphError("Outlook 授权回调参数无效")
    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    now_dt = datetime.now(CN_TZ)
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT * FROM outlook_graph_oauth_states
            WHERE state_hash = ? AND used_at IS NULL AND expires_at >= ?
            """,
            (state_hash, now_dt.isoformat()),
        ).fetchone()
        if not row:
            raise OutlookGraphError("Outlook 授权状态已过期或已使用，请重新连接")
        _assert_active_admin(conn, int(row["admin_user_id"]))
        conn.execute("UPDATE outlook_graph_oauth_states SET used_at = ? WHERE state_hash = ?", (now_dt.isoformat(), state_hash))
        redirect_path = str(row["redirect_path"] or "/admin/emails")
        verifier = _decrypt(str(row["code_verifier_encrypted"]), config)
    payload = _token_request(
        config,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.redirect_uri,
            "code_verifier": verifier,
            "scope": GRAPH_SCOPE,
        },
    )
    _store_token_payload(db_path, payload)
    return redirect_path if redirect_path == "/admin/emails" else "/admin/emails"


def poll_outlook_device_connection(db_path: Path, *, admin_user_id: int) -> dict[str, Any]:
    config = _config()
    if not _configured(config):
        raise OutlookGraphError("Outlook Graph 尚未配置完整")
    now_dt = datetime.now(CN_TZ)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM outlook_graph_device_codes WHERE id = 1").fetchone()
    if not row or int(row["admin_user_id"]) != int(admin_user_id):
        raise OutlookGraphError("没有等待确认的 Outlook 设备授权，请重新连接")
    with _connect(db_path) as conn:
        _assert_active_admin(conn, int(admin_user_id))
    if datetime.fromisoformat(str(row["expires_at"])).astimezone(CN_TZ) < now_dt:
        with _connect(db_path) as conn:
            conn.execute("DELETE FROM outlook_graph_device_codes WHERE id = 1")
        return {"status": "expired", "connected": False}
    device_code = _decrypt(str(row["device_code_encrypted"]), config)
    try:
        response = requests.post(
            f"https://login.microsoftonline.com/{config.tenant}/oauth2/v2.0/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": config.client_id,
                "device_code": device_code,
            },
            timeout=20,
        )
    except requests.RequestException as exc:
        raise OutlookGraphError("连接微软授权服务失败，请稍后重试", retryable=True) from exc
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    error = str(payload.get("error") or "")
    if response.status_code >= 400:
        if error in {"authorization_pending", "slow_down"}:
            return {"status": "pending", "connected": False}
        with _connect(db_path) as conn:
            conn.execute("DELETE FROM outlook_graph_device_codes WHERE id = 1")
        if error in {"authorization_declined", "access_denied"}:
            return {"status": "declined", "connected": False}
        if error in {"expired_token", "bad_verification_code"}:
            return {"status": "expired", "connected": False}
        raise OutlookGraphError(_safe_oauth_error(payload, fallback="微软设备授权失败"))
    if not str(payload.get("access_token") or ""):
        raise OutlookGraphError("微软授权响应缺少访问令牌")
    _store_token_payload(db_path, payload)
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM outlook_graph_device_codes WHERE id = 1")
    return {"status": "connected", "connected": True}


def _mark_reconnect_required(db_path: Path, message: str) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE outlook_graph_credentials SET reconnect_required = 1, last_error = ?, updated_at = ? WHERE id = 1",
            (message[:300], _now()),
        )


def _access_token(db_path: Path, *, force_refresh: bool = False) -> str:
    config = _config()
    if not _configured(config):
        raise OutlookGraphError("Outlook Graph 尚未配置完整")
    with _TOKEN_LOCK:
        with _connect(db_path) as conn:
            row = conn.execute("SELECT * FROM outlook_graph_credentials WHERE id = 1").fetchone()
        if not row:
            raise OutlookGraphError("Outlook 尚未连接，请先在邮件管理中授权", reconnect_required=True)
        if int(row["reconnect_required"] or 0):
            raise OutlookGraphError("Outlook 授权已失效，请重新连接", reconnect_required=True)
        try:
            expires_at = datetime.fromisoformat(str(row["expires_at"])).astimezone(CN_TZ)
            if not force_refresh and expires_at > datetime.now(CN_TZ) + timedelta(seconds=90):
                return _decrypt(str(row["access_token_encrypted"]), config)
            refresh_token = _decrypt(str(row["refresh_token_encrypted"]), config)
            payload = _token_request(
                config,
                {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "scope": GRAPH_SCOPE,
                },
            )
        except OutlookGraphError as exc:
            if exc.reconnect_required:
                _mark_reconnect_required(db_path, str(exc))
            raise
        next_refresh_token = str(payload.get("refresh_token") or refresh_token)
        next_expiry = (datetime.now(CN_TZ) + timedelta(seconds=max(int(payload.get("expires_in") or 3600), 60))).isoformat()
        with _connect(db_path) as conn:
            conn.execute(
                """
                UPDATE outlook_graph_credentials
                SET access_token_encrypted = ?, refresh_token_encrypted = ?, expires_at = ?,
                    scope = ?, updated_at = ?, reconnect_required = 0, last_error = ''
                WHERE id = 1
                """,
                (
                    _encrypt(str(payload["access_token"]), config),
                    _encrypt(next_refresh_token, config),
                    next_expiry,
                    str(payload.get("scope") or GRAPH_SCOPE),
                    _now(),
                ),
            )
        return str(payload["access_token"])


def send_outlook_mime(message_bytes: bytes) -> None:
    db_path = _runtime_db_path()
    encoded = base64.b64encode(message_bytes).decode("ascii")
    token = _access_token(db_path)
    for attempt in range(2):
        try:
            response = requests.post(
                "https://graph.microsoft.com/v1.0/me/sendMail",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "text/plain"},
                data=encoded,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise OutlookGraphError("Outlook 邮件服务连接失败，请稍后重试", retryable=True) from exc
        if response.status_code == 202:
            return
        if response.status_code == 401 and attempt == 0:
            token = _access_token(db_path, force_refresh=True)
            continue
        if response.status_code in {401, 403}:
            _mark_reconnect_required(db_path, "Outlook 授权已失效，请重新连接")
            raise OutlookGraphError("Outlook 授权已失效，请重新连接", reconnect_required=True)
        if response.status_code == 429 or response.status_code >= 500:
            raise OutlookGraphError("Outlook 邮件服务暂时限流或不可用，请稍后重试", retryable=True)
        raise OutlookGraphError(f"Outlook 邮件发送失败（HTTP {response.status_code}）")
    raise OutlookGraphError("Outlook 邮件发送失败")


def set_active_provider(db_path: Path, provider: str) -> dict[str, Any]:
    normalized = provider.strip().lower()
    if normalized not in SUPPORTED_PROVIDERS:
        raise OutlookGraphError("不支持的邮件服务商")
    if normalized == "outlook_graph":
        status = provider_status(db_path)
        if not status["outlook"]["configured"] or not status["outlook"]["connected"]:
            raise OutlookGraphError("Outlook 尚未完成连接，不能启用")
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE email_provider_settings SET active_provider = ?, updated_at = ? WHERE id = 1",
            (normalized, _now()),
        )
    os.environ["EMAIL_PROVIDER"] = normalized
    return provider_status(db_path)


def disconnect_outlook(db_path: Path) -> dict[str, Any]:
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM outlook_graph_credentials WHERE id = 1")
        setting = conn.execute("SELECT active_provider FROM email_provider_settings WHERE id = 1").fetchone()
        if setting and str(setting["active_provider"]) == "outlook_graph":
            fallback = "smtp" if _smtp_configured() else "log"
            conn.execute(
                "UPDATE email_provider_settings SET active_provider = ?, updated_at = ? WHERE id = 1",
                (fallback, _now()),
            )
            os.environ["EMAIL_PROVIDER"] = fallback
    return provider_status(db_path)
