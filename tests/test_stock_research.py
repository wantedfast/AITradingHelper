from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from trade_review_agent.auth_system import AuthError, init_auth_db
from trade_review_agent.stock_research import (
    create_job,
    get_job,
    get_report,
    init_schema,
    list_reports,
    normalize_subject,
    quota_status,
    recover_jobs,
    run_job,
    select_production_provider_from_metrics,
    validate_report,
)


EVIDENCE = [
    {"id": "E001", "title": "公司年度报告", "url": "https://example.com/annual", "publisher": "交易所", "source_tier": "A", "excerpt": "主营与产能"},
    {"id": "E002", "title": "行业数据", "url": "https://example.com/industry", "publisher": "行业协会", "source_tier": "B", "excerpt": "需求与价格"},
]


class FakeProvider:
    name = "luna"

    def __init__(self, *, invalid=False, fail=False, empty_evidence=False, cost_cny=0.36):
        self.invalid = invalid
        self.fail = fail
        self.empty_evidence = empty_evidence
        self.usage = {"input_tokens": 1200, "output_tokens": 400, "search_count": 2, "cost_cny": cost_cny}
        self.subject = {"type": "stock"}

    def evidence(self, subject):
        self.subject = subject
        if self.fail:
            raise RuntimeError("provider unavailable")
        if self.empty_evidence:
            return {"facts": [], "evidence_gaps": ["未找到证据"], "evidence": []}
        return {"facts": ["事实"], "evidence_gaps": [], "evidence": EVIDENCE}

    def role(self, role, prompt):
        return {"summary": f"{role}结论", "claims": [{"claim": "可验证结论", "evidence_ids": ["E001"], "confidence": "high"}], "challenges": ["检查上一角色假设"], "evidence_gaps": []}

    def judge(self, prompt):
        section = lambda summary: {"summary": summary, "evidence_ids": ["E001"]}
        report = {
            "headline": "产业需求存在，但利润只集中在高壁垒环节",
            "capital_logic": section("资金围绕需求催化交易"),
            "product_path": section("产品进入关键部件"),
            "bom": {**section("材料、设备、封装与测试"), "items": ["材料"]},
            "bottleneck": section("认证周期是当前瓶颈"),
            "profit_flow": section("利润集中在有认证壁垒的供应商"),
            "positioning": {**section("具备产品卡位"), "label": "产业龙头"},
            "input_stock_score": {"barrier": 80, "profit": 70, "growth": 60, "core_score": 71.0, "evidence_ids": ["E001"]},
            "core_asset_ranking": [{"name": "样本公司", "position": "产业龙头", "reason": "壁垒较高", "evidence_ids": ["E001"]}],
            "judge": {**section("证据支持产业定位"), "conclusion": "核心但仍需验证", "role_conflicts": ["需求与利润不同步"], "disconfirming_signals": ["订单未兑现"]},
        }
        if self.invalid:
            report["judge"]["evidence_ids"] = ["E999"]
        if self.subject.get("type") == "industry_chain":
            report.pop("input_stock_score", None)
            report["bottleneck_ranking"] = [{"name": "认证环节", "reason": "扩产周期长", "evidence_ids": ["E001"]}]
            report["profit_capture_ranking"] = [{"name": "关键材料", "reason": "定价权较强", "evidence_ids": ["E001"]}]
        return report


class StockResearchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Path(self.temp.name) / "auth.sqlite"
        init_auth_db(self.db)
        init_schema(self.db)
        now = "2026-08-23T09:00:00+08:00"
        conn = sqlite3.connect(self.db)
        try:
            cursor = conn.execute(
                """INSERT INTO users(phone,username,email,email_verified,password_hash,password_salt,role,status,invite_code,created_at)
                   VALUES('email:test@example.com','tester','test@example.com',1,'x','y','user','active','INVTEST1',?)""", (now,)
            )
            self.user_id = int(cursor.lastrowid)
            conn.execute("INSERT INTO credit_ledger(user_id,delta,reason,created_at) VALUES(?,5,'test',?)", (self.user_id, now))
            conn.commit()
        finally:
            conn.close()
        self.user = {"id": self.user_id, "role": "user"}

    def tearDown(self):
        self.temp.cleanup()

    def balance(self):
        conn = sqlite3.connect(self.db)
        try:
            return int(conn.execute("SELECT COALESCE(SUM(delta),0) FROM credit_ledger WHERE user_id=?", (self.user_id,)).fetchone()[0])
        finally:
            conn.close()

    def activate_membership(self):
        expires = (datetime.now().astimezone() + timedelta(days=60)).isoformat(timespec="seconds")
        conn = sqlite3.connect(self.db)
        try:
            conn.execute(
                "UPDATE users SET membership_status='active', membership_expires_at=? WHERE id=?",
                (expires, self.user_id),
            )
            conn.commit()
        finally:
            conn.close()

    def seed_successful_report(self, created_at: str, suffix: str):
        conn = sqlite3.connect(self.db)
        try:
            conn.execute(
                """INSERT INTO stock_research_reports
                   (id,job_id,user_id,subject_type,subject_name,report_json,provider,created_at)
                   VALUES(?,?,?,?,?,'{}','luna',?)""",
                (f"report-seed-{suffix}", f"job-seed-{suffix}", self.user_id, "stock", "样本", created_at),
            )
            conn.commit()
        finally:
            conn.close()

    def test_input_normalization_enforces_one_subject(self):
        self.assertEqual(normalize_subject({"type": "stock", "value": "华正新材"}, allow_fetch=False).code, "603186")
        self.assertEqual(normalize_subject({"type": "industry_chain", "value": "算力租赁产业链"}).name, "算力租赁产业链")
        with self.assertRaises(AuthError):
            normalize_subject({"type": "industry_chain", "value": "算力租赁、PCB"})

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all"})
    def test_complete_six_role_report_charges_three_once(self):
        job = create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        run_job(self.db, job["id"], provider_factory=lambda _: FakeProvider())
        done = get_job(self.db, job["id"], user_id=self.user_id)
        self.assertEqual(done["status"], "completed")
        self.assertEqual(self.balance(), 2)
        report = get_report(self.db, done["report_id"], user_id=self.user_id)["report"]
        self.assertEqual(set(report["role_outputs"]), {"capital_logic", "product_path", "bom", "bottleneck", "profit_flow"})
        self.assertEqual(report["input_stock_score"]["core_score"], 71.0)
        run_job(self.db, job["id"], provider_factory=lambda _: FakeProvider())
        self.assertEqual(self.balance(), 2)
        self.assertEqual(len(list_reports(self.db, user_id=self.user_id)), 1)

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all"})
    def test_provider_or_contract_failure_does_not_charge(self):
        first = create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        run_job(self.db, first["id"], provider_factory=lambda _: FakeProvider(fail=True), allow_provider_retry=False)
        self.assertEqual(get_job(self.db, first["id"], user_id=self.user_id)["status"], "failed")
        self.assertEqual(self.balance(), 5)
        second = create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        run_job(self.db, second["id"], provider_factory=lambda _: FakeProvider(invalid=True))
        self.assertEqual(get_job(self.db, second["id"], user_id=self.user_id)["error_code"], "citation_error")
        self.assertEqual(self.balance(), 5)

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all"})
    def test_member_includes_ten_reports_then_charges_three_credits(self):
        self.activate_membership()
        month = datetime.now().astimezone().strftime("%Y-%m")
        for index in range(1, 11):
            self.seed_successful_report(f"{month}-{index:02d}T09:00:00+08:00", str(index))
        before = quota_status(self.db, user_id=self.user_id)
        self.assertEqual(before["monthly_used"], 10)
        self.assertEqual(before["next_billing_mode"], "credits")
        job = create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        self.assertEqual(job["billing_mode"], "credits")
        run_job(self.db, job["id"], provider_factory=lambda _: FakeProvider())
        self.assertEqual(self.balance(), 2)

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all"})
    def test_member_daily_limit_counts_only_successful_reports(self):
        self.activate_membership()
        first = create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        run_job(self.db, first["id"], provider_factory=lambda _: FakeProvider())
        second = create_job(self.db, user=self.user, payload={"type": "industry_chain", "value": "算力租赁"}, start=False)
        run_job(self.db, second["id"], provider_factory=lambda _: FakeProvider())
        self.assertEqual(self.balance(), 5)
        quota = quota_status(self.db, user_id=self.user_id)
        self.assertEqual(quota["daily_used"], 2)
        with self.assertRaises(AuthError) as caught:
            create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        self.assertEqual(caught.exception.status, 429)

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all"})
    def test_failed_member_job_does_not_consume_quota(self):
        self.activate_membership()
        before = quota_status(self.db, user_id=self.user_id)
        job = create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        run_job(self.db, job["id"], provider_factory=lambda _: FakeProvider(fail=True), allow_provider_retry=False)
        after = quota_status(self.db, user_id=self.user_id)
        self.assertEqual(after["monthly_used"], before["monthly_used"])
        self.assertEqual(after["daily_used"], before["daily_used"])

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all"})
    def test_empty_evidence_failure_preserves_search_progress_and_usage(self):
        job = create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        run_job(self.db, job["id"], provider_factory=lambda _: FakeProvider(empty_evidence=True))
        failed = get_job(self.db, job["id"], user_id=self.user_id)
        self.assertEqual(failed["error_code"], "evidence_missing")
        self.assertEqual(failed["progress"], 8)
        self.assertEqual(failed["search_count"], 2)
        self.assertEqual(self.balance(), 5)

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all"})
    def test_admin_research_is_free(self):
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("UPDATE users SET role='admin' WHERE id=?", (self.user_id,))
            conn.commit()
        finally:
            conn.close()
        admin = {"id": self.user_id, "role": "admin"}
        job = create_job(self.db, user=admin, payload={"type": "stock", "value": "华正新材"}, start=False)
        self.assertEqual(job["billing_mode"], "admin_free")
        run_job(self.db, job["id"], provider_factory=lambda _: FakeProvider())
        self.assertEqual(self.balance(), 5)

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all"})
    def test_only_one_active_job_per_user(self):
        create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        with self.assertRaises(AuthError) as caught:
            create_job(self.db, user=self.user, payload={"type": "industry_chain", "value": "算力租赁"}, start=False)
        self.assertEqual(caught.exception.status, 409)

    @patch.dict(os.environ, {
        "STOCK_RESEARCH_ACCESS": "all",
        "STOCK_RESEARCH_PROVIDER": "doubao_deepseek",
        "ARK_API_KEY": "test-ark",
        "DEEPSEEK_API_KEY": "test-deepseek",
    })
    def test_normal_users_cannot_silently_fallback_from_luna(self):
        with self.assertRaises(AuthError) as caught:
            create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        self.assertEqual(caught.exception.status, 503)
        self.assertIn("Luna", caught.exception.message)

    @patch.dict(os.environ, {
        "STOCK_RESEARCH_ACCESS": "all",
        "STOCK_RESEARCH_PROVIDER": "luna",
        "OPENAI_API_KEY": "",
    })
    def test_missing_luna_key_fails_before_job_is_enqueued(self):
        with self.assertRaises(AuthError) as caught:
            create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=True)
        self.assertEqual(caught.exception.status, 503)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM stock_research_jobs").fetchone()[0], 0)

    @patch.dict(os.environ, {
        "STOCK_RESEARCH_ACCESS": "all",
        "STOCK_RESEARCH_PROVIDER": "auto",
        "STOCK_RESEARCH_ALLOW_AUTOMATIC_PROVIDER_SELECTION": "0",
    })
    def test_automatic_provider_selection_requires_explicit_opt_in(self):
        with self.assertRaises(AuthError) as caught:
            create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        self.assertEqual(caught.exception.status, 503)

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all"})
    def test_industry_chain_report_has_chain_rankings_and_no_stock_score(self):
        job = create_job(self.db, user=self.user, payload={"type": "industry_chain", "value": "算力租赁产业链"}, start=False)
        run_job(self.db, job["id"], provider_factory=lambda _: FakeProvider())
        done = get_job(self.db, job["id"], user_id=self.user_id)
        report = get_report(self.db, done["report_id"], user_id=self.user_id)["report"]
        self.assertNotIn("input_stock_score", report)
        self.assertTrue(report["bottleneck_ranking"])
        self.assertTrue(report["profit_capture_ranking"])

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all"})
    def test_cost_cap_stops_without_charge(self):
        job = create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        run_job(self.db, job["id"], provider_factory=lambda _: FakeProvider(cost_cny=2.01))
        failed = get_job(self.db, job["id"], user_id=self.user_id)
        self.assertEqual(failed["error_code"], "cost_limit")
        self.assertEqual(self.balance(), 5)

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all"})
    def test_concurrent_workers_claim_one_job_and_charge_once(self):
        job = create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        calls = 0
        lock = threading.Lock()

        class CountingProvider(FakeProvider):
            def evidence(inner_self, subject):
                nonlocal calls
                with lock: calls += 1
                time.sleep(0.05)
                return super().evidence(subject)

        threads = [threading.Thread(target=run_job, args=(self.db, job["id"]), kwargs={"provider_factory": lambda _: CountingProvider()}) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(calls, 1)
        self.assertEqual(self.balance(), 2)

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all"})
    def test_restart_recovery_resumes_queued_job(self):
        job = create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        with patch("trade_review_agent.stock_research.build_provider", side_effect=lambda _: FakeProvider()):
            self.assertEqual(recover_jobs(self.db), 1)
            for _ in range(40):
                if get_job(self.db, job["id"], user_id=self.user_id)["status"] == "completed":
                    break
                time.sleep(0.03)
        self.assertEqual(get_job(self.db, job["id"], user_id=self.user_id)["status"], "completed")
        self.assertEqual(self.balance(), 2)

    def test_report_rejects_trading_instruction(self):
        report = FakeProvider().judge("")
        report.update({"schema_version": 1, "subject": {"type": "stock", "name": "华正新材", "code": "603186"}, "evidence": EVIDENCE})
        report["headline"] = "建议立即买入"
        with self.assertRaisesRegex(Exception, "禁止"):
            validate_report(report)

    def test_luna_becomes_primary_only_after_all_benchmark_gates(self):
        metrics = {
            "luna": {"samples": 20, "citation_rate": 96, "completeness_rate": 99, "severe_errors": 0, "quality_score": 92, "median_cost_cny": 1.0, "p95_cost_cny": 1.8, "p95_duration_seconds": 170},
            "doubao_deepseek": {"samples": 20, "quality_score": 95},
        }
        self.assertEqual(select_production_provider_from_metrics(metrics)["provider"], "luna")
        metrics["luna"]["p95_cost_cny"] = 2.01
        self.assertEqual(select_production_provider_from_metrics(metrics)["provider"], "doubao_deepseek")


if __name__ == "__main__":
    unittest.main()
