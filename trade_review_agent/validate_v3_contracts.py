from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable


SOURCE_TYPES = {"llm", "real_data", "fallback", "hardcode", "missing"}
TOP_LEVEL_LAYERS = {
    "ai_final_answer": dict,
    "answer_evidence": dict,
    "research_layers": dict,
    "source_trace": dict,
}
FINAL_ANSWER_FIELDS = {
    "score",
    "verdict",
    "better_choice",
    "main_reason",
    "mistake_source",
    "next_action",
}
ANSWER_EVIDENCE_FIELDS = {
    "why_stock_moved": dict,
    "investment_thesis": dict,
    "better_candidates": list,
    "mistake_diagnosis": dict,
    "future_rules": list,
}
RESEARCH_LAYER_FIELDS = {
    "market_scout": dict,
    "wang_industry": dict,
    "public_equity": dict,
    "trade_execution": dict,
}
TRACE_REQUIRED_PATHS = {
    *(f"ai_final_answer.{field}" for field in FINAL_ANSWER_FIELDS),
    "answer_evidence.why_stock_moved",
    "answer_evidence.investment_thesis",
    "answer_evidence.better_candidates",
    "answer_evidence.mistake_diagnosis",
    "answer_evidence.future_rules",
    "research_layers.market_scout",
    "research_layers.wang_industry",
    "research_layers.public_equity",
    "research_layers.trade_execution",
}
PROTECTED_CONCLUSION_NAMES = {
    "ai_final_answer",
    "score",
    "verdict",
    "better_choice",
    "main_reason",
    "mistake_source",
    "next_action",
    "profit_flow",
    "moat_radar",
    "logic_tree",
    "peer_ranking",
    "valuation_odds",
    "industry_rating",
    "investment_rating",
}
MISSING_STRINGS = {
    "",
    "missing",
    "pending",
    "pending verification",
    "待验证",
    "等待验证",
    "待补充",
}


@dataclass(frozen=True)
class ContractIssue:
    code: str
    location: str
    message: str

    def render(self) -> str:
        return f"[{self.code}] {self.location}: {self.message}"


def validate_v3_payload(payload: Any, *, label: str = "payload") -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    if not isinstance(payload, dict):
        return [ContractIssue("V3-TOP-001", label, "top-level value must be an object")]

    for key, expected_type in TOP_LEVEL_LAYERS.items():
        value = payload.get(key)
        if key not in payload:
            issues.append(ContractIssue("V3-TOP-002", f"{label}.{key}", "required layer is missing"))
        elif not isinstance(value, expected_type):
            issues.append(
                ContractIssue(
                    "V3-TOP-003",
                    f"{label}.{key}",
                    f"must be {expected_type.__name__}, got {type(value).__name__}",
                )
            )

    final_answer = payload.get("ai_final_answer")
    if isinstance(final_answer, dict):
        issues.extend(_check_required_fields(final_answer, FINAL_ANSWER_FIELDS, f"{label}.ai_final_answer"))

    evidence = payload.get("answer_evidence")
    if isinstance(evidence, dict):
        issues.extend(_check_typed_fields(evidence, ANSWER_EVIDENCE_FIELDS, f"{label}.answer_evidence"))

    layers = payload.get("research_layers")
    if isinstance(layers, dict):
        issues.extend(_check_typed_fields(layers, RESEARCH_LAYER_FIELDS, f"{label}.research_layers"))

    trace = payload.get("source_trace")
    if isinstance(trace, dict):
        issues.extend(_validate_source_trace(trace, label=label))
        issues.extend(_validate_trace_coverage(payload, trace, label=label))
        issues.extend(_validate_missing_semantics(payload, trace, label=label))
        issues.extend(_validate_provenance_semantics(payload, trace, label=label))

    issues.extend(_validate_forbidden_defaults(payload, label=label))
    return issues


def validate_presenter_projection(
    upstream: Any,
    presenter: Any,
    *,
    upstream_label: str = "payload",
    presenter_label: str = "presenter",
) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    if not isinstance(upstream, dict) or not isinstance(presenter, dict):
        return [
            ContractIssue(
                "V3-PRES-001",
                presenter_label,
                "upstream and presenter payloads must both be objects",
            )
        ]

    for path in _protected_leaf_paths(presenter):
        presenter_value = _get_path(presenter, path)
        upstream_value = _get_path(upstream, path)
        if _is_missing_value(presenter_value):
            continue
        if upstream_value != presenter_value:
            issues.append(
                ContractIssue(
                    "V3-PRES-002",
                    f"{presenter_label}.{path}",
                    "Presenter introduced or changed a protected conclusion; it may only copy upstream values",
                )
            )

    upstream_trace = upstream.get("source_trace")
    presenter_trace = presenter.get("source_trace")
    if isinstance(upstream_trace, dict) and isinstance(presenter_trace, dict):
        for path, entry in presenter_trace.items():
            if path in upstream_trace and entry != upstream_trace[path]:
                issues.append(
                    ContractIssue(
                        "V3-PRES-003",
                        f"{presenter_label}.source_trace.{path}",
                        "Presenter changed source provenance",
                    )
                )
    return issues


def audit_source_tree(source_root: Path) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    for relative in (
        Path("trade_review_agent/workbench_schema.py"),
        Path("trade_review_agent/workbench_composer.py"),
        Path("trade_review_agent/presenter_agent.py"),
        Path("trade_review_agent/workbench_report_renderer.py"),
    ):
        path = source_root / relative
        if not path.exists():
            issues.append(ContractIssue("V3-SRC-001", str(path), "required production module not found"))
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            issues.append(ContractIssue("V3-SRC-002", str(path), f"cannot parse module: {exc}"))
            continue
        issues.extend(_audit_module_ast(tree, relative))
    return issues


def _audit_module_ast(tree: ast.AST, relative: Path) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    is_presenter = relative.name == "presenter_agent.py"
    payload_builder_functions = {
        "build_presenter_fallback_data",
        "_merge_presenter_data",
        "_normalize_presenter_data",
        "_expression_layer",
        "_profit_items",
        "_logic_tree",
        "_moat_items",
        "_moat_dimensions",
    }
    owner_by_node: dict[int, str] = {}
    if is_presenter:
        for function in (item for item in ast.walk(tree) if isinstance(item, ast.FunctionDef)):
            for child in ast.walk(function):
                owner_by_node[id(child)] = function.name
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            literal_args = [_literal_value(arg) for arg in node.args]
            if any(value == "B" for value in literal_args):
                issues.append(
                    _source_issue(
                        "V3-SRC-010",
                        relative,
                        node,
                        "default rating B is forbidden; use missing/pending verification",
                    )
                )
            if any(_is_numeric_50(value) for value in literal_args) and _call_name(node.func) in {
                "_first",
                "_num",
                "get",
                "setdefault",
            }:
                issues.append(
                    _source_issue(
                        "V3-SRC-011",
                        relative,
                        node,
                        "default score 50 is forbidden; preserve null/missing",
                    )
                )

        if is_presenter and isinstance(node, (ast.Assign, ast.AnnAssign)):
            names = set(_assignment_names(node))
            protected = names & PROTECTED_CONCLUSION_NAMES
            if protected and _assignment_synthesizes_value(node):
                issues.append(
                    _source_issue(
                        "V3-PRES-010",
                        relative,
                        node,
                        "Presenter synthesizes protected conclusion field(s): "
                        + ", ".join(sorted(protected)),
                    )
                )

        if (
            is_presenter
            and isinstance(node, ast.Dict)
            and owner_by_node.get(id(node)) in payload_builder_functions
        ):
            for key_node, value_node in zip(node.keys, node.values):
                key = _literal_value(key_node) if key_node is not None else None
                if key in PROTECTED_CONCLUSION_NAMES and not _is_passthrough_expression(value_node):
                    issues.append(
                        _source_issue(
                            "V3-PRES-012",
                            relative,
                            value_node,
                            f"Presenter constructs protected conclusion field: {key}",
                        )
                    )

        if is_presenter and isinstance(node, ast.FunctionDef) and node.name in {
            "_profit_items",
            "_logic_tree",
            "_moat_items",
            "_moat_dimensions",
            "_expression_layer",
        }:
            if _function_contains_fabricating_fallback(node):
                issues.append(
                    _source_issue(
                        "V3-PRES-011",
                        relative,
                        node,
                        f"{node.name} contains a deterministic fallback for research conclusions",
                    )
                )
    return _dedupe_issues(issues)


def _validate_source_trace(trace: dict[str, Any], *, label: str) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    for path, entry in trace.items():
        location = f"{label}.source_trace.{path}"
        if not isinstance(entry, dict):
            issues.append(ContractIssue("V3-TRACE-001", location, "trace entry must be an object"))
            continue
        source = entry.get("source")
        if source not in SOURCE_TYPES:
            issues.append(
                ContractIssue(
                    "V3-TRACE-002",
                    location,
                    f"source must be one of {sorted(SOURCE_TYPES)}, got {source!r}",
                )
            )
    return issues


def _validate_trace_coverage(
    payload: dict[str, Any],
    trace: dict[str, Any],
    *,
    label: str,
) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    expected = set(TRACE_REQUIRED_PATHS)
    expected.update(_research_leaf_paths(payload.get("research_layers")))
    for path in sorted(expected):
        if path not in trace:
            issues.append(
                ContractIssue(
                    "V3-TRACE-003",
                    f"{label}.source_trace",
                    f"missing provenance entry for {path}",
                )
            )
    return issues


def _validate_missing_semantics(
    payload: dict[str, Any],
    trace: dict[str, Any],
    *,
    label: str,
) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    for path, entry in trace.items():
        if not isinstance(entry, dict):
            continue
        value = _get_path(payload, path)
        source = entry.get("source")
        if source == "missing" and not _is_missing_value(value):
            issues.append(
                ContractIssue(
                    "V3-MISS-001",
                    f"{label}.{path}",
                    "source is missing but field contains a concrete-looking value",
                )
            )
        if source in {"llm", "real_data"} and _is_missing_value(value):
            issues.append(
                ContractIssue(
                    "V3-MISS-002",
                    f"{label}.{path}",
                    f"source is {source} but value is missing",
                )
            )
    return issues


def _validate_provenance_semantics(
    payload: dict[str, Any],
    trace: dict[str, Any],
    *,
    label: str,
) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    layers = payload.get("research_layers")
    layers = layers if isinstance(layers, dict) else {}
    public = layers.get("public_equity")
    public = public if isinstance(public, dict) else {}
    sufficiency = public.get("data_sufficiency")
    sufficiency = sufficiency if isinstance(sufficiency, dict) else {}

    protected_inputs = {
        "investment_rating": ("financials", "valuation"),
        "financial_validation": ("financials",),
        "valuation_odds": ("valuation",),
        "expectation_gap.gap_score": ("consensus",),
    }
    for relative_path, required_inputs in protected_inputs.items():
        if not sufficiency or all(bool(sufficiency.get(item)) for item in required_inputs):
            continue
        value = _get_path(public, relative_path)
        if not _is_missing_value(value):
            issues.append(
                ContractIssue(
                    "V3-SEM-001",
                    f"{label}.research_layers.public_equity.{relative_path}",
                    f"verified conclusion requires {', '.join(required_inputs)} input data",
                )
            )

    wang = layers.get("wang_industry")
    wang = wang if isinstance(wang, dict) else {}
    wang_sufficiency = wang.get("data_sufficiency")
    wang_sufficiency = wang_sufficiency if isinstance(wang_sufficiency, dict) else {}
    if wang_sufficiency:
        profit_flow = wang.get("profit_flow")
        profit_flow = profit_flow if isinstance(profit_flow, dict) else {}
        if not bool(wang_sufficiency.get("profit_pool")):
            for index, item in enumerate(profit_flow.get("items") or []):
                if isinstance(item, dict) and not _is_missing_value(item.get("share_pct")):
                    issues.append(
                        ContractIssue(
                            "V3-SEM-006",
                            f"{label}.research_layers.wang_industry.profit_flow.items.{index}.share_pct",
                            "profit share requires structured profit-pool input data",
                        )
                    )
        moat = wang.get("moat_radar")
        moat = moat if isinstance(moat, dict) else {}
        if not bool(wang_sufficiency.get("peer_moat_samples")):
            for field in ("company_score", "industry_average"):
                if not _is_missing_value(moat.get(field)):
                    issues.append(
                        ContractIssue(
                            "V3-SEM-007",
                            f"{label}.research_layers.wang_industry.moat_radar.{field}",
                            "moat score requires structured peer moat samples",
                        )
                    )
            for index, dimension in enumerate(moat.get("dimensions") or []):
                if not isinstance(dimension, dict):
                    continue
                for field in ("company", "average"):
                    if not _is_missing_value(dimension.get(field)):
                        issues.append(
                            ContractIssue(
                                "V3-SEM-007",
                                f"{label}.research_layers.wang_industry.moat_radar.dimensions.{index}.{field}",
                                "moat dimension score requires structured peer moat samples",
                            )
                        )
        if not bool(wang_sufficiency.get("probability_calibration")):
            for index, node in enumerate(wang.get("logic_tree") or []):
                if isinstance(node, dict) and not _is_missing_value(node.get("certainty_pct")):
                    issues.append(
                        ContractIssue(
                            "V3-SEM-008",
                            f"{label}.research_layers.wang_industry.logic_tree.{index}.certainty_pct",
                            "certainty percentage requires calibrated probability input",
                        )
                    )
        if (
            not bool(wang_sufficiency.get("peer_metrics"))
            and not _is_missing_value(wang.get("peer_ranking"))
        ):
            issues.append(
                ContractIssue(
                    "V3-SEM-009",
                    f"{label}.research_layers.wang_industry.peer_ranking",
                    "peer ranking requires structured peer metrics",
                )
            )

    execution = layers.get("trade_execution")
    execution = execution if isinstance(execution, dict) else {}
    execution_prefix = "research_layers.trade_execution"
    for relative_path, value in _walk_leaves(execution):
        if _is_missing_value(value) or not _is_execution_judgment_path(relative_path):
            continue
        full_path = f"{execution_prefix}.{relative_path}"
        if _trace_source(trace.get(full_path)) == "real_data":
            issues.append(
                ContractIssue(
                    "V3-SEM-002",
                    f"{label}.{full_path}",
                    "execution judgment/rule output cannot be labeled real_data",
                )
            )

    execution_layer_source = _trace_source(trace.get(execution_prefix))
    execution_leaf_sources = {
        _trace_source(entry)
        for path, entry in trace.items()
        if path.startswith(f"{execution_prefix}.") and isinstance(entry, dict)
    }
    if execution_layer_source == "real_data" and (
        any(_is_execution_judgment_path(path) for path, _value in _walk_leaves(execution))
        or any(source not in {None, "real_data", "missing"} for source in execution_leaf_sources)
    ):
        issues.append(
            ContractIssue(
                "V3-SEM-003",
                f"{label}.{execution_prefix}",
                "mixed Trade Execution output cannot be labeled real_data at layer level",
            )
        )

    market = layers.get("market_scout")
    market = market if isinstance(market, dict) else {}
    for field in ("market_catalyst", "industry_news"):
        path = f"research_layers.market_scout.{field}"
        if _trace_source(trace.get(path)) == "real_data" and not _fact_rows_have_sources(market.get(field)):
            issues.append(
                ContractIssue(
                    "V3-SEM-004",
                    f"{label}.{path}",
                    "real_data fact rows require explicit non-missing sources",
                )
            )
    sector_path = "research_layers.market_scout.sector_strength"
    sector = market.get("sector_strength")
    if (
        _trace_source(trace.get(sector_path)) == "real_data"
        and isinstance(sector, dict)
        and _is_missing_value(sector.get("source"))
    ):
        issues.append(
            ContractIssue(
                "V3-SEM-005",
                f"{label}.{sector_path}",
                "real_data sector strength requires an explicit source",
            )
        )
    return issues


def _is_execution_judgment_path(path: str) -> bool:
    lowered = path.lower()
    markers = (
        "advice",
        "analysis",
        "grade",
        "judgment",
        "lesson",
        "note",
        "rating",
        "recommendation",
        "rule",
        "score",
        "verdict",
    )
    return any(marker in lowered for marker in markers)


def _fact_rows_have_sources(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if not isinstance(item, dict) or _is_missing_value(item.get("source")):
            return False
    return True


def _validate_forbidden_defaults(payload: dict[str, Any], *, label: str) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    trace = payload.get("source_trace") if isinstance(payload.get("source_trace"), dict) else {}
    for path, value in _walk_leaves(payload):
        leaf = path.rsplit(".", 1)[-1]
        source = _trace_source(trace.get(path))
        if leaf in {"industry_rating", "investment_rating", "quality_rating"} and value == "B":
            if source in {None, "fallback", "hardcode", "missing"}:
                issues.append(
                    ContractIssue(
                        "V3-DEFAULT-001",
                        f"{label}.{path}",
                        "default B is forbidden without an explicit llm/real_data provenance",
                    )
                )
        if leaf in {
            "score",
            "trade_score",
            "gap_score",
            "company_score",
            "industry_average",
            "certainty_pct",
            "confidence_pct",
        } and _is_numeric_50(value):
            if source in {None, "fallback", "hardcode", "missing"}:
                issues.append(
                    ContractIssue(
                        "V3-DEFAULT-002",
                        f"{label}.{path}",
                        "default 50 is forbidden without an explicit llm/real_data provenance",
                    )
                )
    return issues


def _check_required_fields(
    value: dict[str, Any],
    fields: Iterable[str],
    location: str,
) -> list[ContractIssue]:
    return [
        ContractIssue("V3-FIELD-001", f"{location}.{field}", "required field is missing")
        for field in sorted(fields)
        if field not in value
    ]


def _check_typed_fields(
    value: dict[str, Any],
    fields: dict[str, type],
    location: str,
) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    for field, expected_type in fields.items():
        if field not in value:
            issues.append(ContractIssue("V3-FIELD-001", f"{location}.{field}", "required field is missing"))
        elif not isinstance(value[field], expected_type):
            issues.append(
                ContractIssue(
                    "V3-FIELD-002",
                    f"{location}.{field}",
                    f"must be {expected_type.__name__}, got {type(value[field]).__name__}",
                )
            )
    return issues


def _research_leaf_paths(layers: Any) -> set[str]:
    if not isinstance(layers, dict):
        return set()
    paths: set[str] = set()
    for layer_name, layer in layers.items():
        base = f"research_layers.{layer_name}"
        paths.add(base)
        if isinstance(layer, dict):
            for path, _ in _walk_leaves(layer, prefix=base):
                paths.add(path)
    return paths


def _protected_leaf_paths(payload: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for path, _ in _walk_leaves(payload):
        parts = path.split(".")
        if "ai_final_answer" in parts or any(part in PROTECTED_CONCLUSION_NAMES for part in parts):
            result.add(path)
    return result


def _walk_leaves(value: Any, *, prefix: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(item, (dict, list)):
                yield from _walk_leaves(item, prefix=path)
            else:
                yield path, item
    elif isinstance(value, list):
        for index, item in enumerate(value):
            path = f"{prefix}.{index}" if prefix else str(index)
            if isinstance(item, (dict, list)):
                yield from _walk_leaves(item, prefix=path)
            else:
                yield path, item


def _get_path(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return None
            current = current[index]
        else:
            return None
    return current


def _is_missing_value(value: Any) -> bool:
    if value is None or value == [] or value == {}:
        return True
    return isinstance(value, str) and value.strip().lower() in MISSING_STRINGS


def _trace_source(entry: Any) -> str | None:
    return entry.get("source") if isinstance(entry, dict) else None


def _is_numeric_50(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) == 50.0


def _literal_value(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _assignment_names(node: ast.Assign | ast.AnnAssign) -> Iterable[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    for target in targets:
        yield from _target_names(target)


def _target_names(target: ast.AST) -> Iterable[str]:
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, ast.Subscript):
        slice_value = _literal_value(target.slice)
        if isinstance(slice_value, str):
            yield slice_value
    elif isinstance(target, (ast.Tuple, ast.List)):
        for item in target.elts:
            yield from _target_names(item)


def _assignment_synthesizes_value(node: ast.Assign | ast.AnnAssign) -> bool:
    value = node.value
    if value is None:
        return False
    if isinstance(value, (ast.Name, ast.Attribute, ast.Subscript)):
        return False
    if isinstance(value, ast.Call) and _call_name(value.func) in {"_dict", "_list", "_str_list"}:
        return False
    return True


def _is_passthrough_expression(node: ast.AST) -> bool:
    if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
        return True
    if isinstance(node, ast.Call) and _call_name(node.func) == "get":
        return len(node.args) == 1 and not node.keywords
    return False


def _function_contains_fabricating_fallback(node: ast.FunctionDef) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Return) and isinstance(child.value, (ast.List, ast.ListComp, ast.Dict)):
            return True
        if isinstance(child, ast.Constant) and (
            _is_numeric_50(child.value)
            or child.value == "B"
            or (isinstance(child.value, str) and "deterministic fallback" in child.value.lower())
        ):
            return True
    return False


def _source_issue(code: str, relative: Path, node: ast.AST, message: str) -> ContractIssue:
    return ContractIssue(code, f"{relative}:{getattr(node, 'lineno', '?')}", message)


def _dedupe_issues(issues: Iterable[ContractIssue]) -> list[ContractIssue]:
    seen: set[tuple[str, str, str]] = set()
    result = []
    for issue in issues:
        key = (issue.code, issue.location, issue.message)
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _valid_fixture() -> dict[str, Any]:
    payload = {
        "ai_final_answer": {
            "score": None,
            "verdict": "missing",
            "better_choice": "missing",
            "main_reason": "missing",
            "mistake_source": "missing",
            "next_action": "missing",
        },
        "answer_evidence": {
            "why_stock_moved": {},
            "investment_thesis": {},
            "better_candidates": [],
            "mistake_diagnosis": {},
            "future_rules": [],
        },
        "research_layers": {
            "market_scout": {},
            "wang_industry": {},
            "public_equity": {},
            "trade_execution": {},
        },
        "source_trace": {},
    }
    for path in TRACE_REQUIRED_PATHS:
        payload["source_trace"][path] = {"source": "missing"}
    return payload


def run_self_test() -> list[ContractIssue]:
    failures: list[ContractIssue] = []
    valid = _valid_fixture()
    if validate_v3_payload(valid, label="self_test.valid"):
        failures.append(ContractIssue("V3-SELF-001", "self_test.valid", "valid fixture was rejected"))

    invalid = _valid_fixture()
    invalid["ai_final_answer"]["score"] = 50
    invalid["source_trace"]["ai_final_answer.score"] = {"source": "fallback"}
    invalid["source_trace"]["ai_final_answer.verdict"] = {"source": "template"}
    invalid_issues = validate_v3_payload(invalid, label="self_test.invalid")
    codes = {issue.code for issue in invalid_issues}
    if "V3-DEFAULT-002" not in codes or "V3-TRACE-002" not in codes:
        failures.append(
            ContractIssue(
                "V3-SELF-002",
                "self_test.invalid",
                "invalid fixture did not trigger default/source-enum checks",
            )
        )

    presenter = _valid_fixture()
    presenter["ai_final_answer"]["verdict"] = "Presenter invented this"
    projection_issues = validate_presenter_projection(valid, presenter)
    if not any(issue.code == "V3-PRES-002" for issue in projection_issues):
        failures.append(
            ContractIssue(
                "V3-SELF-003",
                "self_test.presenter",
                "Presenter fabrication fixture was not rejected",
            )
        )

    semantic = _valid_fixture()
    semantic["research_layers"]["public_equity"] = {
        "investment_rating": "A",
        "data_sufficiency": {"financials": False, "valuation": False, "consensus": False},
    }
    semantic["research_layers"]["trade_execution"] = {
        "trade_execution_notes": {"buy_verdict": "good"}
    }
    semantic["research_layers"]["wang_industry"] = {
        "profit_flow": {"items": [{"share_pct": 42}]},
        "data_sufficiency": {
            "profit_pool": False,
            "peer_moat_samples": False,
            "probability_calibration": False,
            "peer_metrics": False,
        },
    }
    semantic["source_trace"].update(
        {
            "research_layers.public_equity.investment_rating": {"source": "llm"},
            "research_layers.public_equity.data_sufficiency.financials": {"source": "fallback"},
            "research_layers.public_equity.data_sufficiency.valuation": {"source": "fallback"},
            "research_layers.public_equity.data_sufficiency.consensus": {"source": "fallback"},
            "research_layers.trade_execution.trade_execution_notes.buy_verdict": {
                "source": "real_data"
            },
            "research_layers.wang_industry.profit_flow.items.0.share_pct": {
                "source": "llm"
            },
            "research_layers.wang_industry.data_sufficiency.profit_pool": {
                "source": "hardcode"
            },
            "research_layers.wang_industry.data_sufficiency.peer_moat_samples": {
                "source": "hardcode"
            },
            "research_layers.wang_industry.data_sufficiency.probability_calibration": {
                "source": "hardcode"
            },
            "research_layers.wang_industry.data_sufficiency.peer_metrics": {
                "source": "hardcode"
            },
        }
    )
    semantic_issues = _validate_provenance_semantics(
        semantic,
        semantic["source_trace"],
        label="self_test.semantic",
    )
    semantic_codes = {issue.code for issue in semantic_issues}
    if not {"V3-SEM-001", "V3-SEM-002", "V3-SEM-006"}.issubset(semantic_codes):
        failures.append(
            ContractIssue(
                "V3-SELF-005",
                "self_test.semantic",
                "semantic fixtures did not reject unsupported Public Equity or execution provenance",
            )
        )

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        module_dir = root / "trade_review_agent"
        module_dir.mkdir()
        for name in ("workbench_schema.py", "workbench_composer.py", "workbench_report_renderer.py"):
            (module_dir / name).write_text("VALUE = None\n", encoding="utf-8")
        (module_dir / "presenter_agent.py").write_text(
            "def build():\n"
            "    industry_rating = _first(None, 'B')\n"
            "    profit_flow = {'items': [{'share_pct': 50}]}\n"
            "    return profit_flow\n",
            encoding="utf-8",
        )
        source_issues = audit_source_tree(root)
        source_codes = {issue.code for issue in source_issues}
        if not {"V3-SRC-010", "V3-PRES-010"}.issubset(source_codes):
            failures.append(
                ContractIssue(
                    "V3-SELF-004",
                    "self_test.source",
                    "source guard fixture did not trigger Presenter/default checks",
                )
            )
    return failures


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate YingHang V3 contracts.")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root containing trade_review_agent/",
    )
    parser.add_argument("--payload", type=Path, help="V3 workbench JSON to validate")
    parser.add_argument(
        "--presenter-payload",
        type=Path,
        help="Presenter JSON to compare against --payload for conclusion fabrication",
    )
    parser.add_argument(
        "--skip-source-audit",
        action="store_true",
        help="validate payload only; do not scan production modules",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run validator fixtures before requested checks",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    issues: list[ContractIssue] = []

    if args.self_test:
        issues.extend(run_self_test())

    payload: Any = None
    if args.payload:
        try:
            payload = _load_json(args.payload)
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(ContractIssue("V3-IO-001", str(args.payload), f"cannot load JSON: {exc}"))
        else:
            issues.extend(validate_v3_payload(payload, label=args.payload.name))

    if args.presenter_payload:
        if payload is None:
            issues.append(
                ContractIssue(
                    "V3-PRES-004",
                    str(args.presenter_payload),
                    "--presenter-payload requires a valid --payload",
                )
            )
        else:
            try:
                presenter = _load_json(args.presenter_payload)
            except (OSError, json.JSONDecodeError) as exc:
                issues.append(
                    ContractIssue("V3-IO-001", str(args.presenter_payload), f"cannot load JSON: {exc}")
                )
            else:
                issues.extend(validate_presenter_projection(payload, presenter))

    if not args.skip_source_audit:
        issues.extend(audit_source_tree(args.source_root.resolve()))

    issues = _dedupe_issues(issues)
    if issues:
        print(f"YingHang V3 contract validation failed: {len(issues)} issue(s)")
        for issue in issues:
            print(issue.render())
        return 1

    print("YingHang V3 contract validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
