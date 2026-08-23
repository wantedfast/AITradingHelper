from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import urllib.request
import urllib.error
from urllib.parse import urlparse
from contextlib import contextmanager
from math import ceil
from statistics import median
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo

from trade_review_agent.auth_system import (
    AuthError,
)
from trade_review_agent.market.stock_resolver import KNOWN_CODES, resolve_stock_code
from trade_review_agent.review.final_wang_agent.agent import (
    ark_cost,
    deepseek_cost,
    doubao_model_name,
    extract_responses_text,
)


CN_TZ = ZoneInfo("Asia/Shanghai")
FEATURE = "stock_reverse_research"
ROLE_ORDER = ("capital_logic", "product_path", "bom", "bottleneck", "profit_flow", "fund_manager")
RUNNING_STATUSES = ("queued", "running", "retrying")
TERMINAL_STATUSES = ("completed", "failed", "cancelled", "timed_out", "payment_required")
RETRYABLE_STATUSES = ("failed", "cancelled", "timed_out", "payment_required")
MAX_COST_CNY = 2.0
DEFAULT_TIMEOUT_SECONDS = 300
MEMBER_MONTHLY_INCLUDED = 10
MEMBER_DAILY_LIMIT = 2
FORBIDDEN_PATTERNS = (
    r"(?:建议|立即|应该|应当|可以|推荐)[^。；\n]{0,8}(?:买入|卖出|加仓|减仓|建仓|清仓)",
    r"(?:仓位|目标价|止盈价|止损价)\s*[:：]?\s*\d",
    r"(?:保证收益|承诺收益|收益承诺|稳赚|必涨|确定上涨|收益率可达)",
)
SOURCE_TIERS = {"A", "B", "C", "D"}


class StockResearchError(RuntimeError):
    def __init__(self, message: str, *, code: str = "stock_research_error") -> None:
        super().__init__(message)
        self.code = code


class CostLimitError(StockResearchError):
    pass


class Provider(Protocol):
    name: str
    usage: dict[str, Any]

    def evidence(self, subject: dict[str, str]) -> dict[str, Any]: ...
    def supplement(self, subject: dict[str, str], gaps: list[str]) -> dict[str, Any]: ...
    def role(self, role: str, prompt: str) -> dict[str, Any]: ...
    def judge(self, prompt: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class NormalizedSubject:
    type: str
    name: str
    code: str = ""

    def payload(self) -> dict[str, str]:
        result = {"type": self.type, "name": self.name}
        if self.code:
            result["code"] = self.code
        return result


@contextmanager
def _connect(db_path: Path):
    conn = sqlite3.connect(str(db_path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        yield conn
        if conn.in_transaction:
            conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def init_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS stock_research_jobs (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                subject_type TEXT NOT NULL,
                subject_name TEXT NOT NULL,
                stock_code TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                provider TEXT NOT NULL,
                billing_mode TEXT NOT NULL DEFAULT 'credits',
                model_names TEXT NOT NULL DEFAULT '',
                attempts INTEGER NOT NULL DEFAULT 0,
                progress INTEGER NOT NULL DEFAULT 0,
                board_json TEXT NOT NULL DEFAULT '{}',
                role_outputs_json TEXT NOT NULL DEFAULT '{}',
                sources_json TEXT NOT NULL DEFAULT '[]',
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                search_count INTEGER NOT NULL DEFAULT 0,
                cost_cny REAL NOT NULL DEFAULT 0,
                error_code TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '',
                request_ip TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                started_at TEXT,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS stock_research_reports (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                subject_type TEXT NOT NULL,
                subject_name TEXT NOT NULL,
                stock_code TEXT NOT NULL DEFAULT '',
                schema_version INTEGER NOT NULL DEFAULT 1,
                report_json TEXT NOT NULL,
                provider TEXT NOT NULL,
                model_names TEXT NOT NULL DEFAULT '',
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                search_count INTEGER NOT NULL DEFAULT 0,
                cost_cny REAL NOT NULL DEFAULT 0,
                duration_seconds REAL NOT NULL DEFAULT 0,
                source_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES stock_research_jobs(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_stock_research_jobs_user_created
              ON stock_research_jobs(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_stock_research_jobs_status
              ON stock_research_jobs(status, updated_at);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_research_one_active_user
              ON stock_research_jobs(user_id)
              WHERE status IN ('queued', 'running', 'retrying');
            CREATE INDEX IF NOT EXISTS idx_stock_research_reports_user_created
              ON stock_research_reports(user_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS stock_research_benchmark_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_key TEXT NOT NULL,
                provider TEXT NOT NULL,
                citation_rate REAL NOT NULL,
                completeness_rate REAL NOT NULL,
                severe_error INTEGER NOT NULL DEFAULT 0,
                quality_score REAL NOT NULL,
                cost_cny REAL NOT NULL,
                duration_seconds REAL NOT NULL,
                reviewed_by INTEGER,
                reviewed_at TEXT NOT NULL,
                UNIQUE(sample_key, provider),
                FOREIGN KEY (reviewed_by) REFERENCES users(id)
            );
            """
        )
        columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(stock_research_jobs)").fetchall()}
        if "billing_mode" not in columns:
            try:
                conn.execute("ALTER TABLE stock_research_jobs ADD COLUMN billing_mode TEXT NOT NULL DEFAULT 'credits'")
            except sqlite3.OperationalError as exc:
                if "duplicate column" not in str(exc).lower():
                    raise


def normalize_subject(payload: dict[str, Any], *, allow_fetch: bool = True) -> NormalizedSubject:
    kind = str(payload.get("type") or payload.get("subject_type") or "").strip().lower()
    value = str(payload.get("value") or payload.get("subject") or payload.get("name") or "").strip()
    if kind not in {"stock", "industry_chain"}:
        raise AuthError("研究类型必须是 stock 或 industry_chain", 422)
    if not value:
        raise AuthError("请输入一只 A 股或一个产业链名称", 422)
    if any(mark in value for mark in (",", "，", ";", "；", "、", "\n")):
        raise AuthError("每次只能研究一只 A 股或一个产业链", 422)
    if kind == "industry_chain":
        compact = re.sub(r"\s+", "", value)
        if not 2 <= len(compact) <= 30:
            raise AuthError("产业链名称需为 2–30 个字", 422)
        return NormalizedSubject(kind, compact)

    compact = re.sub(r"\s+", "", value)
    code = resolve_stock_code(compact, allow_fetch=allow_fetch, exact_only=True)
    if not code or not re.fullmatch(r"\d{6}", code):
        raise AuthError("未能解析为唯一 A 股，请输入股票简称或六位代码", 422)
    if not code.startswith(("00", "30", "60", "68", "43", "83", "87", "92")):
        raise AuthError("当前仅支持 A 股股票", 422)
    name = compact
    if compact.isdigit():
        reverse_known = {known_code: known_name for known_name, known_code in KNOWN_CODES.items()}
        name = reverse_known.get(code, code)
    return NormalizedSubject(kind, name, code)


def is_user_allowed(user: dict[str, Any]) -> bool:
    if str(user.get("role")) == "admin":
        return True
    mode = os.getenv("STOCK_RESEARCH_ACCESS", "admin").strip().lower()
    if mode == "all":
        return True
    if mode != "pilot":
        return False
    try:
        percent = max(0, min(100, int(os.getenv("STOCK_RESEARCH_ROLLOUT_PERCENT", "10"))))
    except ValueError:
        percent = 10
    bucket = int(hashlib.sha256(str(user.get("id")).encode()).hexdigest()[:8], 16) % 100
    return bucket < percent


def quota_status(db_path: Path, *, user_id: int) -> dict[str, Any]:
    """Return the successful-report quota and the billing mode for the next job."""
    now = datetime.now(CN_TZ)
    month_prefix = now.strftime("%Y-%m")
    day_prefix = now.strftime("%Y-%m-%d")
    with _connect(db_path) as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            raise AuthError("用户不存在", 404)
        monthly_used = int(conn.execute(
            "SELECT COUNT(*) FROM stock_research_reports WHERE user_id=? AND substr(created_at,1,7)=?",
            (user_id, month_prefix),
        ).fetchone()[0])
        daily_used = int(conn.execute(
            "SELECT COUNT(*) FROM stock_research_reports WHERE user_id=? AND substr(created_at,1,10)=?",
            (user_id, day_prefix),
        ).fetchone()[0])
        credit_balance = int(conn.execute(
            "SELECT COALESCE(SUM(delta),0) FROM credit_ledger WHERE user_id=?", (user_id,)
        ).fetchone()[0])

    role = str(user["role"] or "")
    membership_active = False
    expires_at = str(user["membership_expires_at"] or "") if "membership_expires_at" in user.keys() else ""
    if str(user["membership_status"] or "") == "active" and expires_at:
        try:
            expires = datetime.fromisoformat(expires_at)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=CN_TZ)
            membership_active = expires > now
        except ValueError:
            membership_active = False

    if role == "admin":
        billing_mode = "admin_free"
    elif membership_active and monthly_used < MEMBER_MONTHLY_INCLUDED:
        billing_mode = "membership_included"
    else:
        billing_mode = "credits"
    return {
        "membership_active": membership_active,
        "monthly_included": MEMBER_MONTHLY_INCLUDED if membership_active else 0,
        "monthly_used": monthly_used,
        "monthly_remaining": max(0, MEMBER_MONTHLY_INCLUDED - monthly_used) if membership_active else 0,
        "daily_limit": MEMBER_DAILY_LIMIT if membership_active else None,
        "daily_used": daily_used,
        "daily_remaining": max(0, MEMBER_DAILY_LIMIT - daily_used) if membership_active else None,
        "credit_balance": credit_balance,
        "next_billing_mode": billing_mode,
        "next_credit_cost": 3 if billing_mode == "credits" else 0,
    }


def _validate_job_quota(db_path: Path, *, user_id: int) -> dict[str, Any]:
    quota = quota_status(db_path, user_id=user_id)
    if quota["membership_active"] and int(quota["daily_used"]) >= MEMBER_DAILY_LIMIT:
        raise AuthError("今日产业链逆向研究额度已用完，明天可继续生成", 429)
    if quota["next_billing_mode"] == "credits" and int(quota["credit_balance"]) < 3:
        raise AuthError("可用次数不足，本功能需要 3 次", 402)
    return quota


def create_job(
    db_path: Path,
    *,
    user: dict[str, Any],
    payload: dict[str, Any],
    request_ip: str = "",
    start: bool = True,
    provider_name: str = "",
) -> dict[str, Any]:
    if not is_user_allowed(user):
        raise AuthError("产业链逆向研究正在管理员评测阶段，暂未对当前账号开放", 403)
    subject = normalize_subject(payload)
    user_id = int(user["id"])
    quota = _validate_job_quota(db_path, user_id=user_id)
    billing_mode = str(quota["next_billing_mode"])
    job_id = f"sr-{uuid4().hex}"
    provider = (provider_name or os.getenv("STOCK_RESEARCH_PROVIDER", "luna")).strip().lower()
    if provider == "auto":
        provider = select_production_provider(db_path)["provider"]
    if provider not in {"luna", "doubao_deepseek"}:
        raise AuthError("研究引擎配置无效", 503)
    now = _now()
    model_names = _configured_model_names(provider)
    try:
        with _connect(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            active = conn.execute(
                "SELECT id FROM stock_research_jobs WHERE user_id = ? AND status IN ('queued','running','retrying')",
                (user_id,),
            ).fetchone()
            if active:
                raise AuthError("当前已有一份研究正在生成，请等待完成后再提交", 409)
            conn.execute(
                """INSERT INTO stock_research_jobs
                   (id,user_id,subject_type,subject_name,stock_code,status,stage,provider,billing_mode,model_names,request_ip,created_at,updated_at)
                   VALUES (?,?,?,?,?,'queued','queued',?,?,?,?,?,?)""",
                (job_id, user_id, subject.type, subject.name, subject.code, provider, billing_mode, model_names, request_ip, now, now),
            )
    except sqlite3.IntegrityError as exc:
        raise AuthError("当前已有一份研究正在生成，请等待完成后再提交", 409) from exc
    if start:
        start_job(db_path, job_id)
    return get_job(db_path, job_id, user_id=user_id)


def start_job(db_path: Path, job_id: str, *, provider_factory: Callable[[str], Provider] | None = None) -> None:
    thread = threading.Thread(
        target=run_job,
        args=(db_path, job_id),
        kwargs={"provider_factory": provider_factory},
        name=f"stock-research-{job_id[-8:]}",
        daemon=True,
    )
    thread.start()


def recover_jobs(db_path: Path) -> int:
    init_schema(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id FROM stock_research_jobs WHERE status IN ('queued','running','retrying') ORDER BY created_at"
        ).fetchall()
        conn.execute(
            "UPDATE stock_research_jobs SET status='queued', stage='recovering', updated_at=? WHERE status IN ('running','retrying')",
            (_now(),),
        )
    for row in rows:
        start_job(db_path, str(row["id"]))
    return len(rows)


def run_job(
    db_path: Path,
    job_id: str,
    *,
    provider_factory: Callable[[str], Provider] | None = None,
    allow_provider_retry: bool = True,
) -> None:
    started = time.monotonic()
    try:
        with _connect(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM stock_research_jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row["status"] not in {"queued", "retrying"}:
                return
            conn.execute(
                "UPDATE stock_research_jobs SET status='running',stage='collecting_evidence',attempts=attempts+1,started_at=COALESCE(started_at,?),updated_at=? WHERE id=?",
                (_now(), _now(), job_id),
            )
            subject = NormalizedSubject(str(row["subject_type"]), str(row["subject_name"]), str(row["stock_code"]))
            provider_name = str(row["provider"])
            billing_mode = str(row["billing_mode"] or "credits")
            user_id = int(row["user_id"])
            request_ip = str(row["request_ip"])

        provider = (provider_factory or build_provider)(provider_name)
        evidence_pack = provider.evidence(subject.payload())
        _enforce_cost(provider.usage)
        sources = normalize_sources(evidence_pack.get("evidence"))
        if not sources:
            raise StockResearchError("未找到可验证的一手或权威证据", code="evidence_missing")
        if not any(item["source_tier"] in {"A", "B"} for item in sources):
            raise StockResearchError("证据仅有概念标签或低等级来源", code="evidence_quality_low")
        board: dict[str, Any] = {
            "subject": subject.payload(),
            "facts": evidence_pack.get("facts") or [],
            "hypotheses": [],
            "conflicts": [],
            "evidence_gaps": evidence_pack.get("evidence_gaps") or [],
        }
        role_outputs: dict[str, Any] = {}
        _persist_progress(db_path, job_id, "capital_logic", 12, board, role_outputs, sources, provider.usage)

        for index, role in enumerate(ROLE_ORDER[:-1]):
            _enforce_timeout(started)
            prompt = build_role_prompt(role, subject.payload(), board, role_outputs, sources)
            result = provider.role(role, prompt)
            validate_role_output(role, result, sources)
            role_outputs[role] = result
            merge_role_into_board(board, role, result)
            progress = 18 + (index + 1) * 12
            _persist_progress(db_path, job_id, role, progress, board, role_outputs, sources, provider.usage)
            _enforce_cost(provider.usage)

        # At most one evidence-gap search round, and never after the hard cost cap.
        gaps = [str(item) for item in board.get("evidence_gaps", []) if str(item).strip()][:5]
        if (
            gaps
            and len(sources) < 8
            and int(provider.usage.get("search_count", 0)) < 8
            and hasattr(provider, "supplement")
            and float(provider.usage.get("cost_cny", 0)) < MAX_COST_CNY * 0.8
        ):
            supplement = provider.supplement(subject.payload(), gaps)
            additions = normalize_sources(supplement.get("evidence"))
            known_ids = {item["id"] for item in sources}
            sources.extend(item for item in additions if item["id"] not in known_ids)
            board["supplemental_facts"] = supplement.get("facts") or []
            board["supplement_search_completed"] = True
            _persist_progress(db_path, job_id, "evidence_gap_search", 82, board, role_outputs, sources, provider.usage)
            _enforce_cost(provider.usage)

        _enforce_timeout(started)
        _persist_progress(db_path, job_id, "fund_manager", 86, board, role_outputs, sources, provider.usage)
        judge_prompt = build_judge_prompt(subject.payload(), board, role_outputs, sources)
        report = provider.judge(judge_prompt)
        report = finalize_report(report, subject, board, role_outputs, sources, provider.name, provider.usage)
        validate_report(report)
        _enforce_cost(provider.usage)

        report_id = f"report-{job_id[3:]}"
        duration = round(time.monotonic() - started, 3)
        usage = provider.usage
        now = _now()
        _store_report_charge_and_complete(
            db_path, job_id=job_id, report_id=report_id, user_id=user_id, subject=subject,
            report=report, provider=provider.name, usage=usage, duration=duration, sources=sources,
            board=board, role_outputs=role_outputs, request_ip=request_ip, now=now, billing_mode=billing_mode,
        )
    except AuthError as exc:
        _mark_failed(db_path, job_id, "payment_required" if exc.status == 402 else "failed", "credit_error", exc.message)
    except Exception as exc:
        code = exc.code if isinstance(exc, StockResearchError) else "unexpected_error"
        if allow_provider_retry and code in {"unexpected_error", "provider_json_error", "provider_error"} and _queue_single_provider_retry(db_path, job_id, str(exc)):
            start_job(db_path, job_id, provider_factory=provider_factory)
            return
        _mark_failed(db_path, job_id, "timed_out" if code == "timeout" else "failed", code, str(exc))


def _queue_single_provider_retry(db_path: Path, job_id: str, message: str) -> bool:
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT attempts FROM stock_research_jobs WHERE id=?", (job_id,)).fetchone()
        if not row or int(row["attempts"] or 0) >= 2:
            return False
        conn.execute(
            """UPDATE stock_research_jobs SET status='retrying',stage='provider_retry',progress=0,
               error_code='provider_retry',error_message=?,updated_at=? WHERE id=?""",
            (message[:1200], _now(), job_id),
        )
        return True


def _persist_progress(
    db_path: Path, job_id: str, stage: str, progress: int, board: dict[str, Any], roles: dict[str, Any],
    sources: list[dict[str, Any]], usage: dict[str, Any]
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """UPDATE stock_research_jobs SET stage=?,progress=?,board_json=?,role_outputs_json=?,sources_json=?,
               input_tokens=?,output_tokens=?,search_count=?,cost_cny=?,updated_at=? WHERE id=?""",
            (stage, progress, json.dumps(board, ensure_ascii=False), json.dumps(roles, ensure_ascii=False),
             json.dumps(sources, ensure_ascii=False), int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)),
             int(usage.get("search_count", 0)), float(usage.get("cost_cny", 0)), _now(), job_id),
        )


def _store_report_charge_and_complete(
    db_path: Path, *, job_id: str, report_id: str, user_id: int, subject: NormalizedSubject,
    report: dict[str, Any], provider: str, usage: dict[str, Any], duration: float,
    sources: list[dict[str, Any]], board: dict[str, Any], role_outputs: dict[str, Any], request_ip: str, now: str,
    billing_mode: str,
) -> None:
    """Atomically persist the valid report, charge once, and complete the job."""
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            raise AuthError("用户不存在", 404)
        already_charged = conn.execute(
            "SELECT 1 FROM usage_events WHERE user_id=? AND feature=? AND related_id=? AND status IN ('charged','admin_free','membership_free')",
            (user_id, FEATURE, job_id),
        ).fetchone()
        if not already_charged:
            if user["role"] == "admin" or billing_mode == "admin_free":
                billing_status, credits = "admin_free", 0
            elif billing_mode == "membership_included":
                billing_status, credits = "membership_free", 0
            else:
                balance = int(conn.execute(
                    "SELECT COALESCE(SUM(delta),0) AS balance FROM credit_ledger WHERE user_id=?", (user_id,)
                ).fetchone()["balance"])
                if balance < 3:
                    raise AuthError("可用次数不足，本功能需要 3 次", 402)
                conn.execute(
                    "INSERT INTO credit_ledger(user_id,delta,reason,related_id,created_at) VALUES(?, -3, ?, ?, ?)",
                    (user_id, f"use_{FEATURE}", job_id, now),
                )
                billing_status, credits = "charged", 3
            conn.execute(
                "INSERT INTO usage_events(user_id,feature,credits_spent,status,related_id,ip,created_at) VALUES(?,?,?,?,?,?,?)",
                (user_id, FEATURE, credits, billing_status, job_id, request_ip, now),
            )
        conn.execute(
            """INSERT OR IGNORE INTO stock_research_reports
               (id,job_id,user_id,subject_type,subject_name,stock_code,schema_version,report_json,provider,model_names,
                input_tokens,output_tokens,search_count,cost_cny,duration_seconds,source_count,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                report_id, job_id, user_id, subject.type, subject.name, subject.code, 1,
                json.dumps(report, ensure_ascii=False), provider, _configured_model_names(provider), int(usage.get("input_tokens", 0)),
                int(usage.get("output_tokens", 0)), int(usage.get("search_count", 0)),
                float(usage.get("cost_cny", 0)), duration, len(sources), now,
            ),
        )
        conn.execute(
            """UPDATE stock_research_jobs SET status='completed',stage='completed',progress=100,
               board_json=?,role_outputs_json=?,sources_json=?,input_tokens=?,output_tokens=?,search_count=?,cost_cny=?,
               error_code='',error_message='',completed_at=?,updated_at=? WHERE id=?""",
            (
                json.dumps(board, ensure_ascii=False), json.dumps(role_outputs, ensure_ascii=False),
                json.dumps(sources, ensure_ascii=False), int(usage.get("input_tokens", 0)),
                int(usage.get("output_tokens", 0)), int(usage.get("search_count", 0)),
                float(usage.get("cost_cny", 0)), now, now, job_id,
            ),
        )


def _mark_failed(db_path: Path, job_id: str, status: str, code: str, message: str) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE stock_research_jobs SET status=?,stage='failed',error_code=?,error_message=?,updated_at=?,completed_at=? WHERE id=?",
            (status, code[:80], message[:1200], _now(), _now(), job_id),
        )


def get_job(db_path: Path, job_id: str, *, user_id: int | None = None, admin: bool = False) -> dict[str, Any]:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM stock_research_jobs WHERE id=?", (job_id,)).fetchone()
        report_row = conn.execute("SELECT id FROM stock_research_reports WHERE job_id=?", (job_id,)).fetchone()
    if not row or (not admin and user_id is not None and int(row["user_id"]) != int(user_id)):
        raise AuthError("研究任务不存在", 404)
    payload = _job_payload(row)
    payload["report_id"] = str(report_row["id"]) if report_row else ""
    payload["estimated_wait_seconds"] = _estimated_wait(payload)
    return payload


def list_reports(db_path: Path, *, user_id: int, limit: int = 30) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT id,job_id,subject_type,subject_name,stock_code,provider,cost_cny,duration_seconds,source_count,created_at
               FROM stock_research_reports WHERE user_id=? ORDER BY created_at DESC LIMIT ?""",
            (user_id, max(1, min(limit, 100))),
        ).fetchall()
    return [dict(row) for row in rows]


def get_report(db_path: Path, report_id: str, *, user_id: int | None = None, admin: bool = False) -> dict[str, Any]:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM stock_research_reports WHERE id=?", (report_id,)).fetchone()
    if not row or (not admin and user_id is not None and int(row["user_id"]) != int(user_id)):
        raise AuthError("研究报告不存在", 404)
    payload = dict(row)
    payload["report"] = json.loads(payload.pop("report_json"))
    return payload


def admin_list_jobs(db_path: Path, *, status: str = "", limit: int = 100) -> list[dict[str, Any]]:
    query = """SELECT j.*,u.username,u.email FROM stock_research_jobs j JOIN users u ON u.id=j.user_id"""
    params: list[Any] = []
    if status:
        query += " WHERE j.status=?"
        params.append(status)
    query += " ORDER BY j.created_at DESC LIMIT ?"
    params.append(max(1, min(limit, 300)))
    with _connect(db_path) as conn:
        return [_job_payload(row) for row in conn.execute(query, params).fetchall()]


def record_benchmark_result(db_path: Path, *, admin_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    sample_key = str(payload.get("sample_key") or "").strip()[:120]
    provider = str(payload.get("provider") or "").strip().lower()
    if not sample_key or provider not in {"luna", "doubao_deepseek"}:
        raise AuthError("benchmark sample_key 或 provider 无效", 422)
    try:
        citation = float(payload["citation_rate"])
        completeness = float(payload["completeness_rate"])
        quality = float(payload["quality_score"])
        cost = float(payload["cost_cny"])
        duration = float(payload["duration_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthError("benchmark 评分字段不完整", 422) from exc
    if any(not 0 <= value <= 100 for value in (citation, completeness, quality)) or cost < 0 or duration < 0:
        raise AuthError("benchmark 评分超出允许范围", 422)
    with _connect(db_path) as conn:
        conn.execute(
            """INSERT INTO stock_research_benchmark_results
               (sample_key,provider,citation_rate,completeness_rate,severe_error,quality_score,cost_cny,duration_seconds,reviewed_by,reviewed_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(sample_key,provider) DO UPDATE SET citation_rate=excluded.citation_rate,
               completeness_rate=excluded.completeness_rate,severe_error=excluded.severe_error,
               quality_score=excluded.quality_score,cost_cny=excluded.cost_cny,duration_seconds=excluded.duration_seconds,
               reviewed_by=excluded.reviewed_by,reviewed_at=excluded.reviewed_at""",
            (sample_key, provider, citation, completeness, int(bool(payload.get("severe_error"))), quality, cost, duration, admin_id, _now()),
        )
    return benchmark_summary(db_path)


def benchmark_summary(db_path: Path) -> dict[str, Any]:
    with _connect(db_path) as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM stock_research_benchmark_results ORDER BY sample_key,provider").fetchall()]
    by_provider: dict[str, list[dict[str, Any]]] = {"luna": [], "doubao_deepseek": []}
    for row in rows:
        by_provider[str(row["provider"])].append(row)
    metrics: dict[str, Any] = {}
    for provider, items in by_provider.items():
        costs = sorted(float(item["cost_cny"]) for item in items)
        durations = sorted(float(item["duration_seconds"]) for item in items)
        metrics[provider] = {
            "samples": len(items),
            "citation_rate": round(sum(float(item["citation_rate"]) for item in items) / len(items), 2) if items else 0,
            "completeness_rate": round(sum(float(item["completeness_rate"]) for item in items) / len(items), 2) if items else 0,
            "severe_errors": sum(int(item["severe_error"]) for item in items),
            "quality_score": round(sum(float(item["quality_score"]) for item in items) / len(items), 2) if items else 0,
            "median_cost_cny": round(median(costs), 3) if costs else 0,
            "p95_cost_cny": round(_p95(costs), 3) if costs else 0,
            "p95_duration_seconds": round(_p95(durations), 2) if durations else 0,
        }
    decision = select_production_provider_from_metrics(metrics)
    return {"metrics": metrics, "decision": decision, "results": rows}


def select_production_provider(db_path: Path) -> dict[str, Any]:
    return benchmark_summary(db_path)["decision"]


def select_production_provider_from_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    luna = metrics.get("luna") or {}
    hybrid = metrics.get("doubao_deepseek") or {}
    enough = int(luna.get("samples", 0)) >= 20 and int(hybrid.get("samples", 0)) >= 20
    quality_gap = float(hybrid.get("quality_score", 0)) - float(luna.get("quality_score", 0))
    passed = enough and all((
        float(luna.get("citation_rate", 0)) >= 95,
        float(luna.get("completeness_rate", 0)) >= 98,
        int(luna.get("severe_errors", 0)) == 0,
        quality_gap <= 5,
        float(luna.get("median_cost_cny", 999)) <= 1.2,
        float(luna.get("p95_cost_cny", 999)) <= 2,
        float(luna.get("p95_duration_seconds", 999)) <= 180,
    ))
    if passed:
        return {"provider": "luna", "gate_passed": True, "reason": "Luna 已通过20份盲测门槛"}
    return {
        "provider": os.getenv("STOCK_RESEARCH_BENCHMARK_FALLBACK", "doubao_deepseek"),
        "gate_passed": False,
        "reason": "盲测样本不足或 Luna 未满足质量、成本、时延门槛",
    }


def _p95(values: list[float]) -> float:
    return values[max(0, ceil(len(values) * 0.95) - 1)] if values else 0.0


def retry_job(db_path: Path, job_id: str) -> dict[str, Any]:
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM stock_research_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise AuthError("研究任务不存在", 404)
        if row["status"] not in RETRYABLE_STATUSES:
            raise AuthError("只有失败、超时或余额不足任务可以重试", 409)
        if conn.execute(
            "SELECT 1 FROM stock_research_jobs WHERE user_id=? AND status IN ('queued','running','retrying')", (row["user_id"],)
        ).fetchone():
            raise AuthError("该用户已有运行中的研究任务", 409)
        conn.execute(
            """UPDATE stock_research_jobs SET status='retrying',stage='queued',progress=0,error_code='',error_message='',
               board_json='{}',role_outputs_json='{}',sources_json='[]',updated_at=?,completed_at=NULL WHERE id=?""",
            (_now(), job_id),
        )
    start_job(db_path, job_id)
    return get_job(db_path, job_id, admin=True)


def _job_payload(row: sqlite3.Row) -> dict[str, Any]:
    keys = (
        "id", "user_id", "subject_type", "subject_name", "stock_code", "status", "stage", "provider", "billing_mode", "model_names", "attempts",
        "progress", "input_tokens", "output_tokens", "search_count", "cost_cny", "error_code", "error_message",
        "created_at", "started_at", "updated_at", "completed_at",
    )
    payload = {key: row[key] for key in keys if key in row.keys()}
    for key in ("username", "email"):
        if key in row.keys():
            payload[key] = row[key]
    if "sources_json" in row.keys():
        try:
            payload["source_count"] = len(json.loads(row["sources_json"] or "[]"))
        except (TypeError, ValueError):
            payload["source_count"] = 0
    return payload


def _configured_model_names(provider: str) -> str:
    if provider == "luna":
        return os.getenv("STOCK_RESEARCH_LUNA_MODEL", "gpt-5.6-luna").strip()
    return " + ".join((
        doubao_model_name(),
        os.getenv("STOCK_RESEARCH_DEEPSEEK_FLASH_MODEL", "deepseek-chat").strip(),
        os.getenv("STOCK_RESEARCH_DEEPSEEK_PRO_MODEL", "deepseek-reasoner").strip(),
    ))


def _estimated_wait(job: dict[str, Any]) -> int:
    if job.get("status") not in RUNNING_STATUSES:
        return 0
    return max(15, int(DEFAULT_TIMEOUT_SECONDS * (100 - int(job.get("progress") or 0)) / 100))


def normalize_sources(value: Any) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(rows, 1):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        if not url.startswith(("http://", "https://")) or not title:
            continue
        evidence_id = str(item.get("id") or f"E{index:03d}").strip().upper()
        if evidence_id in seen:
            continue
        tier = _normalize_source_tier(item)
        result.append({
            "id": evidence_id,
            "title": title[:240],
            "url": url[:1000],
            "publisher": str(item.get("publisher") or "")[:120],
            "published_at": str(item.get("published_at") or "")[:40],
            "source_tier": tier,
            "excerpt": str(item.get("excerpt") or item.get("summary") or "")[:600],
        })
        seen.add(evidence_id)
    return result


def _normalize_source_tier(item: dict[str, Any]) -> str:
    raw = str(item.get("source_tier") or item.get("tier") or item.get("source_type") or "").strip().upper()
    combined = " ".join(str(item.get(key) or "") for key in ("publisher", "title", "url", "source_type")).lower()
    try:
        domain = urlparse(str(item.get("url") or "")).hostname or ""
    except ValueError:
        domain = ""
    official_domain = domain.endswith(("cninfo.com.cn", "sse.com.cn", "szse.cn", "bse.cn", "gov.cn"))
    if official_domain:
        return "A"
    if raw[:1] == "A":
        # A document title alone does not make a third-party mirror an official source.
        return "C" if domain else "D"
    if raw[:1] in SOURCE_TIERS:
        return raw[:1]
    if any(marker in combined for marker in ("行业协会", "研究院", "研究所", "政府", "协会")):
        return "B"
    if any(marker in combined for marker in ("财经", "证券报", "财联社", "证券时报")):
        return "C"
    return "D"


def build_role_prompt(role: str, subject: dict[str, str], board: dict[str, Any], roles: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    instructions = {
        "capital_logic": "解释近期资金为什么交易该对象，区分事实、催化与市场叙事。",
        "product_path": "映射到真实产品、部件、下游需求，不把概念标签当主营证据。",
        "bom": "拆解材料、设备、工艺、封装、测试、配套设施以及对应A股。必须挑战产品路径中的跳跃。",
        "bottleneck": "判断紧缺环节、扩产难度、定价权和瓶颈迁移。必须挑战BOM的伪瓶颈。",
        "profit_flow": "区分利润中心、量增受益、主题跟随、伪核心。必须挑战瓶颈是否真正转化为利润。",
    }
    return _json_prompt(
        f"你是六角色产业链逆向研究中的 {role}。{instructions[role]}", subject, board, roles, sources,
        "仅输出JSON：{summary:string,claims:[{claim,evidence_ids:[E001],confidence:high|medium|low}],challenges:[string],evidence_gaps:[string]}。每个重要claim必须有证据ID。"
    )


def build_judge_prompt(subject: dict[str, str], board: dict[str, Any], roles: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    stock_extra = "股票输入必须给input_stock_score（三高各0-100、core_score=0.4*barrier+0.3*profit+0.3*growth）和core_asset_ranking。" if subject["type"] == "stock" else "产业链输入不要input_stock_score，必须给core_asset_ranking、bottleneck_ranking、profit_capture_ranking。"
    schema = """仅输出JSON：{headline,capital_logic:{summary,evidence_ids},product_path:{summary,evidence_ids},bom:{summary,items,evidence_ids},bottleneck:{summary,evidence_ids},profit_flow:{summary,evidence_ids},positioning:{label,reason,evidence_ids},input_stock_score?:{barrier,profit,growth,core_score,evidence_ids},core_asset_ranking:[{name,code?,position,reason,evidence_ids}],bottleneck_ranking?:[],profit_capture_ranking?:[],judge:{conclusion,role_conflicts:[string],disconfirming_signals:[string],evidence_ids}}。"""
    return _json_prompt(
        "你是第六角色基金经理与核心资产裁决者。解决前五角色冲突，证据不足必须降级或标记，不得补造事实。" + stock_extra,
        subject, board, roles, sources, schema
    )


def _json_prompt(prefix: str, subject: dict[str, str], board: dict[str, Any], roles: dict[str, Any], sources: list[dict[str, Any]], suffix: str) -> str:
    return (
        prefix + "\n禁止个性化买卖指令、仓位、目标价、收益承诺。概念标签只能作为搜索线索。\n" + suffix
        + "\n研究对象=" + json.dumps(subject, ensure_ascii=False)
        + "\n共享研究板=" + json.dumps(board, ensure_ascii=False)
        + "\n已有角色结果=" + json.dumps(roles, ensure_ascii=False)
        + "\n证据库=" + json.dumps(sources, ensure_ascii=False)
    )


def validate_role_output(role: str, result: Any, sources: list[dict[str, Any]]) -> None:
    if not isinstance(result, dict) or not isinstance(result.get("claims"), list):
        raise StockResearchError(f"{role} 角色输出不完整", code="role_contract_error")
    known = {item["id"] for item in sources}
    for claim in result["claims"]:
        ids = claim.get("evidence_ids") if isinstance(claim, dict) else None
        if not ids or any(str(item) not in known for item in ids):
            raise StockResearchError(f"{role} 存在无效或缺失证据引用", code="citation_error")
    if role in {"bom", "bottleneck", "profit_flow"} and not result.get("challenges"):
        raise StockResearchError(f"{role} 必须挑战上一角色结论", code="role_challenge_missing")


def merge_role_into_board(board: dict[str, Any], role: str, result: dict[str, Any]) -> None:
    board.setdefault("role_findings", {})[role] = result.get("summary") or ""
    board.setdefault("conflicts", []).extend(result.get("challenges") or [])
    board.setdefault("evidence_gaps", []).extend(result.get("evidence_gaps") or [])


def finalize_report(report: Any, subject: NormalizedSubject, board: dict[str, Any], roles: dict[str, Any], sources: list[dict[str, Any]], provider: str, usage: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise StockResearchError("裁决模型未返回结构化报告", code="report_contract_error")
    report["schema_version"] = 1
    report["subject"] = subject.payload()
    report["evidence"] = sources
    report["research_board"] = board
    report["role_outputs"] = roles
    report["meta"] = {
        "provider": provider,
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
        "search_count": int(usage.get("search_count", 0)),
        "cost_cny": round(float(usage.get("cost_cny", 0)), 4),
    }
    return report


def validate_report(report: dict[str, Any]) -> None:
    serialized = json.dumps(report, ensure_ascii=False)
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, serialized, flags=re.I):
            raise StockResearchError("报告包含禁止的投资指令或收益承诺", code="unsafe_advice")
    subject = report.get("subject") or {}
    required = ("capital_logic", "product_path", "bom", "bottleneck", "profit_flow", "positioning", "core_asset_ranking", "judge")
    for key in required:
        if key not in report or report[key] in (None, "", []):
            raise StockResearchError(f"最终报告缺少 {key}", code="report_contract_error")
    known = {item.get("id") for item in report.get("evidence", []) if isinstance(item, dict)}
    for key in ("capital_logic", "product_path", "bom", "bottleneck", "profit_flow", "positioning", "judge"):
        section = report.get(key)
        ids = section.get("evidence_ids") if isinstance(section, dict) else None
        if not ids or any(item not in known for item in ids):
            raise StockResearchError(f"{key} 缺少可验证证据", code="citation_error")
    if subject.get("type") == "stock":
        score = report.get("input_stock_score")
        if not isinstance(score, dict):
            raise StockResearchError("股票报告缺少三高评分", code="score_error")
        barrier, profit, growth = (float(score.get(key, -1)) for key in ("barrier", "profit", "growth"))
        if any(value < 0 or value > 100 for value in (barrier, profit, growth)):
            raise StockResearchError("三高评分必须在0-100", code="score_error")
        expected = round(barrier * 0.4 + profit * 0.3 + growth * 0.3, 1)
        if abs(float(score.get("core_score", -1)) - expected) > 0.11:
            raise StockResearchError("三高综合分公式不正确", code="score_error")
    else:
        if "input_stock_score" in report:
            raise StockResearchError("产业链报告不得生成输入股票评分", code="score_error")
        for key in ("bottleneck_ranking", "profit_capture_ranking"):
            if not report.get(key):
                raise StockResearchError(f"产业链报告缺少 {key}", code="report_contract_error")
    for key in ("core_asset_ranking", "bottleneck_ranking", "profit_capture_ranking"):
        for item in report.get(key) or []:
            ids = item.get("evidence_ids") if isinstance(item, dict) else None
            if not ids or any(evidence_id not in known for evidence_id in ids):
                raise StockResearchError(f"{key} 存在无效或缺失证据引用", code="citation_error")


def _enforce_timeout(started: float) -> None:
    try:
        timeout = int(os.getenv("STOCK_RESEARCH_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    except ValueError:
        timeout = DEFAULT_TIMEOUT_SECONDS
    if time.monotonic() - started > max(30, timeout):
        raise StockResearchError("研究任务超过5分钟", code="timeout")


def _enforce_cost(usage: dict[str, Any]) -> None:
    try:
        limit = float(os.getenv("STOCK_RESEARCH_MAX_COST_CNY", str(MAX_COST_CNY)))
    except ValueError:
        limit = MAX_COST_CNY
    if float(usage.get("cost_cny", 0)) > max(0.1, limit):
        raise CostLimitError("单份研究成本已达到2元上限，停止追加搜索", code="cost_limit")


def build_provider(name: str) -> Provider:
    if name == "luna":
        return LunaProvider()
    if name == "doubao_deepseek":
        return DoubaoDeepSeekProvider()
    raise StockResearchError("未知研究引擎", code="provider_error")


class BaseProvider:
    name = "base"

    def __init__(self) -> None:
        self.usage: dict[str, Any] = {"input_tokens": 0, "output_tokens": 0, "search_count": 0, "cost_cny": 0.0}
        try:
            timeout = int(os.getenv("STOCK_RESEARCH_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
        except ValueError:
            timeout = DEFAULT_TIMEOUT_SECONDS
        self.deadline = time.monotonic() + max(30, timeout)

    def _add_usage(self, input_tokens: int, output_tokens: int, cost_cny: float, searches: int = 0) -> None:
        self.usage["input_tokens"] += int(input_tokens)
        self.usage["output_tokens"] += int(output_tokens)
        self.usage["search_count"] += int(searches)
        self.usage["cost_cny"] = round(float(self.usage["cost_cny"]) + float(cost_cny), 6)

    def _request_timeout(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise StockResearchError("研究任务超过5分钟", code="timeout")
        return max(1.0, min(180.0, remaining))


class LunaProvider(BaseProvider):
    name = "luna"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("STOCK_RESEARCH_LUNA_MODEL", "gpt-5.6-luna").strip()
        if not self.api_key:
            raise StockResearchError("服务器未配置 OPENAI_API_KEY", code="provider_not_configured")

    def evidence(self, subject: dict[str, str]) -> dict[str, Any]:
        prompt = (
            "为A股产业链逆向研究收集8-15条可验证证据。优先公司公告、财报、交易所、政府和行业机构；"
            "概念页只作线索。source_tier必须严格为A/B/C/D：A=公告财报交易所政府，B=行业协会或权威研究，C=可靠财经媒体，D=概念标签。"
            "输出JSON {facts:[],evidence_gaps:[],evidence:[{id,title,url,publisher,published_at,source_tier,excerpt}]}。对象="
            + json.dumps(subject, ensure_ascii=False)
        )
        return self._call(prompt, web=True)

    def role(self, role: str, prompt: str) -> dict[str, Any]:
        return self._call(prompt, web=False)

    def supplement(self, subject: dict[str, str], gaps: list[str]) -> dict[str, Any]:
        return self._call(
            "只补齐以下证据缺口，不重复已有搜索。输出JSON facts/evidence。对象="
            + json.dumps(subject, ensure_ascii=False) + "\n缺口=" + json.dumps(gaps, ensure_ascii=False), web=True
        )

    def judge(self, prompt: str) -> dict[str, Any]:
        return self._call(prompt, web=False)

    def _call(self, prompt: str, *, web: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "stock_research_stage",
                    "strict": False,
                    "schema": {"type": "object", "additionalProperties": True},
                }
            },
        }
        if web:
            body["tools"] = [{"type": "web_search"}]
        request = urllib.request.Request(
            os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/responses",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._request_timeout()) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            raise StockResearchError(f"Luna HTTP {exc.code}: {detail}", code="provider_error") from exc
        self._write_debug_response(data)
        usage = data.get("usage") or {}
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        searches = sum(1 for item in data.get("output", []) if isinstance(item, dict) and item.get("type") == "web_search_call")
        # Luna $0.20/M input, $1.20/M output; web search $0.01/call. USD/CNY configurable.
        usd = input_tokens * 0.20 / 1_000_000 + output_tokens * 1.20 / 1_000_000 + searches * 0.01
        self._add_usage(input_tokens, output_tokens, usd * float(os.getenv("STOCK_RESEARCH_USD_CNY", "7.2")), searches)
        _enforce_cost(self.usage)
        return _parse_json(extract_responses_text(data))

    def _write_debug_response(self, data: dict[str, Any]) -> None:
        debug_dir = os.getenv("STOCK_RESEARCH_DEBUG_DIR", "").strip()
        if not debug_dir:
            return
        path = Path(debug_dir)
        path.mkdir(parents=True, exist_ok=True)
        index = len(list(path.glob("luna_response_*.json"))) + 1
        (path / f"luna_response_{index:02d}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


class DoubaoDeepSeekProvider(BaseProvider):
    name = "doubao_deepseek"

    def __init__(self) -> None:
        super().__init__()
        self.ark_key = os.getenv("ARK_API_KEY", "").strip()
        self.deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.flash_model = os.getenv("STOCK_RESEARCH_DEEPSEEK_FLASH_MODEL", "deepseek-chat").strip()
        self.pro_model = os.getenv("STOCK_RESEARCH_DEEPSEEK_PRO_MODEL", "deepseek-reasoner").strip()
        if not self.ark_key or not self.deepseek_key:
            raise StockResearchError("服务器未配置 ARK_API_KEY 或 DEEPSEEK_API_KEY", code="provider_not_configured")

    def evidence(self, subject: dict[str, str]) -> dict[str, Any]:
        response = self._doubao_search(
            "收集8-15条A股产业链证据，优先公告财报交易所政府行业机构，输出严格JSON，字段facts/evidence_gaps/evidence。对象="
            + json.dumps(subject, ensure_ascii=False),
        )
        usage = response.get("usage") or {}
        cost = ark_cost(usage)
        self._add_usage(cost["input_tokens"], cost["output_tokens"], cost["cny"], 1)
        return _parse_json(extract_responses_text(response))

    def role(self, role: str, prompt: str) -> dict[str, Any]:
        return self._deepseek(prompt, self.flash_model)

    def supplement(self, subject: dict[str, str], gaps: list[str]) -> dict[str, Any]:
        response = self._doubao_search(
            "只补齐以下产业链研究证据缺口，输出严格JSON facts/evidence。对象="
            + json.dumps(subject, ensure_ascii=False) + "\n缺口=" + json.dumps(gaps, ensure_ascii=False),
        )
        usage = response.get("usage") or {}
        cost = ark_cost(usage)
        self._add_usage(cost["input_tokens"], cost["output_tokens"], cost["cny"], 1)
        return _parse_json(extract_responses_text(response))

    def _doubao_search(self, prompt: str) -> dict[str, Any]:
        body = {
            "model": doubao_model_name(), "input": prompt, "tools": [{"type": "web_search"}],
            "thinking": {"type": "enabled"}, "reasoning": {"effort": "medium"},
        }
        request = urllib.request.Request(
            os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/") + "/responses",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.ark_key}", "Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._request_timeout()) as response:
            return json.loads(response.read().decode("utf-8"))

    def judge(self, prompt: str) -> dict[str, Any]:
        return self._deepseek(prompt, self.pro_model)

    def _deepseek(self, prompt: str, model: str) -> dict[str, Any]:
        body = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "response_format": {"type": "json_object"}}
        request = urllib.request.Request(
            os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/") + "/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.deepseek_key}", "Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._request_timeout()) as response:
            data = json.loads(response.read().decode("utf-8"))
        usage = data.get("usage") or {}
        cost = deepseek_cost(usage, model)
        self._add_usage(cost["input_tokens"], cost["output_tokens"], cost["cny"])
        _enforce_cost(self.usage)
        return _parse_json(str(data.get("choices", [{}])[0].get("message", {}).get("content") or ""))


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.S)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise StockResearchError("模型未返回合法JSON", code="provider_json_error") from exc
    if not isinstance(value, dict):
        raise StockResearchError("模型JSON根节点必须为对象", code="provider_json_error")
    return value
