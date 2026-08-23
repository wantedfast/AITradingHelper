from __future__ import annotations

import os
import copy
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from trade_review_agent.auth_system import AuthError, init_auth_db
from trade_review_agent.stock_research import (
    build_judge_prompt,
    build_role_prompt,
    create_job,
    _provider_urlopen,
    finalize_report,
    get_job,
    get_report,
    init_schema,
    list_reports,
    load_stock_research_skill,
    merge_supplement_sources,
    normalize_sources,
    normalize_role_output_for_contract,
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
        common = {
            "claims": [{"claim": "可验证结论", "evidence_ids": ["E001"], "confidence": "high"}],
            "challenges": [{"target": "previous_role", "issue": "检查上一角色假设", "resolution": "保留并降级未验证部分", "evidence_ids": ["E001"]}],
            "evidence_gaps": [],
        }
        if role == "capital_logic":
            return {**common, "stock": self.subject.get("name", "华正新材"), "speculation_logic": "需求催化",
                    "trigger_event": "行业需求改善", "core_driver": "国产替代", "emotion_strength": "medium",
                    "evidence_confidence": "high", "current_catalysts": [{"event": "需求改善", "type": "trend", "evidence_ids": ["E001"]}]}
        if role == "product_path":
            return {**common, "stock": self.subject.get("name", "华正新材"), "real_product_line": "覆铜板",
                    "final_product": "AI服务器", "product_path": [
                        {"node": "华正新材", "node_type": "stock", "evidence_ids": ["E001"]},
                        {"node": "覆铜板", "node_type": "material", "evidence_ids": ["E001"]},
                        {"node": "PCB", "node_type": "component", "evidence_ids": ["E001"]},
                        {"node": "AI服务器", "node_type": "final_demand", "evidence_ids": ["E002"]},
                    ], "exposure_judgment": "core", "evidence_confidence": "medium"}
        if role == "bom":
            return {**common, "final_product": "AI服务器",
                    "bom_tree": {"name": "AI服务器", "children": [{"name": "PCB", "node_type": "component", "evidence_ids": ["E001"]}]},
                    "bom_table": [{"node": "覆铜板", "chain_position": "upstream", "a_share_companies": [{"name": "生益科技", "code": "600183"}],
                                   "value_trend": "需求改善", "evidence_confidence": "medium", "evidence_ids": ["E001"]}]}
        if role == "bottleneck":
            return {**common, "current_bottleneck": "高端材料认证", "bottleneck_type": "structural",
                    "first_price_response": "认证材料", "expansion_difficulty": "客户认证周期长",
                    "profit_realization": "验证后可能扩张", "next_bottleneck": "良率",
                    "a_share_mapping": [{"node": "高端覆铜板", "companies": [{"name": "生益科技", "code": "600183"}],
                                         "reason": "认证积累", "evidence_ids": ["E001"]}], "evidence_confidence": "medium"}
        return {**common, "ranked_nodes": [{"node": "高端覆铜板", "stars": 4, "classification": "strong_beneficiary",
                                            "first_price_increase": "认证产品", "supply_tightness": "中等", "pricing_power": "较强",
                                            "profit_elasticity": "较高", "a_share_companies": [{"name": "生益科技", "code": "600183"}],
                                            "evidence_ids": ["E001"]}], "first_tightening": "认证材料",
                "first_price_increase": "高端覆铜板", "pricing_power": "头部供应商",
                "highest_earnings_elasticity": "高端材料", "margin_squeezed_nodes": ["通用加工"]}

    def judge(self, prompt):
        section = lambda summary: {"summary": summary, "evidence_ids": ["E001"]}
        report = {
            "headline": "产业需求存在，但利润只集中在高壁垒环节",
            "capital_logic": section("资金围绕需求催化交易"),
            "product_path": {**section("产品进入关键部件"), "path": ["华正新材", "覆铜板", "PCB", "AI服务器"], "exposure_judgment": "core"},
            "bom": {**section("材料、设备、封装与测试"), "tree": {"name": "AI服务器"}, "items": [{"node": "覆铜板", "evidence_ids": ["E001"]}]},
            "bottleneck": {**section("认证周期是当前瓶颈"), "current": "认证", "type": "structural"},
            "profit_flow": {**section("利润集中在有认证壁垒的供应商"), "ranked_nodes": [{"node": "覆铜板", "stars": 4, "evidence_ids": ["E001"]}]},
            "positioning": {**section("具备产品卡位"), "label": "产业龙头"},
            "input_stock_score": {"barrier": 8, "profit": 7, "growth": 6, "core_score": 7.1, "evidence_ids": ["E001"]},
            "same_chain_core_asset_ranking": [{"name": "生益科技", "code": "600183", "position": "产业龙头", "reason": "壁垒较高",
                                                "barrier": 9, "profit": 8, "growth": 7, "core_score": 8.1, "evidence_ids": ["E001"]}],
            "bottleneck_ranking": [{"name": "认证环节", "reason": "扩产周期长", "evidence_ids": ["E001"]}],
            "profit_capture_ranking": [{"name": "关键材料", "reason": "定价权较强", "evidence_ids": ["E001"]}],
            "judge": {**section("证据支持产业定位"), "conclusion": "核心但仍需验证",
                      "role_conflicts": [{"issue": "需求与利润不同步", "roles": ["capital_logic", "profit_flow"], "resolution": "等待验证", "evidence_ids": ["E001"]}],
                      "disconfirming_signals": ["订单未兑现"]},
        }
        if self.invalid:
            report["judge"]["evidence_ids"] = ["E999"]
        if self.subject.get("type") == "industry_chain":
            report.pop("input_stock_score", None)
        return report


class FakeSingleAgentProvider(FakeProvider):
    def __init__(self, *, semantic_pass=True):
        super().__init__()
        self.semantic_pass = semantic_pass
        self.single_calls = 0
        self.legacy_calls = 0

    def evidence(self, subject):
        self.legacy_calls += 1
        return super().evidence(subject)

    def single_agent(self, subject):
        self.single_calls += 1
        self.subject = subject
        self.usage.update({"input_tokens": 1200, "output_tokens": 600, "search_count": 8, "cost_cny": 0.42})
        report = self.judge("")
        report["schema_version"] = 2
        report["subject"] = subject
        report["evidence"] = copy.deepcopy(EVIDENCE)
        report["positioning"].update({
            "summary": "产业修复与高弹性并存", "reason": "证据支持",
        })
        report["audit"] = {
            "claim_evidence_checks": [{
                "claim": "关键结论", "evidence_id": "E001",
                "verdict": "supported" if self.semantic_pass else "partial",
                "reason": "公告支持" if self.semantic_pass else "只得到部分支持",
            }],
            "entity_mismatch_found": False,
            "d_tier_only_claim_found": False,
            "score_formula_checked": True,
            "unresolved_evidence_gaps": [],
        }
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

    def test_luna_provider_uses_dedicated_proxy_without_global_proxy_state(self):
        request = urllib.request.Request("https://api.openai.com/v1/responses")
        sentinel = object()
        with patch("trade_review_agent.stock_research.urllib.request.build_opener") as build:
            build.return_value.open.return_value = sentinel
            result = _provider_urlopen(request, timeout=12, proxy_url="http://172.19.0.1:7890")
        self.assertIs(result, sentinel)
        proxy_handler = build.call_args.args[0]
        self.assertEqual(proxy_handler.proxies["https"], "http://172.19.0.1:7890")
        build.return_value.open.assert_called_once_with(request, timeout=12)

    def test_supplement_evidence_accepts_provider_variant_and_reassigns_recycled_ids(self):
        variant = normalize_sources([{
            "id": "E001", "date": "2026-08-01", "item": "同链公司主营已验证",
            "source": "([cninfo](https://www.cninfo.com.cn/new/disclosure/detail))",
        }])
        self.assertEqual(len(variant), 1)
        merged = merge_supplement_sources(EVIDENCE, variant)
        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[-1]["id"], "E003")
        self.assertEqual(merged[-1]["title"], "同链公司主营已验证")

    def test_unsupported_challenge_is_downgraded_to_evidence_gap(self):
        result = {
            "challenges": [
                {"target": "market", "issue": "已验证冲突", "resolution": "降级", "evidence_ids": ["E001"]},
                {"target": "market", "issue": "缺少价格数据", "resolution": "待验证", "evidence_ids": []},
            ],
            "evidence_gaps": [],
        }
        normalized = normalize_role_output_for_contract(result, EVIDENCE)
        self.assertEqual(len(normalized["challenges"]), 1)
        self.assertEqual(normalized["evidence_gaps"], ["缺少价格数据"])

    def test_backend_freezes_weighted_core_score_instead_of_trusting_model_arithmetic(self):
        provider = FakeProvider()
        raw = provider.judge("")
        raw["input_stock_score"]["core_score"] = 99
        report = finalize_report(
            raw,
            normalize_subject({"type": "stock", "value": "华正新材"}, allow_fetch=False),
            {},
            {},
            EVIDENCE,
            "luna",
            provider.usage,
        )
        self.assertEqual(report["input_stock_score"]["core_score"], 7.1)
        validate_report(report)

    def test_role_prompts_preserve_skill_specific_contracts_and_challenge_chain(self):
        subject = {"type": "stock", "name": "华正新材", "code": "603186"}
        board = {"product_paths": [], "bom_tree": {}, "bottlenecks": [], "profit_flow": []}
        expected = {
            "capital_logic": ("current_catalysts", "Capital Logic Analyst"),
            "product_path": ("real_product_line", "Product Path Mapper"),
            "bom": ("bom_table", "BOM Chain Analyst"),
            "bottleneck": ("next_bottleneck", "Bottleneck Analyst"),
            "profit_flow": ("ranked_nodes", "Profit Flow Analyst"),
        }
        prompts = {role: build_role_prompt(role, subject, board, {}, EVIDENCE) for role in expected}
        for role, markers in expected.items():
            for marker in markers:
                self.assertIn(marker, prompts[role])
        self.assertNotEqual(prompts["bom"], prompts["profit_flow"])
        judge = build_judge_prompt(subject, board, {}, EVIDENCE)
        self.assertIn("same_chain_core_asset_ranking", judge)
        self.assertIn("bottleneck_ranking", judge)
        self.assertIn("profit_capture_ranking", judge)
        self.assertIn("Same-Chain Core Asset Ranking", judge)

    def test_prompts_embed_the_versioned_canonical_skill_files(self):
        bundle = load_stock_research_skill()
        self.assertIn("# Stock Reverse Engineering", bundle.skill_markdown)
        self.assertIn("# Multi-Agent Protocol", bundle.protocol_markdown)
        self.assertEqual(len(bundle.version), 64)
        prompt = build_role_prompt(
            "bom",
            {"type": "stock", "name": "华正新材", "code": "603186"},
            {"product_paths": [], "bom_tree": {}, "bottlenecks": [], "profit_flow": []},
            {},
            EVIDENCE,
            skill_bundle=bundle,
        )
        self.assertIn(bundle.skill_markdown, prompt)
        self.assertIn(bundle.protocol_markdown, prompt)

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all"})
    def test_complete_six_role_report_charges_three_once(self):
        job = create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        run_job(self.db, job["id"], provider_factory=lambda _: FakeProvider())
        done = get_job(self.db, job["id"], user_id=self.user_id)
        self.assertEqual(done["status"], "completed")
        self.assertEqual(self.balance(), 2)
        report = get_report(self.db, done["report_id"], user_id=self.user_id)["report"]
        self.assertEqual(set(report["role_outputs"]), {"capital_logic", "product_path", "bom", "bottleneck", "profit_flow"})
        self.assertEqual(report["input_stock_score"]["core_score"], 7.1)
        self.assertEqual(report["schema_version"], 2)
        self.assertTrue(report["research_board"]["product_paths"])
        self.assertTrue(report["research_board"]["bom_tree"])
        self.assertTrue(report["research_board"]["bottlenecks"])
        self.assertTrue(report["research_board"]["profit_flow"])
        self.assertEqual(report["meta"]["skill_version"], load_stock_research_skill().version)
        run_job(self.db, job["id"], provider_factory=lambda _: FakeProvider())
        self.assertEqual(self.balance(), 2)
        self.assertEqual(len(list_reports(self.db, user_id=self.user_id)), 1)

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all", "STOCK_RESEARCH_LUNA_SINGLE_AGENT": "1"})
    def test_luna_single_agent_is_the_default_production_path(self):
        provider = FakeSingleAgentProvider()
        job = create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        run_job(self.db, job["id"], provider_factory=lambda _: provider)
        done = get_job(self.db, job["id"], user_id=self.user_id)
        self.assertEqual(done["status"], "completed")
        self.assertEqual(provider.single_calls, 1)
        self.assertEqual(provider.legacy_calls, 0)
        self.assertEqual(self.balance(), 2)
        record = get_report(self.db, done["report_id"], user_id=self.user_id)
        self.assertEqual(record["schema_version"], 2)
        self.assertEqual(record["report"]["meta"]["execution_mode"], "single_agent")
        self.assertEqual(record["report"]["research_board"]["execution_mode"], "luna_single_agent")

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all", "STOCK_RESEARCH_LUNA_SINGLE_AGENT": "1"})
    def test_single_agent_semantic_gate_fails_without_charging(self):
        provider = FakeSingleAgentProvider(semantic_pass=False)
        job = create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        run_job(self.db, job["id"], provider_factory=lambda _: provider, allow_provider_retry=False)
        done = get_job(self.db, job["id"], user_id=self.user_id)
        self.assertEqual(done["status"], "failed")
        self.assertEqual(done["error_code"], "citation_semantic_error")
        self.assertEqual(done["input_tokens"], 1200)
        self.assertEqual(done["output_tokens"], 600)
        self.assertEqual(done["search_count"], 8)
        self.assertAlmostEqual(done["cost_cny"], 0.42)
        self.assertEqual(self.balance(), 5)

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all"})
    def test_capital_logic_and_product_path_start_in_parallel(self):
        class ParallelProvider(FakeProvider):
            def __init__(inner_self):
                super().__init__()
                inner_self.started = set()
                inner_self.lock = threading.Lock()
                inner_self.both_started = threading.Event()

            def role(inner_self, role, prompt):
                if role in {"capital_logic", "product_path"}:
                    with inner_self.lock:
                        inner_self.started.add(role)
                        if len(inner_self.started) == 2:
                            inner_self.both_started.set()
                    if not inner_self.both_started.wait(1):
                        raise RuntimeError("initial roles were serialized")
                return super().role(role, prompt)

        provider = ParallelProvider()
        job = create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        run_job(self.db, job["id"], provider_factory=lambda _: provider)
        self.assertEqual(get_job(self.db, job["id"], user_id=self.user_id)["status"], "completed")
        self.assertEqual(provider.started, {"capital_logic", "product_path"})

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all", "STOCK_RESEARCH_CROSS_EXAMINATION": "1"})
    def test_cross_examination_revises_challenged_roles_and_reruns_downstream(self):
        class ChallengingProvider(FakeProvider):
            def __init__(inner_self):
                super().__init__()
                inner_self.calls = {}
                inner_self.outputs = {}
                inner_self.review_calls = 0

            def role(inner_self, role, prompt):
                inner_self.calls[role] = inner_self.calls.get(role, 0) + 1
                result = super().role(role, prompt)
                inner_self.outputs[role] = result
                return result

            def review_roles(inner_self, prompt):
                inner_self.review_calls += 1
                revised = copy.deepcopy(inner_self.outputs)
                if inner_self.review_calls == 1:
                    revised["bom"]["claims"][0]["evidence_ids"] = []
                return {"revised_roles": revised, "conflicts": [{"issue": "产品暴露与资金标签需统一", "roles": ["capital_logic", "product_path"], "resolution": "按公告口径修订", "evidence_ids": ["E001"]}]}

        provider = ChallengingProvider()
        job = create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        run_job(self.db, job["id"], provider_factory=lambda _: provider)
        done = get_job(self.db, job["id"], user_id=self.user_id)
        self.assertEqual(done["status"], "completed")
        report = get_report(self.db, done["report_id"], user_id=self.user_id)["report"]
        self.assertEqual(provider.review_calls, 2)
        self.assertEqual(report["research_board"]["revision_log"], [{"stage": "initial_cross_examination", "reviewed_roles": ["capital_logic", "product_path", "bom", "bottleneck", "profit_flow"], "conflict_count": 1}])
        self.assertEqual(report["research_board"]["conflicts"][0]["resolution"], "按公告口径修订")
        self.assertEqual(report["research_board"]["contract_repairs"], [{"role": "cross_examination", "stage": "initial_cross_examination", "reason": "citation_error"}])
        self.assertEqual(provider.calls, {"capital_logic": 1, "product_path": 1, "bom": 1, "bottleneck": 1, "profit_flow": 1})

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all"})
    def test_supplemental_evidence_reruns_roles_that_reported_gaps(self):
        class GapProvider(FakeProvider):
            def __init__(inner_self):
                super().__init__()
                inner_self.capital_calls = 0
                inner_self.outputs = {}
                inner_self.review_calls = 0

            def role(inner_self, role, prompt):
                result = super().role(role, prompt)
                if role == "capital_logic":
                    inner_self.capital_calls += 1
                    if inner_self.capital_calls == 1:
                        result["evidence_gaps"] = ["缺少最新订单验证"]
                inner_self.outputs[role] = result
                return result

            def review_roles(inner_self, prompt):
                inner_self.review_calls += 1
                return {"revised_roles": inner_self.outputs, "conflicts": []}

            def supplement(inner_self, subject, gaps):
                return {"facts": [{"topic": "订单", "fact": "补充验证", "evidence_ids": ["E001"]}], "evidence": [{"id": "E001", "title": "补充公告", "url": "https://example.com/supplement", "publisher": "交易所", "source_tier": "A", "excerpt": "订单说明"}]}

        provider = GapProvider()
        job = create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        run_job(self.db, job["id"], provider_factory=lambda _: provider)
        done = get_job(self.db, job["id"], user_id=self.user_id)
        self.assertEqual(done["status"], "completed")
        report = get_report(self.db, done["report_id"], user_id=self.user_id)["report"]
        self.assertEqual(report["research_board"]["supplement_refreshed_roles"], ["capital_logic", "product_path", "bom", "bottleneck", "profit_flow"])
        self.assertEqual(provider.review_calls, 2)
        self.assertEqual(provider.capital_calls, 1)

    @patch.dict(os.environ, {"STOCK_RESEARCH_ACCESS": "all"})
    def test_invalid_role_citation_gets_one_same_provider_contract_repair(self):
        class RepairProvider(FakeProvider):
            def __init__(inner_self):
                super().__init__()
                inner_self.capital_calls = 0

            def role(inner_self, role, prompt):
                if role == "capital_logic":
                    inner_self.capital_calls += 1
                    if inner_self.capital_calls == 1:
                        result = super().role(role, prompt)
                        result["claims"][0]["evidence_ids"] = ["E999"]
                        return result
                return super().role(role, prompt)

        provider = RepairProvider()
        job = create_job(self.db, user=self.user, payload={"type": "stock", "value": "华正新材"}, start=False)
        run_job(self.db, job["id"], provider_factory=lambda _: provider)
        done = get_job(self.db, job["id"], user_id=self.user_id)
        self.assertEqual(done["status"], "completed")
        self.assertEqual(provider.capital_calls, 2)
        report = get_report(self.db, done["report_id"], user_id=self.user_id)["report"]
        self.assertEqual(report["research_board"]["contract_repairs"], [{"role": "capital_logic", "reason": "citation_error"}])

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

    def test_stock_report_rejects_self_only_same_chain_ranking_or_missing_chain_tables(self):
        provider = FakeProvider()
        report = finalize_report(
            provider.judge(""), normalize_subject({"type": "stock", "value": "华正新材"}, allow_fetch=False),
            {}, {}, EVIDENCE, "luna", provider.usage,
        )
        report["same_chain_core_asset_ranking"] = [{
            "name": "华正新材", "code": "603186", "barrier": 7, "profit": 6, "growth": 6,
            "core_score": 6.4, "reason": "仅输入对象", "evidence_ids": ["E001"],
        }]
        with self.assertRaisesRegex(Exception, "不得重复输入股票"):
            validate_report(report)
        report = finalize_report(
            provider.judge(""), normalize_subject({"type": "stock", "value": "华正新材"}, allow_fetch=False),
            {}, {}, EVIDENCE, "luna", provider.usage,
        )
        report["bottleneck_ranking"] = []
        with self.assertRaisesRegex(Exception, "瓶颈榜"):
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
