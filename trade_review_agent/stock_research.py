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
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from contextlib import contextmanager
from math import ceil
from statistics import median
from dataclasses import dataclass
from datetime import datetime, timedelta
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
SKILL_ROOT = Path(__file__).resolve().parent / "prompts" / "stock_reverse_engineering"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
SKILL_PROTOCOL_PATH = SKILL_ROOT / "references" / "multi-agent-protocol.md"
ROLE_PROTOCOL_NAMES = {
    "capital_logic": "Capital Logic Analyst",
    "product_path": "Product Path Mapper",
    "bom": "BOM Chain Analyst",
    "bottleneck": "Bottleneck Analyst",
    "profit_flow": "Profit Flow Analyst",
    "fund_manager": "Core Asset Judge / Fund Manager",
}

# These contracts intentionally mirror the local stock-reverse-engineering skill.
# Keep role separation explicit: a generic "summary/claims" contract is not enough
# to reproduce the skill's product-path, BOM, bottleneck, and profit-flow work.
ROLE_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "capital_logic": (
        "stock", "speculation_logic", "trigger_event", "core_driver",
        "emotion_strength", "evidence_confidence", "current_catalysts",
        "claims", "challenges", "evidence_gaps",
    ),
    "product_path": (
        "stock", "real_product_line", "final_product", "product_path",
        "exposure_judgment", "evidence_confidence", "claims", "challenges",
        "evidence_gaps",
    ),
    "bom": (
        "final_product", "bom_tree", "bom_table", "claims", "challenges",
        "evidence_gaps",
    ),
    "bottleneck": (
        "current_bottleneck", "bottleneck_type", "first_price_response",
        "expansion_difficulty", "profit_realization", "next_bottleneck",
        "a_share_mapping", "evidence_confidence", "claims", "challenges",
        "evidence_gaps",
    ),
    "profit_flow": (
        "ranked_nodes", "first_tightening", "first_price_increase",
        "pricing_power", "highest_earnings_elasticity", "margin_squeezed_nodes",
        "claims", "challenges", "evidence_gaps",
    ),
}

ROLE_CHALLENGE_TARGETS = {
    "capital_logic": "情绪标签与真实产品暴露不匹配",
    "product_path": "输入对象只有相邻、间接或弱暴露",
    "bom": "产品路径存在跳跃或缺少可投资节点",
    "bottleneck": "BOM把可替代节点误判为稀缺瓶颈",
    "profit_flow": "稀缺没有转化为定价权和利润留存",
}
CHALLENGE_ROLE_TARGET = {
    "product_path": "capital_logic",
    "bom": "product_path",
    "bottleneck": "bom",
    "profit_flow": "bottleneck",
}


class StockResearchError(RuntimeError):
    def __init__(self, message: str, *, code: str = "stock_research_error") -> None:
        super().__init__(message)
        self.code = code


class CostLimitError(StockResearchError):
    pass


@dataclass(frozen=True)
class StockResearchSkillBundle:
    skill_markdown: str
    protocol_markdown: str
    version: str

    @property
    def prompt(self) -> str:
        return (
            "以下两个文件是本次研究的唯一行为协议。必须逐条执行，不得用常识摘要、旧提示词或简化流程替代。\n"
            "<SKILL.md>\n" + self.skill_markdown + "\n</SKILL.md>\n"
            "<multi-agent-protocol.md>\n" + self.protocol_markdown + "\n</multi-agent-protocol.md>"
        )


def load_stock_research_skill() -> StockResearchSkillBundle:
    """Load the canonical skill from disk for each job so prompts cannot drift."""
    try:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        protocol = SKILL_PROTOCOL_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise StockResearchError("产业链逆向研究协议文件缺失", code="skill_protocol_missing") from exc
    required = (
        "# Stock Reverse Engineering",
        "## Mandatory Protocol",
        "# Multi-Agent Protocol",
        "## Shared Research Board",
        "## Core Asset Judge / Fund Manager",
    )
    combined = skill + "\n" + protocol
    if any(marker not in combined for marker in required):
        raise StockResearchError("产业链逆向研究协议文件不完整", code="skill_protocol_invalid")
    version = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    return StockResearchSkillBundle(skill, protocol, version)


class Provider(Protocol):
    name: str
    usage: dict[str, Any]

    def evidence(self, subject: dict[str, str]) -> dict[str, Any]: ...
    def supplement(self, subject: dict[str, str], gaps: list[str]) -> dict[str, Any]: ...
    def role(self, role: str, prompt: str) -> dict[str, Any]: ...
    def review_roles(self, prompt: str) -> dict[str, Any]: ...
    def judge(self, prompt: str) -> dict[str, Any]: ...
    def single_agent(self, subject: dict[str, str]) -> dict[str, Any]: ...


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
                cache_hit INTEGER NOT NULL DEFAULT 0,
                cache_source_report_id TEXT NOT NULL DEFAULT '',
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
                cache_hit INTEGER NOT NULL DEFAULT 0,
                cache_source_report_id TEXT NOT NULL DEFAULT '',
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
        for name, declaration in (
            ("cache_hit", "INTEGER NOT NULL DEFAULT 0"),
            ("cache_source_report_id", "TEXT NOT NULL DEFAULT ''"),
        ):
            if name not in columns:
                conn.execute(f"ALTER TABLE stock_research_jobs ADD COLUMN {name} {declaration}")
        report_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(stock_research_reports)").fetchall()}
        for name, declaration in (
            ("cache_hit", "INTEGER NOT NULL DEFAULT 0"),
            ("cache_source_report_id", "TEXT NOT NULL DEFAULT ''"),
        ):
            if name not in report_columns:
                conn.execute(f"ALTER TABLE stock_research_reports ADD COLUMN {name} {declaration}")
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_stock_research_reports_subject_cache
               ON stock_research_reports(subject_type,stock_code,subject_name,created_at DESC)"""
        )
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_research_cache_copy_once
               ON stock_research_reports(user_id,cache_source_report_id)
               WHERE cache_hit=1 AND cache_source_report_id<>''"""
        )


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
            "SELECT COUNT(*) FROM stock_research_reports WHERE user_id=? AND substr(created_at,1,7)=? AND cache_hit=0",
            (user_id, month_prefix),
        ).fetchone()[0])
        daily_used = int(conn.execute(
            "SELECT COUNT(*) FROM stock_research_reports WHERE user_id=? AND substr(created_at,1,10)=? AND cache_hit=0",
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


def _cache_ttl_hours() -> int:
    try:
        return max(0, min(24 * 30, int(os.getenv("STOCK_RESEARCH_CACHE_TTL_HOURS", "24"))))
    except ValueError:
        return 24


def _is_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _find_recent_report(
    db_path: Path, *, subject: NormalizedSubject, user_id: int | None = None,
) -> sqlite3.Row | None:
    ttl_hours = _cache_ttl_hours()
    if ttl_hours <= 0:
        return None
    cutoff = (datetime.now(CN_TZ) - timedelta(hours=ttl_hours)).isoformat(timespec="seconds")
    conditions = ["schema_version>=2", "cache_hit=0", "created_at>=?", "subject_type=?"]
    params: list[Any] = [cutoff, subject.type]
    if subject.type == "stock":
        conditions.append("stock_code=?")
        params.append(subject.code)
    else:
        conditions.append("subject_name=?")
        params.append(subject.name)
    if user_id is not None:
        conditions.append("user_id=?")
        params.append(user_id)
    query = "SELECT * FROM stock_research_reports WHERE " + " AND ".join(conditions) + " ORDER BY created_at DESC LIMIT 1"
    with _connect(db_path) as conn:
        return conn.execute(query, params).fetchone()


def _copy_cached_report_for_user(
    db_path: Path, *, source: sqlite3.Row, subject: NormalizedSubject,
    user_id: int, request_ip: str,
) -> dict[str, Any]:
    source_id = str(source["id"])
    job_id = f"sr-{uuid4().hex}"
    report_id = f"report-{job_id[3:]}"
    now = _now()
    report = json.loads(str(source["report_json"]))
    meta = report.setdefault("meta", {})
    meta["cache_hit"] = True
    meta["cache_source_report_id"] = source_id
    meta["cache_source_created_at"] = str(source["created_at"])
    meta["retrieved_at"] = now
    board = report.get("research_board") if isinstance(report.get("research_board"), dict) else {}
    roles = report.get("role_outputs") if isinstance(report.get("role_outputs"), dict) else {}
    sources = report.get("evidence") if isinstance(report.get("evidence"), list) else []
    try:
        with _connect(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            active = conn.execute(
                "SELECT id FROM stock_research_jobs WHERE user_id=? AND status IN ('queued','running','retrying')",
                (user_id,),
            ).fetchone()
            if active:
                raise AuthError("当前已有一份研究正在生成，请等待完成后再提交", 409)
            conn.execute(
                """INSERT INTO stock_research_jobs
                   (id,user_id,subject_type,subject_name,stock_code,status,stage,provider,billing_mode,model_names,
                    progress,board_json,role_outputs_json,sources_json,request_ip,created_at,started_at,updated_at,
                    completed_at,cache_hit,cache_source_report_id)
                   VALUES(?,?,?,?,?,'completed','completed','cache','cache_reuse',?,100,?,?,?,?,?,?,?,?,1,?)""",
                (
                    job_id, user_id, subject.type, subject.name, subject.code,
                    str(source["model_names"]), json.dumps(board, ensure_ascii=False),
                    json.dumps(roles, ensure_ascii=False), json.dumps(sources, ensure_ascii=False),
                    request_ip, now, now, now, now, source_id,
                ),
            )
            conn.execute(
                """INSERT INTO stock_research_reports
                   (id,job_id,user_id,subject_type,subject_name,stock_code,schema_version,report_json,provider,
                    model_names,input_tokens,output_tokens,search_count,cost_cny,duration_seconds,source_count,
                    created_at,cache_hit,cache_source_report_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
                (
                    report_id, job_id, user_id, subject.type, subject.name, subject.code,
                    int(source["schema_version"]), json.dumps(report, ensure_ascii=False), "cache",
                    str(source["model_names"]), 0, 0, 0, 0.0, 0.0, len(sources), now, source_id,
                ),
            )
    except sqlite3.IntegrityError:
        with _connect(db_path) as conn:
            existing = conn.execute(
                "SELECT job_id FROM stock_research_reports WHERE user_id=? AND cache_hit=1 AND cache_source_report_id=?",
                (user_id, source_id),
            ).fetchone()
        if not existing:
            raise
        job_id = str(existing["job_id"])
    reused = get_job(db_path, job_id, user_id=user_id)
    reused["cache_hit"] = True
    reused["cache_source_report_id"] = source_id
    reused["cache_source_created_at"] = str(source["created_at"])
    return reused


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
    if not _is_truthy(payload.get("force_refresh")):
        cached = _find_recent_report(db_path, subject=subject, user_id=user_id)
        if cached:
            reused = get_job(db_path, str(cached["job_id"]), user_id=user_id)
            reused["cache_hit"] = True
            reused["cache_source_report_id"] = str(cached["id"])
            reused["cache_source_created_at"] = str(cached["created_at"])
            return reused
        shared_cached = _find_recent_report(db_path, subject=subject)
        if shared_cached:
            return _copy_cached_report_for_user(
                db_path, source=shared_cached, subject=subject,
                user_id=user_id, request_ip=request_ip,
            )
    quota = _validate_job_quota(db_path, user_id=user_id)
    billing_mode = str(quota["next_billing_mode"])
    job_id = f"sr-{uuid4().hex}"
    requested_provider = provider_name.strip().lower()
    provider = (requested_provider or os.getenv("STOCK_RESEARCH_PROVIDER", "luna")).strip().lower()
    if provider == "auto":
        if os.getenv("STOCK_RESEARCH_ALLOW_AUTOMATIC_PROVIDER_SELECTION", "0").strip().lower() not in {"1", "true", "yes"}:
            raise AuthError("自动模型切换未启用，请明确配置 Luna", 503)
        provider = select_production_provider(db_path)["provider"]
    if provider not in {"luna", "doubao_deepseek"}:
        raise AuthError("研究引擎配置无效", 503)
    if str(user.get("role")) != "admin" and provider != "luna" and os.getenv(
        "STOCK_RESEARCH_REQUIRE_LUNA_FOR_USERS", "1"
    ).strip().lower() not in {"0", "false", "no"}:
        raise AuthError("当前用户研究固定使用 Luna，服务器模型配置异常", 503)
    if start:
        ensure_provider_configured(provider)
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


def ensure_provider_configured(provider: str) -> None:
    """Fail before enqueueing when the selected provider has no credentials."""
    if provider == "luna" and not os.getenv("OPENAI_API_KEY", "").strip():
        raise AuthError("Luna 尚未完成服务器配置，请联系管理员", 503)
    if provider == "doubao_deepseek" and (
        not os.getenv("ARK_API_KEY", "").strip() or not os.getenv("DEEPSEEK_API_KEY", "").strip()
    ):
        raise AuthError("豆包或 DeepSeek 尚未完成服务器配置", 503)


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
    provider: Provider | None = None
    try:
        with _connect(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM stock_research_jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row["status"] not in {"queued", "retrying"}:
                return
            conn.execute(
                "UPDATE stock_research_jobs SET status='running',stage='collecting_evidence',progress=5,attempts=attempts+1,started_at=COALESCE(started_at,?),updated_at=? WHERE id=?",
                (_now(), _now(), job_id),
            )
            subject = NormalizedSubject(str(row["subject_type"]), str(row["subject_name"]), str(row["stock_code"]))
            provider_name = str(row["provider"])
            billing_mode = str(row["billing_mode"] or "credits")
            user_id = int(row["user_id"])
            request_ip = str(row["request_ip"])

        skill_bundle = load_stock_research_skill()
        provider = (provider_factory or build_provider)(provider_name)
        if (
            provider_name == "luna"
            and callable(getattr(provider, "single_agent", None))
            and os.getenv("STOCK_RESEARCH_LUNA_SINGLE_AGENT", "1").strip().lower() not in {"0", "false", "no"}
        ):
            _run_single_agent_pipeline(
                db_path, job_id=job_id, user_id=user_id, subject=subject, provider=provider,
                billing_mode=billing_mode, request_ip=request_ip, started=started,
            )
            return
        evidence_pack = provider.evidence(subject.payload())
        _enforce_cost(provider.usage)
        sources = normalize_sources(evidence_pack.get("evidence"))
        board: dict[str, Any] = {
            "input_stocks": [subject.payload()] if subject.type == "stock" else [],
            "subject": subject.payload(),
            "facts": evidence_pack.get("facts") or [],
            "current_catalysts": [],
            "product_paths": [],
            "bom_tree": {},
            "bottlenecks": [],
            "profit_flow": [],
            "conflicts": [],
            "evidence_confidence": {},
            "evidence_gaps": evidence_pack.get("evidence_gaps") or [],
            "skill_version": skill_bundle.version,
        }
        _persist_progress(db_path, job_id, "collecting_evidence", 8, board, {}, sources, provider.usage)
        if not sources:
            raise StockResearchError("未找到可验证的一手或权威证据", code="evidence_missing")
        if not any(item["source_tier"] in {"A", "B"} for item in sources):
            raise StockResearchError("证据仅有概念标签或低等级来源", code="evidence_quality_low")
        role_outputs: dict[str, Any] = {}
        _persist_progress(db_path, job_id, "capital_logic", 12, board, role_outputs, sources, provider.usage)

        def execute_role(role: str) -> dict[str, Any]:
            _enforce_timeout(started)
            prompt = build_role_prompt(role, subject.payload(), board, role_outputs, sources, skill_bundle=skill_bundle)
            result = provider.role(role, prompt)
            result = normalize_role_output_for_contract(result, sources)
            try:
                validate_role_output(role, result, sources)
            except StockResearchError as exc:
                if exc.code not in {"citation_error", "role_contract_error", "role_challenge_missing"}:
                    raise
                board.setdefault("contract_repairs", []).append({"role": role, "reason": exc.code})
                result = provider.role(role, build_role_repair_prompt(role, result, sources, exc, skill_bundle=skill_bundle))
                result = normalize_role_output_for_contract(result, sources)
                validate_role_output(role, result, sources)
            return result

        def consolidated_review(stage: str) -> bool:
            if os.getenv("STOCK_RESEARCH_CROSS_EXAMINATION", "1").strip().lower() in {"0", "false", "no"}:
                return False
            reviewer = getattr(provider, "review_roles", None)
            if not callable(reviewer):
                return False
            reviewed = reviewer(build_cross_examination_prompt(
                subject.payload(),
                board,
                role_outputs,
                sources,
                skill_bundle=skill_bundle,
                stage=stage,
            ))
            def validate_review(payload: Any) -> dict[str, dict[str, Any]]:
                revised_roles = payload.get("revised_roles") if isinstance(payload, dict) else None
                if not isinstance(revised_roles, dict):
                    raise StockResearchError("交叉质询没有返回完整角色修订", code="role_contract_error")
                missing = [role for role in ROLE_ORDER[:-1] if not isinstance(revised_roles.get(role), dict)]
                if missing:
                    raise StockResearchError("交叉质询缺少角色修订: " + ",".join(missing), code="role_contract_error")
                normalized: dict[str, dict[str, Any]] = {}
                for role in ROLE_ORDER[:-1]:
                    revised = normalize_role_output_for_contract(revised_roles[role], sources)
                    validate_role_output(role, revised, sources)
                    normalized[role] = revised
                return normalized

            try:
                normalized_roles = validate_review(reviewed)
            except StockResearchError as exc:
                if exc.code not in {"citation_error", "role_contract_error", "role_challenge_missing"}:
                    raise
                board.setdefault("contract_repairs", []).append({"role": "cross_examination", "stage": stage, "reason": exc.code})
                reviewed = reviewer(build_cross_examination_repair_prompt(
                    reviewed, sources, exc, skill_bundle=skill_bundle
                ))
                normalized_roles = validate_review(reviewed)
            for role, revised in normalized_roles.items():
                role_outputs[role] = revised
                merge_role_into_board(board, role, revised)
            conflicts = reviewed.get("conflicts") or []
            board.setdefault("revision_log", []).append({
                "stage": stage,
                "reviewed_roles": list(ROLE_ORDER[:-1]),
                "conflict_count": len(conflicts) if isinstance(conflicts, list) else 0,
            })
            if isinstance(conflicts, list):
                board["conflicts"] = conflicts
            _enforce_cost(provider.usage)
            return True

        # The skill protocol starts these two independent research roles in
        # parallel. They share the same evidence pack but cannot see each
        # other's draft, preventing a one-way anchoring handoff.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="stock-research-role") as executor:
            futures = {role: executor.submit(execute_role, role) for role in ("capital_logic", "product_path")}
            initial_results = {role: futures[role].result() for role in ("capital_logic", "product_path")}
        for index, role in enumerate(("capital_logic", "product_path")):
            result = initial_results[role]
            role_outputs[role] = result
            merge_role_into_board(board, role, result)
            progress = 18 + (index + 1) * 12
            _persist_progress(db_path, job_id, role, progress, board, role_outputs, sources, provider.usage)
            _enforce_cost(provider.usage)

        for index, role in enumerate(("bom", "bottleneck", "profit_flow"), start=2):
            result = execute_role(role)
            role_outputs[role] = result
            merge_role_into_board(board, role, result)
            progress = 18 + (index + 1) * 12
            _persist_progress(db_path, job_id, role, progress, board, role_outputs, sources, provider.usage)
            _enforce_cost(provider.usage)

        # One shared-board hearing preserves the skill's cross-role challenge
        # semantics without paying for a separate model round-trip per edge.
        consolidated_review("initial_cross_examination")

        # The skill permits one evidence-gap round. Search material gaps raised by
        # any role, then expose the additions to the judge rather than inventing
        # conclusions to fill an incomplete chain.
        gaps = list(dict.fromkeys(
            str(item).strip() for item in board.get("evidence_gaps", []) if str(item).strip()
        ))[:8]
        if (
            gaps
            and int(provider.usage.get("search_count", 0)) < 15
            and hasattr(provider, "supplement")
            and float(provider.usage.get("cost_cny", 0)) < MAX_COST_CNY * 0.8
        ):
            supplement = provider.supplement(subject.payload(), gaps)
            additions = normalize_sources(supplement.get("evidence"))
            sources = merge_supplement_sources(sources, additions)
            board["supplemental_facts"] = supplement.get("facts") or []
            board["supplement_search_completed"] = True
            refreshed_roles: list[str] = []
            if additions and consolidated_review("post_supplement_cross_examination"):
                refreshed_roles = list(ROLE_ORDER[:-1])
            board["supplement_refreshed_roles"] = refreshed_roles
            _persist_progress(db_path, job_id, "evidence_gap_search", 82, board, role_outputs, sources, provider.usage)
            _enforce_cost(provider.usage)

        _enforce_timeout(started)
        _persist_progress(db_path, job_id, "fund_manager", 86, board, role_outputs, sources, provider.usage)
        judge_prompt = build_judge_prompt(subject.payload(), board, role_outputs, sources, skill_bundle=skill_bundle)
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
        usage = provider.usage if provider is not None else {}
        _persist_usage_only(db_path, job_id, usage)
        spent_tokens = int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
        # Retry only failures that did not consume a substantive model response.
        # Repeating a long malformed response can double the real provider bill.
        if (
            allow_provider_retry
            and spent_tokens == 0
            and code in {"unexpected_error", "provider_json_error", "provider_error"}
            and _queue_single_provider_retry(db_path, job_id, str(exc))
        ):
            start_job(db_path, job_id, provider_factory=provider_factory)
            return
        _mark_failed(db_path, job_id, "timed_out" if code == "timeout" else "failed", code, str(exc))


def _run_single_agent_pipeline(
    db_path: Path, *, job_id: str, user_id: int, subject: NormalizedSubject,
    provider: Provider, billing_mode: str, request_ip: str, started: float,
) -> None:
    """Run the approved one-call Luna research protocol and keep billing atomic."""
    from scripts.run_stock_research_single_agent import (
        remove_redundant_dangling_evidence_ids,
        validate_report as validate_single_agent_report,
    )

    initial_board = {"subject": subject.payload(), "execution_mode": "luna_single_agent"}
    _persist_progress(db_path, job_id, "single_agent_research", 12, initial_board, {}, [], provider.usage)
    report = provider.single_agent(subject.payload())
    _enforce_timeout(started)
    _enforce_cost(provider.usage)
    if not isinstance(report, dict):
        raise StockResearchError("单 Agent 没有返回结构化报告", code="provider_json_error")
    if subject.type == "industry_chain" and report.get("input_stock_score") is None:
        report.pop("input_stock_score", None)
    removed_ids = remove_redundant_dangling_evidence_ids(report)
    report["schema_version"] = 2
    report["subject"] = subject.payload()
    sources = report.get("evidence") if isinstance(report.get("evidence"), list) else []
    validation_board = {
        **initial_board,
        "source_count": len(sources),
        "provider_response_received": True,
    }
    _persist_progress(
        db_path, job_id, "single_agent_validation", 88,
        validation_board, {}, sources, provider.usage,
    )
    if not sources:
        raise StockResearchError("未找到可验证的一手或权威证据", code="evidence_missing")
    if not any(isinstance(item, dict) and item.get("source_tier") in {"A", "B"} for item in sources):
        raise StockResearchError("证据仅有概念标签或低等级来源", code="evidence_quality_low")

    single_validation = validate_single_agent_report(report)
    if not single_validation["all_evidence_ids_exist"]:
        raise StockResearchError("报告仍包含无效证据编号", code="citation_error")
    if single_validation["self_audited_decision_pass_rate"] < 0.95:
        raise StockResearchError("关键结论的证据语义自审未达到95%", code="citation_semantic_error")
    if not single_validation["score_formula_valid"] or not single_validation["ranking_descending"]:
        raise StockResearchError("三高评分或同链排名未通过校验", code="score_error")

    prompt_version = hashlib.sha256(
        (SKILL_ROOT / "SINGLE_AGENT_PROMPT.md").read_bytes()
    ).hexdigest()
    duration_seconds = round(float(getattr(provider, "last_duration_seconds", 0.0)) or (time.monotonic() - started), 3)
    report["meta"] = {
        **(report.get("meta") if isinstance(report.get("meta"), dict) else {}),
        "provider": provider.name,
        "execution_mode": "single_agent",
        "prompt_version": prompt_version,
        "input_tokens": int(provider.usage.get("input_tokens", 0)),
        "output_tokens": int(provider.usage.get("output_tokens", 0)),
        "search_count": int(provider.usage.get("search_count", 0)),
        "cost_cny": round(float(provider.usage.get("cost_cny", 0)), 4),
        "duration_seconds": duration_seconds,
        "removed_redundant_dangling_evidence_ids": removed_ids,
        "validation": single_validation,
    }
    report["core_asset_ranking"] = report.get("same_chain_core_asset_ranking") or []
    role_outputs = {
        key: report.get(key) for key in ("capital_logic", "product_path", "bom", "bottleneck", "profit_flow", "judge")
    }
    board = {
        "subject": subject.payload(),
        "input_stocks": [subject.payload()] if subject.type == "stock" else [],
        "current_catalysts": (report.get("capital_logic") or {}).get("current_catalysts") or [],
        "product_paths": [(report.get("product_path") or {}).get("path") or []],
        "bom_tree": (report.get("bom") or {}).get("tree") or {},
        "bottlenecks": [report.get("bottleneck") or {}],
        "profit_flow": (report.get("profit_flow") or {}).get("ranked_nodes") or [],
        "conflicts": (report.get("judge") or {}).get("role_conflicts") or [],
        "evidence_confidence": report.get("audit") or {},
        "execution_mode": "luna_single_agent",
        "prompt_version": prompt_version,
    }
    report["role_outputs"] = role_outputs
    report["research_board"] = board
    _persist_progress(db_path, job_id, "fund_manager", 92, board, role_outputs, sources, provider.usage)
    validate_report(report)
    now = _now()
    _store_report_charge_and_complete(
        db_path, job_id=job_id, report_id=f"report-{job_id[3:]}", user_id=user_id,
        subject=subject, report=report, provider=provider.name, usage=provider.usage,
        duration=duration_seconds, sources=sources, board=board,
        role_outputs=role_outputs, request_ip=request_ip, now=now, billing_mode=billing_mode,
    )


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


def _persist_usage_only(db_path: Path, job_id: str, usage: dict[str, Any]) -> None:
    """Keep actual provider spend visible when report validation rejects output."""
    if not usage:
        return
    with _connect(db_path) as conn:
        conn.execute(
            """UPDATE stock_research_jobs SET input_tokens=?,output_tokens=?,search_count=?,cost_cny=?,updated_at=?
               WHERE id=?""",
            (
                int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)),
                int(usage.get("search_count", 0)), float(usage.get("cost_cny", 0)),
                _now(), job_id,
            ),
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
                report_id, job_id, user_id, subject.type, subject.name, subject.code, int(report.get("schema_version") or 1),
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
            """SELECT id,job_id,subject_type,subject_name,stock_code,provider,cost_cny,duration_seconds,source_count,created_at,
                      cache_hit,cache_source_report_id
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
        "created_at", "started_at", "updated_at", "completed_at", "cache_hit", "cache_source_report_id",
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
        source_text = str(item.get("source") or "")
        source_url = re.search(r"https?://[^\s\])]+", source_text)
        url = str(item.get("url") or (source_url.group(0) if source_url else "")).strip()
        title = str(item.get("title") or item.get("item") or item.get("fact") or "").strip()
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


def merge_supplement_sources(existing: list[dict[str, Any]], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge a later search pack without trusting its recycled E001-style IDs."""
    merged = [dict(item) for item in existing]
    seen_urls = {str(item.get("url") or "").rstrip("/") for item in merged}
    next_id = len(merged) + 1
    for item in additions:
        url_key = str(item.get("url") or "").rstrip("/")
        if not url_key or url_key in seen_urls:
            continue
        addition = dict(item)
        addition["id"] = f"E{next_id:03d}"
        next_id += 1
        merged.append(addition)
        seen_urls.add(url_key)
    return merged


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


def build_role_prompt(
    role: str,
    subject: dict[str, str],
    board: dict[str, Any],
    roles: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    skill_bundle: StockResearchSkillBundle | None = None,
) -> str:
    bundle = skill_bundle or load_stock_research_skill()
    schemas = {
        "capital_logic": (
            '{stock:string,speculation_logic:string,trigger_event:string,core_driver:string,'
            'emotion_strength:high|medium|low,evidence_confidence:high|medium|low|pending,'
            'current_catalysts:[{event,type,event_date?,evidence_ids:[E001]}],'
            'claims:[{claim,evidence_ids:[E001],confidence:high|medium|low}],'
            'challenges:[{target:"market_narrative",issue,resolution,evidence_ids:[E001]}],evidence_gaps:[string]}'
        ),
        "product_path": (
            '{stock:string,real_product_line:string,final_product:string,'
            'product_path:[{node,node_type:stock|product|material|component|system|final_demand,evidence_ids:[E001]}],'
            'exposure_judgment:core|edge|adjacent|pending,evidence_confidence:high|medium|low|pending,'
            'claims:[{claim,evidence_ids:[E001],confidence:high|medium|low}],'
            'challenges:[{target:"capital_logic",issue,resolution,evidence_ids:[E001]}],evidence_gaps:[string]}'
        ),
        "bom": (
            '{final_product:string,bom_tree:{name,children:[{name,node_type,children?:[],evidence_ids:[E001]}]},'
            'bom_table:[{node,chain_position:upstream|midstream|downstream,a_share_companies:[{name,code?}],'
            'value_trend,evidence_confidence:high|medium|low|pending,evidence_ids:[E001]}],'
            'claims:[{claim,evidence_ids:[E001],confidence:high|medium|low}],'
            'challenges:[{target:"product_path",issue,resolution,evidence_ids:[E001]}],evidence_gaps:[string]}'
        ),
        "bottleneck": (
            '{current_bottleneck:string,bottleneck_type:structural|capacity|material|emotional|false_bottleneck,'
            'first_price_response:string,expansion_difficulty:string,profit_realization:string,next_bottleneck:string,'
            'a_share_mapping:[{node,companies:[{name,code?}],reason,evidence_ids:[E001]}],'
            'evidence_confidence:high|medium|low|pending,'
            'claims:[{claim,evidence_ids:[E001],confidence:high|medium|low}],'
            'challenges:[{target:"bom",issue,resolution,evidence_ids:[E001]}],evidence_gaps:[string]}'
        ),
        "profit_flow": (
            '{ranked_nodes:[{node,stars:1|2|3|4|5,classification:core_bottleneck|strong_beneficiary|volume_growth|theme_follower|false_core,'
            'first_price_increase:string,supply_tightness:string,pricing_power:string,profit_elasticity:string,'
            'a_share_companies:[{name,code?}],evidence_ids:[E001]}],first_tightening:string,first_price_increase:string,'
            'pricing_power:string,highest_earnings_elasticity:string,margin_squeezed_nodes:[string],'
            'claims:[{claim,evidence_ids:[E001],confidence:high|medium|low}],'
            'challenges:[{target:"bottleneck",issue,resolution,evidence_ids:[E001]}],evidence_gaps:[string]}'
        ),
    }
    return _json_prompt(
        bundle.prompt
        + f"\n\n当前只执行协议中的角色：{ROLE_PROTOCOL_NAMES[role]}。"
        + f"\n固定挑战目标：{ROLE_CHALLENGE_TARGETS[role]}。不得跳过协议中的必答项。",
        subject, board, roles, sources,
        "只输出严格JSON，契约=" + schemas[role] + "。每项重要事实、路径节点、表格行和挑战必须引用证据ID；证据不足写pending/待验证，不得补造。"
    )


def build_role_repair_prompt(
    role: str,
    previous: Any,
    sources: list[dict[str, Any]],
    error: StockResearchError,
    *,
    skill_bundle: StockResearchSkillBundle | None = None,
) -> str:
    bundle = skill_bundle or load_stock_research_skill()
    known_ids = [str(item.get("id")) for item in sources if item.get("id")]
    return (
        bundle.prompt
        + f"\n你正在修复 {ROLE_PROTOCOL_NAMES[role]} 角色的JSON契约错误：{error}。"
        "只能修正JSON结构、evidence_ids和必需的挑战字段，不得新增事实、来源或投资建议。"
        "必须保留并补齐该角色专属字段："
        + json.dumps(ROLE_REQUIRED_FIELDS[role], ensure_ascii=False)
        + "。挑战必须明确target/issue/resolution/evidence_ids。"
        "每条claim必须至少引用一个给定证据ID，且只能使用以下ID："
        + json.dumps(known_ids, ensure_ascii=False)
        + "\n上一次输出="
        + json.dumps(previous, ensure_ascii=False)
        + "\n仅输出修复后的严格JSON对象。"
    )


def build_role_revision_prompt(
    target_role: str,
    challenger_role: str,
    challenge: list[dict[str, Any]],
    original: dict[str, Any],
    subject: dict[str, str],
    board: dict[str, Any],
    roles: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    skill_bundle: StockResearchSkillBundle | None = None,
) -> str:
    bundle = skill_bundle or load_stock_research_skill()
    base = build_role_prompt(
        target_role, subject, board, roles, sources, skill_bundle=bundle
    )
    return (
        base
        + "\n\n这是协议规定的交叉质询修订轮。"
        + f"{ROLE_PROTOCOL_NAMES[challenger_role]} 对你的产物提出了以下挑战："
        + json.dumps(challenge, ensure_ascii=False)
        + "\n你的原始产物="
        + json.dumps(original, ensure_ascii=False)
        + "\n必须逐项回应挑战：证据支持则修订；证据不支持则保留原判断并在challenges.resolution说明理由。"
        + "不得删除原有有效证据，不得补造事实。只输出完整的修订后角色JSON。"
    )


def build_cross_examination_prompt(
    subject: dict[str, str],
    board: dict[str, Any],
    roles: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    skill_bundle: StockResearchSkillBundle | None = None,
    stage: str = "initial_cross_examination",
) -> str:
    bundle = skill_bundle or load_stock_research_skill()
    role_contracts = {role: list(ROLE_REQUIRED_FIELDS[role]) for role in ROLE_ORDER[:-1]}
    return _json_prompt(
        bundle.prompt
        + "\n\n现在执行共享研究板的统一交叉质询轮。五个研究角色必须逐项阅读其他角色产物，"
        "完成协议规定的挑战：资金标签与真实产品暴露、产品路径跳跃、BOM遗漏稀缺节点、"
        "瓶颈是否真正转化为定价权和利润。不能只写泛泛的‘同意’。"
        + f"\n审议阶段={stage}。若证据支持挑战则修订；若不支持则保留判断并在 challenges.resolution 说明。",
        subject,
        board,
        roles,
        sources,
        "只输出严格JSON：{revised_roles:{capital_logic:完整角色JSON,product_path:完整角色JSON,"
        "bom:完整角色JSON,bottleneck:完整角色JSON,profit_flow:完整角色JSON},"
        "conflicts:[{issue,roles:[角色名],resolution,evidence_ids:[E001]}]}。"
        "revised_roles 必须包含全部五个角色，即使某角色结论无需变化也要原样返回；每个角色必填字段="
        + json.dumps(role_contracts, ensure_ascii=False)
        + "。不得新增证据ID，不得补造事实。",
    )


def build_cross_examination_repair_prompt(
    previous: Any,
    sources: list[dict[str, Any]],
    error: StockResearchError,
    *,
    skill_bundle: StockResearchSkillBundle | None = None,
) -> str:
    bundle = skill_bundle or load_stock_research_skill()
    known_ids = [str(item.get("id")) for item in sources if item.get("id")]
    return (
        bundle.prompt
        + "\n\n统一交叉质询的JSON未通过后端契约校验：" + str(error)
        + "。只修复 revised_roles 的结构、缺失字段、空 evidence_ids 或无效证据ID；"
        "不得改变事实判断、不得增加新来源、不得删除任何角色。"
        + "\n允许使用的证据ID=" + json.dumps(known_ids, ensure_ascii=False)
        + "\n上一次输出=" + json.dumps(previous, ensure_ascii=False)
        + "\n只输出完整严格JSON {revised_roles:{capital_logic,product_path,bom,bottleneck,profit_flow},conflicts:[...]}。"
    )


def build_judge_prompt(
    subject: dict[str, str],
    board: dict[str, Any],
    roles: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    skill_bundle: StockResearchSkillBundle | None = None,
) -> str:
    bundle = skill_bundle or load_stock_research_skill()
    stock_extra = (
        "股票输入必须生成input_stock_score和same_chain_core_asset_ranking两张三高表。三高均为1-10分、一位小数，"
        "core_score=0.4*barrier+0.3*profit+0.3*growth。same_chain_core_asset_ranking必须列出BOM/瓶颈/利润角色发现的"
        "同链A股并按core_score降序；输入股票已有独立评分，不得再次放入同链排名。若确无中等置信度对象，数组可为空，但必须用"
        "same_chain_core_asset_status={status:none,reason,evidence_ids}明确证据缺口。"
        if subject["type"] == "stock" else
        "产业链输入不得生成input_stock_score；必须生成产业链核心资产、瓶颈和利润捕获排名。"
    )
    schema = """只输出严格JSON：{
headline:string,
capital_logic:{summary,speculation_json:{event,logic,industry_trend,evidence_confidence},evidence_ids:[E001]},
product_path:{summary,path:[string],exposure_judgment,evidence_ids:[E001]},
bom:{summary,tree:object,items:[{node,chain_position,a_share_companies,value_trend,evidence_confidence,evidence_ids:[E001]}],evidence_ids:[E001]},
bottleneck:{summary,current,type,first_price_response,expansion_difficulty,profit_realization,next_bottleneck,a_share_mapping,evidence_ids:[E001]},
profit_flow:{summary,ranked_nodes:[{node,stars,classification,pricing_power,profit_elasticity,a_share_companies,evidence_ids:[E001]}],evidence_ids:[E001]},
positioning:{label,fund_positioning,is_core_beneficiary,earns_industrial_profit,emotional_premium,cleaner_same_chain_companies:[string],reason,evidence_ids:[E001]},
input_stock_score?:{barrier,profit,growth,core_score,explanation,evidence_ids:[E001]},
same_chain_core_asset_ranking:[{name,code?,industry_node,product,industry_position,barrier,profit,growth,core_score,labels:[string],reason,evidence_ids:[E001]}],
same_chain_core_asset_status?:{status:ranked|none,reason,evidence_ids:[E001]},
bottleneck_ranking:[{name,position,reason,evidence_ids:[E001]}],
profit_capture_ranking:[{name,position,reason,evidence_ids:[E001]}],
judge:{conclusion,classifications:{emotion_leader,industry_leader,capacity_core,shovel_seller,high_elasticity,high_profit,high_growth,long_term_tracking},role_conflicts:[{issue,roles,resolution,evidence_ids:[E001]}],disconfirming_signals:[string],evidence_ids:[E001]}
}。"""
    judge_board = {key: board.get(key) for key in (
        "input_stocks", "current_catalysts", "product_paths", "bom_tree", "bom_table",
        "bottlenecks", "profit_flow", "conflicts", "evidence_confidence", "evidence_gaps",
        "supplemental_facts",
    ) if board.get(key) not in (None, [], {})}
    judge_sources = [{
        "id": item.get("id"), "title": item.get("title"), "publisher": item.get("publisher"),
        "published_at": item.get("published_at"), "source_tier": item.get("source_tier"),
        "excerpt": str(item.get("excerpt") or "")[:280],
    } for item in sources]
    return _json_prompt(
        bundle.prompt
        + "\n\n当前只执行协议中的第六角色 Core Asset Judge / Fund Manager。必须阅读并裁决前五角色全部产物，明确区分资金炒作逻辑和产业利润逻辑；"
        "判断输入对象赚产业利润还是主要赚情绪溢价；完成情绪龙头/产业龙头/容量核心/卖铲子/高弹性/补涨/伪核心等定位。"
        "所有实质冲突必须写明参与角色、裁决和证据；证据不足必须降级或标记待验证，不得补造。" + stock_extra,
        subject, judge_board, roles, judge_sources, schema
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
    if not isinstance(result, dict):
        raise StockResearchError(f"{role} 角色输出不完整", code="role_contract_error")
    missing = [field for field in ROLE_REQUIRED_FIELDS[role] if field not in result or result[field] is None]
    if missing:
        raise StockResearchError(f"{role} 角色缺少专属字段: {', '.join(missing)}", code="role_contract_error")
    if not isinstance(result.get("claims"), list) or not result["claims"]:
        raise StockResearchError(f"{role} 角色缺少可审计结论", code="role_contract_error")
    known = {item["id"] for item in sources}
    for claim in result["claims"]:
        ids = claim.get("evidence_ids") if isinstance(claim, dict) else None
        if not ids or any(str(item) not in known for item in ids):
            raise StockResearchError(f"{role} 存在无效或缺失证据引用", code="citation_error")
    challenges = result.get("challenges")
    if not isinstance(challenges, list) or not challenges:
        raise StockResearchError(f"{role} 必须执行固定挑战关系", code="role_challenge_missing")
    for challenge in challenges:
        if not isinstance(challenge, dict) or not all(challenge.get(key) for key in ("target", "issue", "resolution", "evidence_ids")):
            raise StockResearchError(f"{role} 挑战记录不完整", code="role_challenge_missing")
        if any(str(item) not in known for item in challenge["evidence_ids"]):
            raise StockResearchError(f"{role} 挑战引用无效", code="citation_error")
    if role == "product_path" and len(result.get("product_path") or []) < 4:
        raise StockResearchError("产品路径必须覆盖对象、产品/材料、部件/系统和最终需求", code="role_contract_error")
    if role == "bom" and (not result.get("bom_tree") or not result.get("bom_table")):
        raise StockResearchError("BOM角色必须输出树和A股映射表", code="role_contract_error")
    if role == "bottleneck" and not result.get("a_share_mapping"):
        raise StockResearchError("瓶颈角色必须输出A股映射", code="role_contract_error")
    if role == "profit_flow" and not result.get("ranked_nodes"):
        raise StockResearchError("利润流向角色必须输出五档节点排名", code="role_contract_error")
    _validate_nested_evidence_ids(result, known, role)


def normalize_role_output_for_contract(result: Any, sources: list[dict[str, Any]]) -> Any:
    """Downgrade unsupported challenge assertions to evidence gaps.

    A challenge that literally says evidence is missing cannot honestly cite proof
    of the missing fact. Keep the gap, but do not let it masquerade as an
    evidence-backed role conflict or trigger another model call.
    """
    if not isinstance(result, dict) or not isinstance(result.get("challenges"), list):
        return result
    known = {str(item.get("id")) for item in sources if item.get("id")}
    valid: list[dict[str, Any]] = []
    gaps = list(result.get("evidence_gaps") or [])
    for challenge in result["challenges"]:
        ids = challenge.get("evidence_ids") if isinstance(challenge, dict) else None
        if (
            isinstance(challenge, dict)
            and all(challenge.get(key) for key in ("target", "issue", "resolution"))
            and isinstance(ids, list) and ids
            and all(str(item) in known for item in ids)
        ):
            valid.append(challenge)
        elif isinstance(challenge, dict) and str(challenge.get("issue") or "").strip():
            gap = str(challenge["issue"]).strip()
            if gap not in gaps:
                gaps.append(gap)
    result["challenges"] = valid
    result["evidence_gaps"] = gaps
    return result


def merge_role_into_board(board: dict[str, Any], role: str, result: dict[str, Any]) -> None:
    if role == "capital_logic":
        board["current_catalysts"] = result.get("current_catalysts") or []
    elif role == "product_path":
        board["product_paths"] = [result.get("product_path") or []]
    elif role == "bom":
        board["bom_tree"] = result.get("bom_tree") or {}
        board["bom_table"] = result.get("bom_table") or []
    elif role == "bottleneck":
        board["bottlenecks"] = [{key: result.get(key) for key in (
            "current_bottleneck", "bottleneck_type", "first_price_response",
            "expansion_difficulty", "profit_realization", "next_bottleneck", "a_share_mapping",
        )}]
    elif role == "profit_flow":
        board["profit_flow"] = result.get("ranked_nodes") or []
    board.setdefault("evidence_confidence", {})[role] = result.get("evidence_confidence") or _role_confidence(result)
    board.setdefault("role_findings", {})[role] = _role_summary(role, result)
    board.setdefault("conflicts", []).extend(result.get("challenges") or [])
    gaps = board.setdefault("evidence_gaps", [])
    for gap in result.get("evidence_gaps") or []:
        if gap not in gaps:
            gaps.append(gap)


def finalize_report(report: Any, subject: NormalizedSubject, board: dict[str, Any], roles: dict[str, Any], sources: list[dict[str, Any]], provider: str, usage: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise StockResearchError("裁决模型未返回结构化报告", code="report_contract_error")
    if subject.type == "stock" and isinstance(report.get("input_stock_score"), dict):
        score = report["input_stock_score"]
        try:
            barrier, profit, growth = (float(score.get(key, -1)) for key in ("barrier", "profit", "growth"))
        except (TypeError, ValueError):
            pass
        else:
            if all(1 <= value <= 10 for value in (barrier, profit, growth)):
                expected = round(barrier * 0.4 + profit * 0.3 + growth * 0.3, 1)
                score["core_score"] = expected
                score["calculation"] = f"0.4×{barrier:.1f}+0.3×{profit:.1f}+0.3×{growth:.1f}={expected:.1f}"
                explanation = str(score.get("explanation") or "")
                if explanation:
                    score["explanation"] = re.sub(
                        r"core_score\s*=[^。；\n]*",
                        f"core_score={score['calculation']}",
                        explanation,
                        flags=re.I,
                    )
    rankings = report.get("same_chain_core_asset_ranking")
    if rankings is None and isinstance(report.get("core_asset_ranking"), list):
        rankings = report["core_asset_ranking"]
        report["same_chain_core_asset_ranking"] = rankings
    if subject.type == "stock":
        rankings = [item for item in rankings or [] if isinstance(item, dict) and not (
            str(item.get("name") or "").strip() == subject.name
            or (subject.code and str(item.get("code") or "").strip() == subject.code)
        )]
        report["same_chain_core_asset_ranking"] = rankings
    for item in rankings or []:
        if not isinstance(item, dict):
            continue
        try:
            barrier, profit, growth = (float(item.get(key, -1)) for key in ("barrier", "profit", "growth"))
        except (TypeError, ValueError):
            continue
        if all(1 <= value <= 10 for value in (barrier, profit, growth)):
            item["core_score"] = round(barrier * 0.4 + profit * 0.3 + growth * 0.3, 1)
    report["core_asset_ranking"] = rankings or []  # v1 frontend/API compatibility alias
    report["schema_version"] = 2
    report["subject"] = subject.payload()
    report["evidence"] = sources
    report["research_board"] = board
    report["role_outputs"] = roles
    report["meta"] = {
        "provider": provider,
        "skill_name": "stock-reverse-engineering",
        "skill_version": str(board.get("skill_version") or ""),
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
    required = (
        "capital_logic", "product_path", "bom", "bottleneck", "profit_flow", "positioning",
        "same_chain_core_asset_ranking", "bottleneck_ranking", "profit_capture_ranking", "judge",
    )
    for key in required:
        if key not in report or report[key] in (None, ""):
            raise StockResearchError(f"最终报告缺少 {key}", code="report_contract_error")
    known = {item.get("id") for item in report.get("evidence", []) if isinstance(item, dict)}
    for key in ("capital_logic", "product_path", "bom", "bottleneck", "profit_flow", "positioning", "judge"):
        section = report.get(key)
        ids = section.get("evidence_ids") if isinstance(section, dict) else None
        if not ids or any(item not in known for item in ids):
            raise StockResearchError(f"{key} 缺少可验证证据", code="citation_error")
        _validate_nested_evidence_ids(section, known, f"最终报告/{key}")
    if subject.get("type") == "stock":
        score = report.get("input_stock_score")
        if not isinstance(score, dict):
            raise StockResearchError("股票报告缺少三高评分", code="score_error")
        barrier, profit, growth = (float(score.get(key, -1)) for key in ("barrier", "profit", "growth"))
        if any(value < 1 or value > 10 for value in (barrier, profit, growth)):
            raise StockResearchError("三高评分必须在1-10", code="score_error")
        expected = round(barrier * 0.4 + profit * 0.3 + growth * 0.3, 1)
        if abs(float(score.get("core_score", -1)) - expected) > 0.11:
            raise StockResearchError("三高综合分公式不正确", code="score_error")
        ranking = report.get("same_chain_core_asset_ranking") or []
        status = report.get("same_chain_core_asset_status")
        if not ranking:
            if not isinstance(status, dict) or status.get("status") != "none" or not status.get("reason"):
                raise StockResearchError("未识别同链核心资产时必须明确证据缺口", code="report_contract_error")
            ids = status.get("evidence_ids") or []
            if not ids or any(item not in known for item in ids):
                raise StockResearchError("同链资产缺口说明缺少证据", code="citation_error")
        else:
            input_name = str(subject.get("name") or "")
            input_code = str(subject.get("code") or "")
            if any(str(item.get("name") or "") == input_name or (input_code and str(item.get("code") or "") == input_code) for item in ranking if isinstance(item, dict)):
                raise StockResearchError("同链核心资产排名不得重复输入股票", code="report_contract_error")
    else:
        if "input_stock_score" in report:
            raise StockResearchError("产业链报告不得生成输入股票评分", code="score_error")
    if not report.get("bottleneck_ranking") or not report.get("profit_capture_ranking"):
        raise StockResearchError("最终报告必须包含瓶颈榜和利润捕获榜", code="report_contract_error")
    core_scores: list[float] = []
    for key in ("same_chain_core_asset_ranking", "bottleneck_ranking", "profit_capture_ranking"):
        for item in report.get(key) or []:
            ids = item.get("evidence_ids") if isinstance(item, dict) else None
            if not ids or any(evidence_id not in known for evidence_id in ids):
                raise StockResearchError(f"{key} 存在无效或缺失证据引用", code="citation_error")
            if key == "same_chain_core_asset_ranking":
                try:
                    values = [float(item.get(name, -1)) for name in ("barrier", "profit", "growth", "core_score")]
                except (TypeError, ValueError):
                    raise StockResearchError("同链资产三高评分格式错误", code="score_error")
                if any(value < 1 or value > 10 for value in values):
                    raise StockResearchError("同链资产三高评分必须在1-10", code="score_error")
                expected = round(values[0] * 0.4 + values[1] * 0.3 + values[2] * 0.3, 1)
                if abs(values[3] - expected) > 0.11:
                    raise StockResearchError("同链资产三高综合分公式不正确", code="score_error")
                core_scores.append(values[3])
    if core_scores != sorted(core_scores, reverse=True):
        raise StockResearchError("同链核心资产必须按综合分降序", code="score_error")


def _validate_nested_evidence_ids(value: Any, known: set[str], role: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "evidence_ids":
                if not isinstance(child, list) or not child or any(str(item) not in known for item in child):
                    raise StockResearchError(f"{role} 存在无效或缺失证据引用", code="citation_error")
            else:
                _validate_nested_evidence_ids(child, known, role)
    elif isinstance(value, list):
        for child in value:
            _validate_nested_evidence_ids(child, known, role)


def _role_confidence(result: dict[str, Any]) -> str:
    confidences = [str(item.get("confidence")) for item in result.get("claims") or [] if isinstance(item, dict)]
    if "low" in confidences:
        return "low"
    if "medium" in confidences:
        return "medium"
    return "high" if confidences else "pending"


def _role_summary(role: str, result: dict[str, Any]) -> str:
    keys = {
        "capital_logic": "speculation_logic",
        "product_path": "real_product_line",
        "bom": "final_product",
        "bottleneck": "current_bottleneck",
        "profit_flow": "pricing_power",
    }
    return str(result.get("summary") or result.get(keys[role]) or "")


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
        self.last_duration_seconds = 0.0
        self._state_lock = threading.Lock()
        try:
            timeout = int(os.getenv("STOCK_RESEARCH_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
        except ValueError:
            timeout = DEFAULT_TIMEOUT_SECONDS
        self.deadline = time.monotonic() + max(30, timeout)

    def _add_usage(self, input_tokens: int, output_tokens: int, cost_cny: float, searches: int = 0) -> None:
        with self._state_lock:
            self.usage["input_tokens"] += int(input_tokens)
            self.usage["output_tokens"] += int(output_tokens)
            self.usage["search_count"] += int(searches)
            self.usage["cost_cny"] = round(float(self.usage["cost_cny"]) + float(cost_cny), 6)

    def _request_timeout(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise StockResearchError("研究任务超过5分钟", code="timeout")
        return max(1.0, min(300.0, remaining))


class LunaProvider(BaseProvider):
    name = "luna"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("STOCK_RESEARCH_LUNA_MODEL", "gpt-5.6-luna").strip()
        if not self.api_key:
            raise StockResearchError("服务器未配置 OPENAI_API_KEY", code="provider_not_configured")

    def evidence(self, subject: dict[str, str]) -> dict[str, Any]:
        bundle = load_stock_research_skill()
        prompt = (
            bundle.prompt
            + "\n\n你是六角色开始前的证据编辑。最多使用8次Web Search，收集10-15条可验证证据，并平衡覆盖："
            "①输入对象近期资金交易催化、价格或公告；②真实产品暴露、财务和产能；③从最终产品/BOM/瓶颈/利润池反推的"
            "至少3家同链A股候选公司及其主营、壁垒、盈利和成长证据。不能把同花顺、东方财富或券商概念标签当证明。"
            "优先公司公告、财报、交易所、政府和行业机构；"
            "概念页只作线索。source_tier必须严格为A/B/C/D：A=公告财报交易所政府，B=行业协会或权威研究，C=可靠财经媒体，D=概念标签。"
            "输出严格JSON {facts:[{topic,fact,evidence_ids:[E001]}],evidence_gaps:[string],"
            "evidence:[{id,title,url,publisher,published_at,source_tier,excerpt}]}。每条证据必须有可直接打开的url。对象="
            + json.dumps(subject, ensure_ascii=False)
        )
        return self._call(prompt, web=True)

    def single_agent(self, subject: dict[str, str]) -> dict[str, Any]:
        from scripts.run_stock_research_single_agent import load_prompt, report_schema

        subject_type = str(subject.get("type") or "stock")
        prompt = load_prompt(str(subject.get("name") or ""), str(subject.get("code") or ""), subject_type)
        body: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
            "reasoning": {"effort": os.getenv("STOCK_RESEARCH_LUNA_REASONING", "high")},
            "tools": [{"type": "web_search"}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "stock_research_single_agent",
                    "strict": True,
                    "schema": report_schema(subject_type),
                }
            },
            "max_output_tokens": int(os.getenv("STOCK_RESEARCH_LUNA_MAX_OUTPUT_TOKENS", "30000")),
        }
        request = urllib.request.Request(
            os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/responses",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, method="POST",
        )
        request_started = time.monotonic()
        try:
            with _provider_urlopen(
                request, timeout=self._request_timeout(), proxy_url=os.getenv("OPENAI_PROXY_URL", "").strip()
            ) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            raise StockResearchError(f"Luna HTTP {exc.code}: {detail}", code="provider_error") from exc
        self.last_duration_seconds = round(time.monotonic() - request_started, 3)
        self._write_debug_response(data)
        usage = data.get("usage") or {}
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        searches = sum(1 for item in data.get("output", []) if isinstance(item, dict) and item.get("type") == "web_search_call")
        usd = input_tokens * 0.20 / 1_000_000 + output_tokens * 1.20 / 1_000_000 + searches * 0.01
        self._add_usage(input_tokens, output_tokens, usd * float(os.getenv("STOCK_RESEARCH_USD_CNY", "7.2")), searches)
        response_text = extract_responses_text(data)
        if not response_text.strip():
            reason = str((data.get("incomplete_details") or {}).get("reason") or data.get("status") or "empty_output")
            raise StockResearchError(f"Luna 未返回完整结构化 JSON（{reason}）", code="provider_json_error")
        return _parse_json(response_text)

    def role(self, role: str, prompt: str) -> dict[str, Any]:
        return self._call(prompt, web=False)

    def review_roles(self, prompt: str) -> dict[str, Any]:
        return self._call(prompt, web=False)

    def supplement(self, subject: dict[str, str], gaps: list[str]) -> dict[str, Any]:
        bundle = load_stock_research_skill()
        return self._call(
            bundle.prompt
            + "\n\n这是协议允许的证据缺口补搜。最多使用5次Web Search。优先补齐同产业链A股比较：从产品路径、BOM、当前/下一瓶颈和"
            "利润池寻找比输入对象更纯粹或更核心的A股表达，并用公告、财报、交易所或行业机构证据验证主营、壁垒、利润和成长；"
            "同时补齐下列角色提出的实质缺口，不重复已有搜索。只能输出严格JSON "
            "{facts:[{topic,fact,evidence_ids:[E001]}],evidence:[{id,title,url,publisher,published_at,source_tier,excerpt}]}，"
            "每条证据必须有title和可直接打开的url。对象="
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
            with _provider_urlopen(
                request,
                timeout=self._request_timeout(),
                proxy_url=os.getenv("OPENAI_PROXY_URL", "").strip(),
            ) as response:
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
        with self._state_lock:
            index = len(list(path.glob("luna_response_*.json"))) + 1
            (path / f"luna_response_{index:02d}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )


def _provider_urlopen(
    request: urllib.request.Request, *, timeout: int, proxy_url: str = ""
):
    """Open a provider request through its dedicated proxy without affecting other integrations."""
    if proxy_url:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        )
        return opener.open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)


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
        bundle = load_stock_research_skill()
        response = self._doubao_search(
            bundle.prompt
            + "\n\n收集8-15条A股产业链证据，优先公告财报交易所政府行业机构，输出严格JSON，字段facts/evidence_gaps/evidence。对象="
            + json.dumps(subject, ensure_ascii=False),
        )
        usage = response.get("usage") or {}
        cost = ark_cost(usage)
        self._add_usage(cost["input_tokens"], cost["output_tokens"], cost["cny"], 1)
        return _parse_json(extract_responses_text(response))

    def role(self, role: str, prompt: str) -> dict[str, Any]:
        return self._deepseek(prompt, self.flash_model)

    def review_roles(self, prompt: str) -> dict[str, Any]:
        return self._deepseek(prompt, self.flash_model)

    def supplement(self, subject: dict[str, str], gaps: list[str]) -> dict[str, Any]:
        bundle = load_stock_research_skill()
        response = self._doubao_search(
            bundle.prompt
            + "\n\n只补齐以下产业链研究证据缺口，输出严格JSON facts/evidence。对象="
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
