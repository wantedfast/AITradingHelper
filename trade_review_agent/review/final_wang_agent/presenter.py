from __future__ import annotations

import json
import re
import time
from typing import Any


SECTION_TITLES = [
    "买对了吗",
    "买点质量如何",
    "是否值得重来一次继续买",
    "如果重来一次应该如何交易",
    "属于主线还是跟风",
    "题材分析",
    "相关公司比较",
    "最终判断",
    "交易逻辑",
    "产业链位置",
    "壁垒和利润流向",
    "同行比较",
    "如果重来一次",
    "一句话结论",
]

REVIEW_ITEMS = [
    ("buyCorrect", "买对了吗"),
    ("entryQuality", "买点质量如何"),
    ("replayDecision", "如果重来一次应该如何交易"),
    ("themePosition", "属于主线还是跟风"),
]

REVIEW_ITEM_ALIASES = {
    "如果重来一次应该如何交易": ("是否值得重来一次继续买",),
}

REVIEW_SCORE_ITEMS = [
    ("tradeCorrectness", "交易正确性"),
    ("directionJudgment", "方向判断"),
    ("entryQuality", "买点质量"),
    ("targetSelection", "标的选择"),
    ("industryChainAdvantage", "产业链优势"),
    ("mainlineStrength", "主线强度"),
    ("total", "综合评分"),
]

REVIEW_JUDGMENT_ITEMS = [
    ("tradeCorrectness", "交易正确性"),
    ("entryQuality", "买点质量"),
    ("mainlinePosition", "主线地位"),
    ("improvement", "是否有值得改进的地方"),
]

TITLE_PATTERN = "|".join(re.escape(title) for title in sorted(SECTION_TITLES, key=len, reverse=True))
RANK_LABELS = {"一": 1, "二": 2, "三": 3, "1": 1, "2": 2, "3": 3}
GENERIC_CHOICE_WORDS = (
    "更高",
    "核心票",
    "龙头",
    "标的",
    "供应商",
    "公司",
    "玩家",
    "竞争对手",
    "这类",
    "板块",
    "方向",
)


def present_wang_research_result(
    raw_result: dict[str, Any],
    *,
    call_presenter: Any = None,
    presenter_cost: Any = None,
    usage_token_summary: Any,
    usd_cny: float,
    total_started: float,
) -> dict[str, Any]:
    trade = raw_result["trade"]
    answer = str(raw_result.get("answer") or "")
    sections = split_sections(answer)
    payload = map_sections_to_frontend(sections, answer, str(trade.get("stock_name") or ""))
    mapping_mode = (
        "structured_json_strict_evidence_mapping"
        if payload.get("presenter_contract") == "answer_first_v3_json_evidence"
        else "raw_markdown_strict_evidence_mapping"
    )

    doubao_cost = raw_result.get("doubao_cost") or {}
    judge_cost = raw_result.get("judge_cost") or {}
    total_cny = round(float(doubao_cost.get("cny") or 0) + float(judge_cost.get("cny") or 0), 6)
    seconds = raw_result.get("seconds") if isinstance(raw_result.get("seconds"), dict) else {}
    prompts = raw_result.get("prompts") if isinstance(raw_result.get("prompts"), dict) else {}
    doubao_response = raw_result.get("doubao_response") if isinstance(raw_result.get("doubao_response"), dict) else {}
    judge_response = raw_result.get("judge_response") if isinstance(raw_result.get("judge_response"), dict) else {}
    models = raw_result.get("models") if isinstance(raw_result.get("models"), dict) else {}
    judge_seconds = seconds.get("judge")
    judge_model = models.get("judge")
    judge_provider = models.get("judge_provider") or "deepseek"

    payload.update(
        {
            "agent_type": "wang",
            "agent_name": "Final WANG Agent",
            "coach_answer": answer,
            "raw_markdown_files": raw_result.get("raw_markdown_files") or {},
            "doubao_search_pack": raw_result.get("search_pack") or "",
            "presenter_summary": {
                "mode": mapping_mode,
                "sections": sections,
                "display_sections": display_sections(sections),
            },
            "research_pipeline": f"final_wang_agent:{mapping_mode}",
            "doubao_search_metrics": {
                "model": models.get("doubao"),
                "seconds": seconds.get("doubao_search"),
                "tokens": usage_token_summary(doubao_response.get("usage", {})),
                "cost_cny": doubao_cost.get("cny"),
                "raw_usage": doubao_response.get("usage", {}),
            },
            "research_metrics": {
                "agent": "Final WANG Agent",
                "provider": judge_provider,
                "model": judge_model,
                "mode": mapping_mode,
                "allow_web": False,
                "seconds": round(float(seconds.get("doubao_search") or 0) + float(judge_seconds or 0), 4),
                "status": "ok",
                "api_usage": judge_response.get("usage", {}),
                "presenter_usage": {},
                "estimated_cost_cny": judge_cost.get("cny"),
                "doubao_search_seconds": seconds.get("doubao_search"),
                "doubao_search_tokens": usage_token_summary(doubao_response.get("usage", {})),
                "doubao_search_cost_cny": doubao_cost.get("cny"),
                "judge_seconds": judge_seconds,
                "presenter_seconds": 0,
            },
            "prompts": prompts,
            "cost": {
                "doubao": doubao_cost,
                "judge": judge_cost,
                "presenter": {
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "billable_input_tokens": 0,
                    "output_tokens": 0,
                    "usd": 0.0,
                    "cny": 0.0,
                },
                "total_cny": total_cny,
                "total_usd_equivalent": round(total_cny / usd_cny, 8) if usd_cny else None,
            },
            "seconds": {
                "doubao_search": seconds.get("doubao_search"),
                "judge": judge_seconds,
                "presenter": 0,
                "total": round(time.perf_counter() - total_started, 4),
            },
        }
    )
    return payload


def split_sections(answer: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current_title = ""

    for line in (answer or "").splitlines():
        heading = _parse_heading_line(line)
        if heading:
            title, inline_content = heading
            current_title = title
            bucket = sections.setdefault(title, [])
            if bucket and bucket[-1] != "":
                bucket.append("")
            if inline_content:
                bucket.append(inline_content)
            continue
        if current_title:
            sections.setdefault(current_title, []).append(line.rstrip())

    normalized = {title: "\n".join(lines).strip() for title, lines in sections.items()}
    return {title: text for title, text in normalized.items() if text}


def _parse_heading_line(line: str) -> tuple[str, str] | None:
    text = line.strip()
    if not text:
        return None

    markdown_heading = bool(re.match(r"^#{1,6}\s+", text))
    text = re.sub(r"^#{1,6}\s*", "", text).strip()
    text = text.lstrip(">").strip()
    markdown_emphasis = bool(re.match(r"^[*_`]{1,3}", text))
    text = re.sub(r"^[*_`]+", "", text).lstrip()

    match = re.match(
        rf"^(?P<num>[一二三四五六七]\s*[、.．]\s*)?(?P<title>{TITLE_PATTERN})"
        rf"(?P<question>\s*[？?]?)(?P<emphasis>[\s*_`]*)"
        rf"(?P<colon>\s*[：:]?)(?P<rest>.*)$",
        text,
    )
    if not match:
        return None

    rest = match.group("rest").strip()
    heading_markers = (
        markdown_heading
        or markdown_emphasis
        or bool(match.group("num"))
        or bool(match.group("question").strip())
        or bool(match.group("colon").strip())
        or not rest
    )
    if not heading_markers:
        return None

    rest = clean_text(rest)
    if rest.startswith(("/", "／")) or re.fullmatch(r"[？?：:，,。；;\-/\s]+", rest):
        rest = ""
    return match.group("title"), rest


def display_sections(sections: dict[str, str]) -> list[dict[str, str]]:
    rows = [{"title": title, "content": sections[title]} for title in SECTION_TITLES if sections.get(title)]
    rows.extend({"title": title, "content": content} for title, content in sections.items() if title not in SECTION_TITLES)
    return rows


def parse_structured_json_answer(answer: str) -> dict[str, Any] | None:
    text = answer.strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def build_structured_json_contract(data: dict[str, Any], answer: str, stock_name: str) -> dict[str, Any]:
    evidence_map: dict[str, dict[str, str]] = {}
    confidence: dict[str, str] = {}
    missing_fields: list[str] = []

    def record(path: str, value: Any, certainty: str = "high") -> None:
        if is_empty_value(value):
            missing_fields.append(path)
            return
        evidence_map[path] = {"sourceSection": path, "evidence": evidence_text(value)}
        confidence[path] = certainty

    final = object_at(data, "finalJudgment")
    trade_correctness = object_at(final, "tradeCorrectness")
    entry_quality = object_at(final, "entryQuality")
    mainline_position = object_at(final, "mainlinePosition")
    improvement = object_at(final, "improvement")

    verdict_text = first_text(data.get("oneLineConclusion"), final.get("summary"))
    review_verdict = {"text": verdict_text} if verdict_text else None
    record("oneLineConclusion", verdict_text)

    score_specs = [
        ("tradeCorrectness", "交易正确性", trade_correctness.get("score"), "finalJudgment.tradeCorrectness.score"),
        ("entryQuality", "买点质量", entry_quality.get("score"), "finalJudgment.entryQuality.score"),
        ("mainlineStrength", "主线强度", mainline_position.get("score"), "finalJudgment.mainlinePosition.score"),
        ("total", "综合评分", final.get("totalScore"), "finalJudgment.totalScore"),
    ]
    review_scores: list[dict[str, Any]] = []
    for key, label, value, path in score_specs:
        score = review_score(value)
        if score is None:
            missing_fields.append(path)
            continue
        review_scores.append({"key": key, "label": label, "value": score})
        record(path, value)

    judgment_specs = [
        (
            "tradeCorrectness",
            "交易正确性",
            [
                ("买对了吗", trade_correctness.get("boughtRight")),
                ("买对在哪里", trade_correctness.get("rightReasons")),
                ("买错在哪里", trade_correctness.get("wrongReasons")),
            ],
            "finalJudgment.tradeCorrectness",
            trade_correctness,
        ),
        (
            "entryQuality",
            "买点质量",
            [
                ("买点质量如何", entry_quality.get("judgment")),
                ("是否属于最佳买点", entry_quality.get("isBestEntry")),
                ("买入时机", entry_quality.get("timing")),
                ("盈亏比", entry_quality.get("riskReward")),
                ("确认性", entry_quality.get("confirmation")),
                ("是否追涨", entry_quality.get("isChasing")),
                ("更优位置", entry_quality.get("betterPosition")),
            ],
            "finalJudgment.entryQuality",
            entry_quality,
        ),
        (
            "mainlinePosition",
            "主线地位",
            [("判断", mainline_position.get("level")), ("原因", mainline_position.get("reason"))],
            "finalJudgment.mainlinePosition",
            mainline_position,
        ),
        (
            "improvement",
            "是否有值得改进的地方",
            [
                ("如果重来一次还会不会买", improvement.get("wouldBuyAgain")),
                ("是否应该换成更强标的", improvement.get("shouldSwitchStrongerTarget")),
                ("最大正确点", improvement.get("biggestCorrectPoint")),
                ("最大错误", improvement.get("biggestMistake")),
            ],
            "finalJudgment.improvement",
            improvement,
        ),
    ]
    review_judgments: list[dict[str, str]] = []
    for key, label, parts, path, raw_value in judgment_specs:
        text = join_labeled_parts(parts)
        if not text:
            missing_fields.append(path)
            continue
        summary = raw_value.get("summary") if isinstance(raw_value, dict) else None
        review_judgments.append({"key": key, "label": label, "text": text, "summary": summary})
        record(path, raw_value)

    rerun_choice = object_at(data, "rerunChoice")
    next_actions = build_next_actions_from_json(rerun_choice)
    for index, item in enumerate(next_actions):
        record(f"rerunChoice.items[{index}]", item["text"])

    company_comparison = object_at(data, "companyComparison")
    short_term_ranking = build_ranking_from_json(company_comparison.get("shortTermCapitalRanking"))
    industry_value_ranking = build_ranking_from_json(company_comparison.get("industryValueRanking"))
    ranking = short_term_ranking or build_ranking_from_json(data.get("peerComparison"))
    for index, item in enumerate(ranking):
        record(f"companyComparison.shortTermCapitalRanking[{index}]", item)
    for index, item in enumerate(industry_value_ranking):
        record(f"companyComparison.industryValueRanking[{index}]", item)
    if company_comparison:
        record("companyComparison.summary", company_comparison.get("summary"))

    first_choice = ranking[0] if ranking else None
    if first_choice:
        best_choice = {
            "available": True,
            "name": first_choice["name"],
            "summary": first_choice.get("reason"),
            "ranking": ranking,
        }
        record("bestChoice.name", first_choice["name"])
        record("bestChoice.summary", first_choice.get("reason"))
    else:
        best_choice = {"available": False, "name": None, "summary": None, "ranking": ranking}
        missing_fields.append("companyComparison.shortTermCapitalRanking")

    company_comparison_payload = {
        "shortTermCapitalRanking": ranking,
        "industryValueRanking": industry_value_ranking,
        "summary": company_comparison.get("summary") if company_comparison else None,
    }

    industry_chain_data = object_at(data, "industryChain")
    nodes = build_industry_nodes_from_json(industry_chain_data.get("nodes"), stock_name)
    chain_payload = {"nodes": nodes}
    record("industryChain.nodes", industry_chain_data.get("nodes"))

    barrier_profit = object_at(data, "barrierAndProfitFlow")
    profit_text = join_labeled_parts(
        [
            ("技术壁垒", first_text(barrier_profit.get("technologyBarrier"), barrier_profit.get("barrier"))),
            ("客户认证壁垒", barrier_profit.get("customerCertificationBarrier")),
            ("国产替代壁垒", barrier_profit.get("domesticSubstitutionBarrier")),
            ("规模壁垒", barrier_profit.get("scaleBarrier")),
            ("利润流向", barrier_profit.get("profitFlow")),
            ("利润地位", barrier_profit.get("positionType")),
            ("是否利润中心", barrier_profit.get("isProfitCenter")),
        ]
    )
    profit_payload = {"text": profit_text or None}
    record("barrierAndProfitFlow", barrier_profit)

    trade_logic_value = data.get("tradeLogic")
    if isinstance(trade_logic_value, dict):
        trade_logic_text = join_labeled_parts(
            [
                ("核心逻辑", trade_logic_value.get("coreLogic")),
                ("催化剂", trade_logic_value.get("catalyst")),
                ("业绩验证", trade_logic_value.get("performanceValidation")),
                ("资金认可", trade_logic_value.get("capitalRecognition")),
            ]
        )
        trade_logic_summary = first_text(trade_logic_value.get("summary"))
    else:
        trade_logic_text = first_text(trade_logic_value) or ""
        trade_logic_summary = None
    trade_logic_payload = {"text": trade_logic_text or None, "summary": trade_logic_summary}
    record("tradeLogic", trade_logic_value)

    if review_verdict is None:
        missing_fields.append("oneLineConclusion")
    if not review_scores:
        missing_fields.append("review.scores.items")
    if not review_judgments:
        missing_fields.append("review.judgments.items")
    if not next_actions:
        missing_fields.append("rerunChoice")
    if not nodes:
        missing_fields.append("industryChain.nodes")
    if not profit_text:
        missing_fields.append("barrierAndProfitFlow")
    if not trade_logic_text:
        missing_fields.append("tradeLogic")

    return {
        "presenter_contract": "answer_first_v3_json_evidence",
        "review": {
            "verdict": review_verdict,
            "scores": {"items": review_scores},
            "judgments": {"items": review_judgments},
            "items": [],
            "nextActions": {"items": next_actions},
        },
        "bestChoice": best_choice,
        "companyComparison": company_comparison_payload,
        "tradeLogic": trade_logic_payload,
        "themeAnalysis": {
            "industryChain": chain_payload,
            "profitFlow": profit_payload,
        },
        "audit": {
            "strict_evidence_only": True,
            "missing_fields": dedupe_keep_order(missing_fields),
            "parser_warnings": [],
            "evidence_map": evidence_map,
            "confidence": confidence,
        },
    }


def object_at(value: Any, key: str) -> dict[str, Any]:
    child = value.get(key) if isinstance(value, dict) else None
    return child if isinstance(child, dict) else {}


def is_empty_value(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def evidence_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).strip()


def first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def numeric_score(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0, min(100, round(value)))
    if isinstance(value, str):
        match = re.search(r"\d+(?:\.\d+)?", value)
        if match:
            return max(0, min(100, round(float(match.group(0)))))
    return None


def review_score(value: Any) -> float | None:
    score = numeric_score(value)
    if score is None:
        return None
    normalized = score / 10 if score > 10 else float(score)
    normalized = max(0.0, min(10.0, normalized))
    return int(normalized) if normalized.is_integer() else round(normalized, 1)


def join_labeled_parts(parts: list[tuple[str, Any]]) -> str:
    lines = []
    for label, value in parts:
        if isinstance(value, str) and value.strip():
            lines.append(f"{label}：{value.strip()}")
    return "\n".join(lines)


def build_next_actions_from_json(rerun_choice: dict[str, Any]) -> list[dict[str, str]]:
    priority = rerun_choice.get("priority")
    priority_text = ""
    if isinstance(priority, list):
        names = [str(item).strip() for item in priority if str(item).strip()]
        if names:
            priority_text = "优先级：" + " > ".join(names)
    text = join_labeled_parts(
        [
            ("短线优先买谁", rerun_choice.get("shortTermFirstChoice")),
            ("产业链优先买谁", rerun_choice.get("industryFirstChoice")),
            ("如果交易重来一次选谁", priority_text),
            ("当前标的排序", rerun_choice.get("currentStockRank")),
            ("原因", rerun_choice.get("reason")),
            ("总结", rerun_choice.get("summary")),
        ]
    )
    return [{"key": "rerunChoice", "label": "如果交易重来一次选谁", "text": text}] if text else []


def build_ranking_from_json(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    ranking: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        rank = numeric_score(item.get("rank")) or index + 1
        reason = join_labeled_parts(
            [("理由", item.get("reason")), ("弱点", item.get("weakness")), ("交易意义", item.get("tradeMeaning"))]
        )
        ranking.append({"rank": rank, "name": name, "reason": reason or None})
    return sorted(ranking, key=lambda item: item["rank"])


def build_industry_nodes_from_json(value: Any, stock_name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    nodes = []
    for item in value:
        role = None
        if isinstance(item, dict):
            label = first_text(item.get("label"), item.get("name"), item.get("title")) or ""
            role = first_text(item.get("role"), item.get("description"), item.get("summary"))
        else:
            label = str(item).strip()
        if not label:
            continue
        current_text = " ".join(part for part in (label, role or "") if part)
        nodes.append({"label": label, "role": role, "current": bool(stock_name and stock_name in current_text)})
    return nodes


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def map_sections_to_frontend(sections: dict[str, str], answer: str, stock_name: str) -> dict[str, Any]:
    structured = parse_structured_json_answer(answer)
    if structured is not None:
        return build_structured_json_contract(structured, answer, stock_name)
    return build_strict_contract(answer, sections, stock_name)


def parse_answer_first_markdown(answer: str, trade: dict[str, Any]) -> dict[str, Any]:
    return build_strict_contract(answer, split_sections(answer), str(trade.get("stock_name") or ""))


def build_answer_first_presenter(parsed: dict[str, Any], raw_result: dict[str, Any]) -> dict[str, Any]:
    return parsed


def build_strict_contract(answer: str, sections: dict[str, str], stock_name: str) -> dict[str, Any]:
    evidence_map: dict[str, dict[str, str]] = {}
    confidence: dict[str, str] = {}
    warnings: list[str] = []

    def record(path: str, source_section: str, evidence: str, certainty: str) -> None:
        evidence_map[path] = {"sourceSection": source_section, "evidence": evidence.strip()}
        confidence[path] = certainty

    verdict = extract_verdict(sections)
    review_verdict = None
    if verdict:
        text, source_section, evidence, certainty = verdict
        review_verdict = {"text": text}
        record("review.verdict.text", source_section, evidence, certainty)

    review_scores = extract_review_scores(sections)
    for index, item in enumerate(review_scores):
        record(
            f"review.scores.items[{index}].value",
            item.pop("_sourceSection"),
            item.pop("_evidence"),
            item.pop("_confidence"),
        )

    review_judgments = extract_review_judgments(sections)
    for index, item in enumerate(review_judgments):
        record(
            f"review.judgments.items[{index}].text",
            item.pop("_sourceSection"),
            item.pop("_evidence"),
            item.pop("_confidence"),
        )

    review_items: list[dict[str, str]] = []
    for key, label in REVIEW_ITEMS:
        candidate_labels = (label, *REVIEW_ITEM_ALIASES.get(label, ()))
        item = next(
            (
                extracted
                for candidate_label in candidate_labels
                if (extracted := extract_review_item(answer, sections, candidate_label))
            ),
            None,
        )
        if not item:
            continue
        text, source_section, evidence, certainty = item
        index = len(review_items)
        review_items.append({"key": key, "label": label, "text": text})
        record(f"review.items[{index}].text", source_section, evidence, certainty)

    next_actions = extract_next_actions(sections)
    for index, item in enumerate(next_actions):
        record(
            f"review.nextActions.items[{index}].text",
            item.pop("_sourceSection"),
            item.pop("_evidence"),
            item.pop("_confidence"),
        )
    next_actions_text = extract_next_actions_text(sections)
    if next_actions_text:
        record(
            "review.nextActions.text",
            next_actions_text[1],
            next_actions_text[2],
            next_actions_text[3],
        )

    ranking, ranking_warnings = extract_ranking(sections)
    warnings.extend(ranking_warnings)
    for index, item in enumerate(ranking):
        source_section = item.pop("_sourceSection")
        name_evidence = item.pop("_nameEvidence")
        summary_evidence = item.pop("_summaryEvidence", "")
        certainty = item.pop("_confidence")
        record(f"bestChoice.ranking[{index}].rank", source_section, name_evidence, certainty)
        record(f"bestChoice.ranking[{index}].name", source_section, name_evidence, certainty)
        if item.get("reason"):
            record(f"bestChoice.ranking[{index}].reason", source_section, summary_evidence, certainty)

    priority_choice = extract_priority_choice(sections)
    best_ranking = next((item for item in ranking if item["rank"] == 1), None)
    choice: dict[str, Any] | None = best_ranking
    choice_source: tuple[str, str, str] | None = None
    choice_reason_source: tuple[str, str, str] | None = None

    if best_ranking:
        ranking_audit = evidence_map.get("bestChoice.ranking[0].name")
        if ranking_audit:
            choice_source = (
                ranking_audit["sourceSection"],
                ranking_audit["evidence"],
                confidence["bestChoice.ranking[0].name"],
            )
        reason_audit = evidence_map.get("bestChoice.ranking[0].reason")
        if reason_audit:
            choice_reason_source = (
                reason_audit["sourceSection"],
                reason_audit["evidence"],
                confidence["bestChoice.ranking[0].reason"],
            )
    elif priority_choice:
        name, reason, source_section, name_evidence, reason_evidence, certainty = priority_choice
        choice = {"name": name, "reason": reason}
        choice_source = (source_section, name_evidence, certainty)
        if reason:
            choice_reason_source = (source_section, reason_evidence or name_evidence, certainty)

    if choice and choice_source:
        best_choice = {
            "available": True,
            "name": choice["name"],
            "summary": choice.get("reason"),
            "ranking": ranking,
        }
        record("bestChoice.available", *choice_source)
        record("bestChoice.name", *choice_source)
        if best_choice["summary"]:
            record("bestChoice.summary", *(choice_reason_source or choice_source))
    else:
        best_choice = {"available": False, "name": None, "summary": None, "ranking": ranking}

    industry_chain = extract_industry_chain(sections, stock_name)
    if industry_chain:
        chain_payload, source_section, evidence, certainty = industry_chain
        record("themeAnalysis.industryChain.nodes", source_section, evidence, certainty)
    else:
        chain_payload = {"nodes": []}

    profit_flow = extract_profit_flow(sections)
    if profit_flow:
        profit_text, source_section, evidence, certainty = profit_flow
        profit_payload = {"text": profit_text}
        record("themeAnalysis.profitFlow.text", source_section, evidence, certainty)
    else:
        profit_payload = {"text": None}

    trade_logic = extract_trade_logic(sections)
    if trade_logic:
        trade_logic_text, source_section, evidence, certainty = trade_logic
        trade_logic_payload = {"text": trade_logic_text, "summary": None}
        record("tradeLogic.text", source_section, evidence, certainty)
    else:
        trade_logic_payload = {"text": None, "summary": None}

    missing_fields = []
    if review_verdict is None:
        missing_fields.append("review.verdict.text")
    if not review_scores:
        missing_fields.append("review.scores.items")
    if not review_judgments:
        missing_fields.append("review.judgments.items")
    if not review_items:
        missing_fields.append("review.items")
    if not next_actions:
        missing_fields.append("review.nextActions.items")
    if not best_choice["name"]:
        missing_fields.append("bestChoice.name")
    if not best_choice["ranking"]:
        missing_fields.append("bestChoice.ranking")
    if not chain_payload["nodes"]:
        missing_fields.append("themeAnalysis.industryChain.nodes")
    if not profit_payload["text"]:
        missing_fields.append("themeAnalysis.profitFlow.text")
    if not trade_logic_payload["text"]:
        missing_fields.append("tradeLogic.text")

    if not answer.strip():
        warnings.append("raw markdown is empty")
    elif not evidence_map:
        warnings.append("no explicit supported fields found in raw markdown")

    return {
        "presenter_contract": "answer_first_v2_strict_evidence",
        "review": {
            "verdict": review_verdict,
            "scores": {"items": review_scores},
            "judgments": {"items": review_judgments},
            "items": review_items,
            "nextActions": {
                "text": next_actions_text[0] if next_actions_text else None,
                "items": next_actions,
            },
        },
        "bestChoice": best_choice,
        "tradeLogic": trade_logic_payload,
        "themeAnalysis": {
            "industryChain": chain_payload,
            "profitFlow": profit_payload,
        },
        "audit": {
            "strict_evidence_only": True,
            "missing_fields": missing_fields,
            "parser_warnings": warnings,
            "evidence_map": evidence_map,
            "confidence": confidence,
        },
    }


def extract_trade_logic(sections: dict[str, str]) -> tuple[str, str, str, str] | None:
    text = sections.get("交易逻辑", "").strip()
    if not text:
        return None
    return clean_text(text), "交易逻辑", text, "high"


def extract_verdict(sections: dict[str, str]) -> tuple[str, str, str, str] | None:
    for title in ("一句话结论", "最终判断"):
        text = sections.get(title, "").strip()
        if text:
            return clean_text(text), title, text, "high"
    return None


def extract_review_scores(sections: dict[str, str]) -> list[dict[str, Any]]:
    final_section = sections.get("最终判断", "")
    if not final_section:
        return []

    result: list[dict[str, Any]] = []
    for key, label in REVIEW_SCORE_ITEMS:
        score = find_score_line(final_section, label)
        if not score:
            continue
        value, evidence = score
        result.append(
            {
                "key": key,
                "label": label,
                "value": value,
                "_sourceSection": "最终判断",
                "_evidence": evidence,
                "_confidence": "high",
            }
        )
    return result


def find_score_line(text: str, label: str) -> tuple[float, str] | None:
    pattern = re.compile(
        rf"^[\s>*#_`\-]*{re.escape(label)}"
        rf"(?:\s*[\(（]\s*\d{{1,3}}\s*分\s*[\)）])?"
        rf"\s*[：:]\s*(?P<score>\d{{1,3}})\s*分?(?:\s*[。.]|\s*$)"
    )
    for raw_line in text.splitlines():
        normalized = clean_text(raw_line)
        match = pattern.match(normalized)
        if not match:
            continue
        value = review_score(match.group("score"))
        if value is not None:
            return value, raw_line.strip()
    return None


def extract_review_judgments(sections: dict[str, str]) -> list[dict[str, str]]:
    final_section = sections.get("最终判断", "")
    if not final_section:
        return []

    blocks = split_numbered_blocks(final_section)
    result: list[dict[str, str]] = []
    for key, label in REVIEW_JUDGMENT_ITEMS:
        block = blocks.get(label)
        if not block:
            continue
        text = clean_judgment_block(block)
        if not text:
            continue
        result.append(
            {
                "key": key,
                "label": label,
                "text": text,
                "_sourceSection": "最终判断",
                "_evidence": block,
                "_confidence": "high",
            }
        )
    return result


def split_numbered_blocks(text: str) -> dict[str, str]:
    blocks: dict[str, list[str]] = {}
    current_label = ""
    heading_pattern = re.compile(r"^[\s>*#_`\-]*(?P<num>[1-5])\s*[.、．]\s*(?P<label>交易正确性|买点质量|主线地位|是否有值得改进的地方|综合评分)\s*$")
    for raw_line in text.splitlines():
        match = heading_pattern.match(raw_line.strip())
        if match:
            current_label = match.group("label")
            blocks.setdefault(current_label, [])
            continue
        if current_label:
            blocks[current_label].append(raw_line.rstrip())
    return {label: "\n".join(lines).strip() for label, lines in blocks.items() if "".join(lines).strip()}


def clean_judgment_block(block: str) -> str:
    kept: list[str] = []
    skip_until_next_heading = False
    for raw_line in block.splitlines():
        line = clean_text(raw_line)
        if not line:
            continue
        if line in {"评分", "评分：", "评分标准", "评分标准：", "重点从以下维度判断", "重点从以下维度判断：", "判断属于", "判断属于：", "参考", "参考：", "必须回答", "必须回答：", "权重", "权重：", "输出格式", "输出格式："}:
            skip_until_next_heading = True
            continue
        if re.match(r"^(100|90|80|70|60|50|40|20|0)\s*=", line):
            continue
        if "×" in line and "%" in line:
            continue
        if re.match(r"^(交易正确性|买点质量|主线强度|综合评分)\s*[：:]\s*\d{1,3}\s*分?$", line):
            continue
        if line.startswith("是否") or line.startswith("买") or line.startswith("最大") or line.startswith("如果"):
            skip_until_next_heading = False
        if skip_until_next_heading and re.match(r"^-?\s*(是否|买|最大|如果)", line) is None:
            continue
        kept.append(line)
    return "\n".join(dict.fromkeys(kept)).strip()


def extract_review_item(
    answer: str,
    sections: dict[str, str],
    label: str,
) -> tuple[str, str, str, str] | None:
    direct = sections.get(label, "").strip()
    if direct:
        return clean_text(direct), label, direct, "high"

    inline_pattern = re.compile(
        rf"^[\s>*#_`\-]*(?:[一二三四五六七1-7]\s*[、.．]\s*)?"
        rf"[*_`]*{re.escape(label)}\s*[？?]?[*_`]*\s*[：:]?\s*(?P<value>.+)$"
    )
    block_heading_pattern = re.compile(
        rf"^[\s>*#_`\-]*(?:[一二三四五六七1-7]\s*[、.．]\s*)?"
        rf"[*_`]*{re.escape(label)}\s*[？?]?[*_`]*\s*[：:]?\s*$"
    )
    review_heading_pattern = re.compile(
        r"^[\s>*#_`\-]*(?:[一二三四五六七1-7]\s*[、.．]\s*)?"
        r"[*_`]*(?:买对了吗|买点质量如何|属于主线还是跟风|"
        r"是否值得重来一次继续买|如果重来一次应该如何交易)"
        r"\s*[？?]?[*_`]*\s*[：:]?\s*$"
    )
    lines = answer.splitlines()
    for index, raw_line in enumerate(lines):
        match = inline_pattern.match(raw_line.strip())
        if match:
            value = clean_text(match.group("value"))
            if value:
                return value, source_section_for(raw_line, sections, label), raw_line.strip(), "high"
        if not block_heading_pattern.match(raw_line.strip()):
            continue

        value_lines: list[str] = []
        evidence_lines = [raw_line.strip()]
        for following_line in lines[index + 1 :]:
            stripped = following_line.strip()
            if review_heading_pattern.match(stripped) or re.match(
                r"^(?:---+|[一二三四五六七]\s*[、.．])",
                clean_text(stripped),
            ):
                break
            if not stripped:
                if value_lines:
                    break
                continue
            cleaned = clean_text(stripped)
            if cleaned:
                value_lines.append(cleaned)
                evidence_lines.append(stripped)
        if value_lines:
            return (
                "\n".join(value_lines),
                source_section_for(raw_line, sections, label),
                "\n".join(evidence_lines),
                "high",
            )
    return None


def extract_next_actions(sections: dict[str, str]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for source_section in ("如果重来一次", "是否值得重来一次继续买"):
        text = sections.get(source_section, "")
        if not text:
            continue
        for raw_line in text.splitlines():
            evidence = raw_line.strip()
            clean = clean_text(evidence)
            if not clean or clean in {"为什么"}:
                continue
            if re.match(r"^(?:优先买谁|优先买|首选|最佳选择)\s*[：:]", clean):
                candidate = re.split(r"[：:]", clean, maxsplit=1)[-1]
                if not specific_stock_name(candidate):
                    continue
            item_text = strip_action_prefix(clean)
            if not item_text:
                continue
            actions.append(
                {
                    "text": item_text,
                    "_sourceSection": source_section,
                    "_evidence": evidence,
                    "_confidence": "high",
                }
            )
    return actions


def extract_next_actions_text(
    sections: dict[str, str],
) -> tuple[str, str, str, str] | None:
    for source_section in ("如果重来一次", "是否值得重来一次继续买"):
        evidence = sections.get(source_section, "").strip()
        if not evidence:
            continue
        lines = [clean_text(line) for line in evidence.splitlines()]
        text = "\n".join(line for line in lines if line).strip()
        if text:
            return text, source_section, evidence, "high"
    return None


def strip_action_prefix(text: str) -> str:
    stripped = re.sub(r"^\d+\s*[、.．]\s*", "", text).strip()
    stripped = re.sub(r"^(规则|动作|下次|优先买谁|优先买|东材科技排第几|为什么)\s*\d*\s*[：:]\s*", "", stripped).strip()
    return stripped


def extract_ranking(sections: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    ranking: list[dict[str, Any]] = []
    warnings: list[str] = []
    rank_pattern = re.compile(r"^[\s>*#_`\-]*第(?P<rank>[一二三123])名[*_`]*\s*[：:]\s*(?P<name>.+)$")
    reason_pattern = re.compile(r"^[\s>*#_`\-]*(?:[*_`]*)(?:理由|逻辑|交易意义|摘要|优势)(?:[*_`]*)\s*[：:]\s*(?P<reason>.+)$")

    for source_section in ("同行比较", "相关公司比较"):
        lines = sections.get(source_section, "").splitlines()
        for index, raw_line in enumerate(lines):
            match = rank_pattern.match(raw_line.strip())
            if not match:
                continue
            rank = RANK_LABELS[match.group("rank")]
            name = specific_stock_name(match.group("name"))
            if not name:
                warnings.append(f"{source_section}第{rank}名不是明确股票名称，未映射")
                continue
            reason = None
            reason_evidence = ""
            for candidate in lines[index + 1 : index + 4]:
                if rank_pattern.match(candidate.strip()):
                    break
                reason_match = reason_pattern.match(candidate.strip())
                if reason_match:
                    reason = clean_text(reason_match.group("reason"))
                    reason_evidence = candidate.strip()
                    break
                candidate_text = clean_text(candidate)
                if candidate_text and not candidate_text.startswith("东材科技排名"):
                    reason = candidate_text
                    reason_evidence = candidate.strip()
                    break
            ranking.append(
                {
                    "rank": rank,
                    "name": name,
                    "reason": reason,
                    "_sourceSection": source_section,
                    "_nameEvidence": raw_line.strip(),
                    "_summaryEvidence": reason_evidence,
                    "_confidence": "high",
                }
            )

    ranking.sort(key=lambda item: item["rank"])
    return ranking, warnings


def extract_priority_choice(
    sections: dict[str, str],
) -> tuple[str, str | None, str, str, str, str] | None:
    label_pattern = re.compile(r"^[\s>*#_`\-]*(?:优先买谁|优先买|首选|最佳选择)[*_`]*\s*[：:]\s*(?P<name>.+)$")
    sentence_pattern = re.compile(r"(?:应|应该|建议)?优先买(?:入)?(?P<name>[\u4e00-\u9fffA-Z0-9]{2,12})")

    for source_section in ("如果重来一次", "是否值得重来一次继续买"):
        lines = sections.get(source_section, "").splitlines()
        for index, raw_line in enumerate(lines):
            clean = clean_text(raw_line)
            label_match = label_pattern.match(raw_line.strip())
            sentence_match = sentence_pattern.search(clean)
            candidate = label_match.group("name") if label_match else sentence_match.group("name") if sentence_match else ""
            name = specific_stock_name(candidate)
            if not name:
                continue
            reason = None
            reason_evidence = ""
            for candidate_line in lines[index + 1 : index + 4]:
                next_clean = clean_text(candidate_line)
                if re.match(r"^(?:理由|逻辑|交易意义|摘要|优势)[：:]", next_clean):
                    reason = re.split(r"[：:]", next_clean, maxsplit=1)[-1].strip()
                    reason_evidence = candidate_line.strip()
                    break
            return (
                name,
                reason,
                source_section,
                raw_line.strip(),
                reason_evidence,
                "high" if label_match else "medium",
            )
    return None


def extract_industry_chain(
    sections: dict[str, str],
    stock_name: str,
) -> tuple[dict[str, list[dict[str, Any]]], str, str, str] | None:
    direct = sections.get("产业链位置", "").strip()
    if direct:
        evidence = find_chain_evidence(direct) or direct
        nodes = parse_chain_nodes(evidence, stock_name)
        if nodes:
            return {"nodes": nodes}, "产业链位置", evidence, "high"

    label_pattern = re.compile(r"^[\s>*#_`\-]*产业链(?:位置)?\s*[：:]\s*(?P<value>.+)$")
    for source_section in ("题材分析", "交易逻辑"):
        for raw_line in sections.get(source_section, "").splitlines():
            match = label_pattern.match(raw_line.strip())
            if match:
                chain_text = clean_text(match.group("value"))
                nodes = parse_chain_nodes(chain_text, stock_name)
                if nodes:
                    return {"nodes": nodes}, source_section, raw_line.strip(), "high"
            if has_arrow(raw_line):
                nodes = parse_chain_nodes(raw_line, stock_name)
                if nodes:
                    return {"nodes": nodes}, source_section, raw_line.strip(), "medium"
    return None


def find_chain_evidence(text: str) -> str:
    lines = [line.strip().strip("`") for line in text.splitlines() if line.strip()]
    for line in lines:
        if has_arrow(line) and clean_text(line) not in {"↓", "→"}:
            return line
    if any(clean_text(line) == "↓" for line in lines):
        return "\n".join(lines)
    return ""


def parse_chain_nodes(text: str, stock_name: str) -> list[dict[str, Any]]:
    clean = clean_text(text).replace("`", "")
    raw_nodes: list[tuple[str, str]] = []

    if "→" in clean or "->" in clean:
        for part in re.split(r"→|->", clean):
            node = clean_chain_node(part)
            if node:
                raw_nodes.append(("", node))
    else:
        for line in clean.splitlines():
            item = clean_chain_node(line)
            if item and item not in {"↓", "→"}:
                label = ""
                if "：" in item or ":" in item:
                    label, item = re.split(r"[：:]", item, maxsplit=1)
                    label = clean_text(label)
                    item = clean_chain_node(item)
                if item:
                    raw_nodes.append((label, item))

    nodes: list[dict[str, Any]] = []
    seen = set()
    for index, (level, name) in enumerate(raw_nodes, start=1):
        if not name or name in seen:
            continue
        seen.add(name)
        item: dict[str, Any] = {"name": name}
        if level:
            item["level"] = level
        if stock_name and stock_name in name:
            item["current"] = True
        nodes.append(item)
    return nodes


def clean_chain_node(value: str) -> str:
    text = clean_text(value)
    text = re.sub(r"←.*$", "", text).strip()
    text = re.sub(r"^\[|\]$", "", text).strip()
    text = re.sub(r"（.*?在此.*?）", "", text).strip()
    text = re.sub(r"\(.*?在此.*?\)", "", text).strip()
    return text.strip("。；; ")


def extract_profit_flow(sections: dict[str, str]) -> tuple[str, str, str, str] | None:
    label_pattern = re.compile(r"^[\s>*#_`\-]*(?:利润流向|利润分配|利润主要流向)\s*[：:]\s*(?P<value>.+)$")
    for source_section in ("壁垒和利润流向", "题材分析", "交易逻辑"):
        lines = sections.get(source_section, "").splitlines()
        for raw_line in lines:
            match = label_pattern.match(raw_line.strip())
            if match:
                return clean_text(match.group("value")), source_section, raw_line.strip(), "high"

    direct = sections.get("壁垒和利润流向", "").strip()
    if direct:
        return clean_text(direct), "壁垒和利润流向", direct, "high"

    for source_section in ("题材分析", "交易逻辑"):
        for raw_line in sections.get(source_section, "").splitlines():
            if "利润" in raw_line and any(token in raw_line for token in ("流向", "集中", "汇聚", "受益")):
                return clean_text(raw_line), source_section, raw_line.strip(), "medium"
    return None


def source_section_for(raw_line: str, sections: dict[str, str], fallback: str) -> str:
    stripped = raw_line.strip()
    for title, content in sections.items():
        if stripped and stripped in content:
            return title
    return fallback


def specific_stock_name(value: str) -> str:
    clean = clean_text(value)
    clean = re.sub(r"^(?:仍然是|就是|选择|买入)", "", clean).strip()
    clean = re.split(r"[（(。；;\-—]", clean, maxsplit=1)[0].strip()
    if not clean or any(word in clean for word in GENERIC_CHOICE_WORDS):
        return ""
    if re.fullmatch(r"\d{6}", clean):
        return clean
    if re.fullmatch(r"[A-Z]{2,6}", clean):
        return clean
    if re.fullmatch(r"[\u4e00-\u9fff]{2,8}", clean):
        return clean
    names = [part.strip() for part in re.split(r"[、，,]", clean) if part.strip()]
    if len(names) > 1 and all(re.fullmatch(r"[\u4e00-\u9fff]{2,8}|\d{6}|[A-Z]{2,6}", name) for name in names):
        return "、".join(names)
    return ""


def has_arrow(value: str) -> bool:
    return "→" in value or "->" in value or "↓" in value


def clean_text(value: str) -> str:
    text = (value or "").strip()
    text = re.sub(r"^[\s>*#_`\-]+", "", text)
    text = re.sub(r"[*_`]+", "", text)
    return text.strip()
