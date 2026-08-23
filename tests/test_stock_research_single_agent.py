from __future__ import annotations

import copy
import unittest

from scripts.run_stock_research_single_agent import (
    load_prompt,
    remove_redundant_dangling_evidence_ids,
    report_schema,
)


class StockResearchSingleAgentExperimentTests(unittest.TestCase):
    def test_prompt_is_self_contained_and_replaces_subject(self) -> None:
        prompt = load_prompt("华正新材", "603186")
        self.assertIn("华正新材", prompt)
        self.assertIn("603186", prompt)
        self.assertIn("资金逻辑分析", prompt)
        self.assertIn("产品路径映射", prompt)
        self.assertIn("BOM 分析", prompt)
        self.assertIn("瓶颈分析", prompt)
        self.assertIn("利润流向分析", prompt)
        self.assertIn("基金经理裁决", prompt)
        self.assertIn("Web Search", prompt)
        self.assertNotIn("{{SUBJECT}}", prompt)

    def test_strict_schema_closes_every_object(self) -> None:
        schema = report_schema()

        def walk(value: object) -> None:
            if isinstance(value, dict):
                if value.get("type") == "object":
                    self.assertIs(value.get("additionalProperties"), False)
                    self.assertEqual(set(value.get("required") or []), set((value.get("properties") or {}).keys()))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(schema)

    def test_dangling_id_is_removed_only_when_valid_evidence_remains(self) -> None:
        report = {
            "evidence": [{"id": "E001"}],
            "section": {"evidence_ids": ["E999", "E001"]},
        }
        removed = remove_redundant_dangling_evidence_ids(report)
        self.assertEqual(report["section"]["evidence_ids"], ["E001"])
        self.assertEqual(removed[0]["ids"], ["E999"])

    def test_claim_with_only_dangling_evidence_fails(self) -> None:
        report = {
            "evidence": [{"id": "E001"}],
            "section": {"evidence_ids": ["E999"]},
        }
        original = copy.deepcopy(report)
        with self.assertRaisesRegex(RuntimeError, "only dangling evidence"):
            remove_redundant_dangling_evidence_ids(report)
        self.assertEqual(report, original)

    def test_optional_ranked_item_with_only_dangling_reference_is_removed(self) -> None:
        report = {
            "evidence": [{"id": "E001"}],
            "profit_flow": {
                "ranked_nodes": [
                    {"node": "unsupported", "evidence_ids": ["E999"]},
                    {"node": "supported", "evidence_ids": ["E001"]},
                ]
            },
        }
        removed = remove_redundant_dangling_evidence_ids(report)
        self.assertEqual([item["node"] for item in report["profit_flow"]["ranked_nodes"]], ["supported"])
        self.assertEqual(removed[0]["action"], "dropped_unsupported_item")


if __name__ == "__main__":
    unittest.main()
