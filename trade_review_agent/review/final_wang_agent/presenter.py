from __future__ import annotations

import re
import time
from typing import Any


SECTION_TITLES = ["最终判断", "交易逻辑", "产业链位置", "壁垒和利润流向", "同行比较", "如果重来一次", "一句话结论"]
_TITLE_PATTERN = "|".join(re.escape(title) for title in SECTION_TITLES)


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
    payload = map_sections_to_frontend(sections, answer, trade["stock_name"])

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
                "mode": "deterministic_section_mapping",
                "sections": sections,
                "display_sections": display_sections(sections),
            },
            "research_pipeline": "final_wang_agent:deepseek_raw_answer_sections_direct_to_frontend",
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
                "mode": "deepseek_raw_coach_answer_direct_section_mapping",
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
    normalized = {title: text for title, text in normalized.items() if text}
    if not normalized and answer.strip():
        normalized["最终判断"] = answer.strip()
    return normalized


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
        rf"^(?P<num>[一二三四五六七]\s*[、.．]\s*)?(?P<title>{_TITLE_PATTERN})(?P<colon>\s*[：:]?)(?P<rest>.*)$",
        text,
    )
    if not match:
        return None

    number_prefix = bool(match.group("num"))
    colon = match.group("colon").strip()
    rest = match.group("rest").strip()
    heading_markers = markdown_heading or markdown_emphasis or number_prefix or bool(colon) or not rest
    if not heading_markers:
        return None

    rest = re.sub(r"^[*_`#\s]+", "", rest).strip()
    rest = rest.strip("*_` ").strip()
    return match.group("title"), rest


def display_sections(sections: dict[str, str]) -> list[dict[str, str]]:
    rows = [{"title": title, "content": sections[title]} for title in SECTION_TITLES if sections.get(title)]
    rows.extend({"title": title, "content": content} for title, content in sections.items() if title not in SECTION_TITLES)
    return rows


def map_sections_to_frontend(sections: dict[str, str], answer: str, stock_name: str) -> dict[str, Any]:
    final_section = sections.get("最终判断", "")
    logic_section = sections.get("交易逻辑", "")
    chain_section = sections.get("产业链位置", "")
    moat_section = sections.get("壁垒和利润流向", "")
    peer_section = sections.get("同行比较", "")
    replay_section = sections.get("如果重来一次", "")
    one_line = sections.get("一句话结论", "") or last_nonempty_line(answer)
    rankings = extract_rankings(peer_section)
    better_choice = extract_better_choice(replay_section) or (rankings[0] if rankings else stock_name)

    return {
        "ai_final_answer": {
            "score": score_from_text(answer),
            "verdict": final_section or one_line,
            "better_choice": better_choice,
            "main_reason": logic_section,
            "mistake_source": mistake_source(answer),
            "next_action": replay_section,
        },
        "market_theme": {"mainline": logic_section, "secondary_theme": logic_section, "theme_fit": final_section, "core_stocks": rankings},
        "industry_chain": {
            "position": chain_section,
            "chain_nodes": extract_chain_nodes(chain_section),
            "upstream": [],
            "downstream": [],
            "core_products": [],
            "barrier": moat_section,
            "barriers": [moat_section] if moat_section else [],
            "profit_flow": moat_section,
        },
        "peer_comparison": {
            "better_choice": {"name": better_choice, "reason": replay_section or peer_section},
            "same_chain_peers": [{"name": name, "role": f"第{idx}名", "key_reason": peer_section} for idx, name in enumerate(rankings, start=1)],
            "stronger_on_trade_day": rankings,
            "summary": peer_section,
        },
        "industry_rating": "B",
        "theme": logic_section,
        "market_hype_reason": logic_section,
        "traded_business_line": chain_section,
        "what_market_is_pricing": logic_section,
        "industry_tags": [],
        "claims": [item for item in [final_section, one_line] if item],
        "section_map": sections,
        "display_sections": display_sections(sections),
        "profit_flow": {"company_position": chain_section, "why_profit_flows_here": moat_section},
        "moat_radar": {"company_score": None, "industry_average": None, "dimensions": [], "explanation": moat_section},
        "logic_tree": [],
        "weakest_link": mistake_source(answer),
        "sector_symbol": "",
        "peer_ranking": rankings,
        "reasoning_summary": one_line or final_section,
    }


def extract_chain_nodes(text: str) -> list[str]:
    for line in text.splitlines():
        if "→" in line or "->" in line:
            return [node for node in (clean_node(item) for item in re.split(r"→|->", line)) if node][:8]
    return []


def extract_rankings(text: str) -> list[str]:
    return [name for name in (extract_rank(text, idx) for idx in (1, 2, 3)) if name]


def extract_rank(text: str, rank: int) -> str:
    label = {1: "第一名", 2: "第二名", 3: "第三名"}[rank]
    for line in text.splitlines():
        if label in line:
            value = line.split("：", 1)[-1] if "：" in line else line.split(":", 1)[-1] if ":" in line else line
            return re.split(r"[，,。；;\-—]", re.sub(r"[*`#]", "", value).strip())[0].strip()
    return ""


def extract_better_choice(text: str) -> str:
    for line in text.splitlines():
        if "优先买" in line or "优先：" in line:
            value = line.split("：", 1)[-1] if "：" in line else line.split(":", 1)[-1] if ":" in line else line
            return re.split(r"[，,。；;\-—]", re.sub(r"^[\-*\s]+", "", value).strip())[0].strip()
    return ""


def score_from_text(text: str) -> int:
    score = 72
    if "方向买对" in text or "买对方向" in text or "方向是对" in text:
        score += 6
    if "主线核心" in text:
        score += 6
    if "主线支线" in text or "不是最核心" in text:
        score += 1
    if "买错" in text or "不值得" in text:
        score -= 8
    return max(0, min(100, score))


def mistake_source(text: str) -> str:
    if "选股" in text and "执行" in text:
        return "选股和执行都需要优化"
    if "选股" in text or "更强标的" in text or "不是最核心" in text:
        return "选股问题"
    if "买点" in text or "追高" in text or "执行" in text:
        return "执行问题"
    return "暂无明显问题"


def last_nonempty_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def clean_node(value: str) -> str:
    return re.sub(r"^[\-*`\s]+|[`。；;\s]+$", "", value).strip()
