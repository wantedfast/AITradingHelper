from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trade_review_agent.review.final_wang_agent.agent import extract_responses_text


PROMPT_PATH = ROOT / "trade_review_agent" / "prompts" / "stock_reverse_engineering" / "SINGLE_AGENT_PROMPT.md"
MODEL = "gpt-5.6-luna"


def obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


STRING = {"type": "string"}
NUMBER = {"type": "number"}
INTEGER = {"type": "integer"}
BOOLEAN = {"type": "boolean"}
STRINGS = {"type": "array", "items": STRING}
EVIDENCE_IDS = {"type": "array", "items": {"type": "string", "pattern": "^E[0-9]{3}$"}, "minItems": 1}


def report_schema(subject_type: str = "stock") -> dict[str, Any]:
    company = obj({"name": STRING, "code": STRING})
    claim = obj({"claim": STRING, "evidence_ids": EVIDENCE_IDS, "confidence": {"type": "string", "enum": ["high", "medium", "low", "pending"]}})
    challenge = obj({"challenger": STRING, "target": STRING, "issue": STRING, "resolution": STRING, "evidence_ids": EVIDENCE_IDS})
    ranking = obj({
        "name": STRING, "code": STRING, "industry_node": STRING, "product": STRING,
        "industry_position": STRING, "barrier": NUMBER, "profit": NUMBER, "growth": NUMBER,
        "core_score": NUMBER, "labels": STRINGS, "reason": STRING, "evidence_ids": EVIDENCE_IDS,
    })
    simple_ranking = obj({"name": STRING, "position": STRING, "reason": STRING, "evidence_ids": EVIDENCE_IDS})
    evidence = obj({
        "id": {"type": "string", "pattern": "^E[0-9]{3}$"}, "title": STRING, "url": STRING,
        "publisher": STRING, "published_at": STRING, "source_tier": {"type": "string", "enum": ["A", "B", "C", "D"]},
        "excerpt": STRING,
    })
    properties = {
        "schema_version": {"type": "integer", "enum": [2]},
        "headline": STRING,
        "subject": obj({"type": {"type": "string", "enum": [subject_type]}, "name": STRING, "code": STRING}),
        "capital_logic": obj({
            "summary": STRING,
            "speculation_json": obj({"event": STRING, "logic": STRING, "industry_trend": STRING, "evidence_confidence": STRING}),
            "current_catalysts": {"type": "array", "items": obj({"event": STRING, "event_type": STRING, "event_date": STRING, "evidence_ids": EVIDENCE_IDS})},
            "claims": {"type": "array", "items": claim}, "challenges": {"type": "array", "items": challenge},
            "evidence_ids": EVIDENCE_IDS,
        }),
        "product_path": obj({
            "summary": STRING, "path": {"type": "array", "items": STRING, "minItems": 4},
            "exposure_judgment": STRING, "claims": {"type": "array", "items": claim},
            "challenges": {"type": "array", "items": challenge}, "evidence_ids": EVIDENCE_IDS,
        }),
        "bom": obj({
            "summary": STRING,
            "tree": obj({
                "final_product": STRING,
                "branches": {"type": "array", "items": obj({
                    "component": STRING, "subnodes": STRINGS,
                    "a_share_companies": {"type": "array", "items": company}, "evidence_ids": EVIDENCE_IDS,
                })},
            }),
            "items": {"type": "array", "items": obj({
                "node": STRING, "chain_position": {"type": "string", "enum": ["upstream", "midstream", "downstream"]},
                "a_share_companies": {"type": "array", "items": company}, "value_trend": STRING,
                "evidence_confidence": {"type": "string", "enum": ["high", "medium", "low", "pending"]},
                "evidence_ids": EVIDENCE_IDS,
            })},
            "claims": {"type": "array", "items": claim}, "challenges": {"type": "array", "items": challenge},
            "evidence_ids": EVIDENCE_IDS,
        }),
        "bottleneck": obj({
            "summary": STRING, "current": STRING,
            "type": {"type": "string", "enum": ["structural", "capacity", "material", "emotional", "false_bottleneck"]},
            "first_price_response": STRING, "expansion_difficulty": STRING, "profit_realization": STRING,
            "next_bottleneck": STRING,
            "a_share_mapping": {"type": "array", "items": obj({
                "node": STRING, "companies": {"type": "array", "items": company}, "reason": STRING, "evidence_ids": EVIDENCE_IDS,
            })},
            "claims": {"type": "array", "items": claim}, "challenges": {"type": "array", "items": challenge},
            "evidence_ids": EVIDENCE_IDS,
        }),
        "profit_flow": obj({
            "summary": STRING,
            "ranked_nodes": {"type": "array", "items": obj({
                "node": STRING, "stars": INTEGER,
                "classification": {"type": "string", "enum": ["core_bottleneck", "strong_beneficiary", "volume_growth", "theme_follower", "false_core"]},
                "pricing_power": STRING, "profit_elasticity": STRING,
                "a_share_companies": {"type": "array", "items": company}, "evidence_ids": EVIDENCE_IDS,
            })},
            "first_tightening": STRING, "first_price_increase": STRING, "pricing_power": STRING,
            "highest_earnings_elasticity": STRING, "margin_squeezed_nodes": STRINGS,
            "claims": {"type": "array", "items": claim}, "challenges": {"type": "array", "items": challenge},
            "evidence_ids": EVIDENCE_IDS,
        }),
        "positioning": obj({
            "summary": STRING, "label": STRING, "fund_positioning": STRING,
            "is_core_beneficiary": BOOLEAN, "earns_industrial_profit": BOOLEAN, "emotional_premium": STRING,
            "cleaner_same_chain_companies": STRINGS, "reason": STRING, "evidence_ids": EVIDENCE_IDS,
        }),
        "same_chain_core_asset_ranking": {"type": "array", "items": ranking},
        "same_chain_core_asset_status": obj({"status": {"type": "string", "enum": ["ranked", "none"]}, "reason": STRING, "evidence_ids": EVIDENCE_IDS}),
        "bottleneck_ranking": {"type": "array", "items": simple_ranking, "minItems": 1},
        "profit_capture_ranking": {"type": "array", "items": simple_ranking, "minItems": 1},
        "judge": obj({
            "conclusion": STRING,
            "classifications": obj({
                "emotion_leader": BOOLEAN, "industry_leader": BOOLEAN, "capacity_core": BOOLEAN,
                "shovel_seller": BOOLEAN, "high_elasticity": BOOLEAN, "high_profit": BOOLEAN,
                "high_growth": BOOLEAN, "catch_up": BOOLEAN, "false_core": BOOLEAN, "long_term_tracking": BOOLEAN,
            }),
            "role_conflicts": {"type": "array", "items": challenge},
            "disconfirming_signals": {"type": "array", "items": STRING, "minItems": 1},
            "evidence_ids": EVIDENCE_IDS,
        }),
        "audit": obj({
            "claim_evidence_checks": {"type": "array", "items": obj({
                "claim": STRING, "evidence_id": {"type": "string", "pattern": "^E[0-9]{3}$"},
                "verdict": {"type": "string", "enum": ["supported", "partial", "not_supported"]}, "reason": STRING,
            }), "minItems": 8},
            "entity_mismatch_found": BOOLEAN, "d_tier_only_claim_found": BOOLEAN,
            "score_formula_checked": BOOLEAN, "unresolved_evidence_gaps": STRINGS,
        }),
        "evidence": {"type": "array", "items": evidence, "minItems": 8},
    }
    if subject_type == "stock":
        properties["input_stock_score"] = obj({
            "barrier": NUMBER, "profit": NUMBER, "growth": NUMBER, "core_score": NUMBER,
            "explanation": STRING, "evidence_ids": EVIDENCE_IDS,
        })
    return obj(properties)


def load_prompt(subject: str, code: str, subject_type: str = "stock") -> str:
    if subject_type == "stock":
        type_rule = "股票输入必须输出输入股票三高评分；同链核心资产排名不得重复输入股票。"
    else:
        type_rule = "产业链输入不得输出 input_stock_score；核心资产排名直接列出产业链 A 股，positioning 评价产业链所处阶段而不是虚构输入股票。"
    return (
        PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{{SUBJECT}}", subject)
        .replace("{{STOCK_CODE}}", code)
        .replace("{{SUBJECT_TYPE}}", subject_type)
        .replace("{{SUBJECT_TYPE_RULE}}", type_rule)
        .replace("{{AS_OF_DATE}}", datetime.now().astimezone().isoformat(timespec="minutes"))
    )


def call_luna(prompt: str) -> tuple[dict[str, Any], dict[str, Any], float]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required")
    body = {
        "model": os.getenv("STOCK_RESEARCH_LUNA_MODEL", MODEL),
        "input": prompt,
        "reasoning": {"effort": "high"},
        "tools": [{"type": "web_search"}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "stock_research_single_agent",
                "strict": True,
                "schema": report_schema("stock"),
            }
        },
        "max_output_tokens": int(os.getenv("STOCK_RESEARCH_LUNA_MAX_OUTPUT_TOKENS", "30000")),
    }
    request = urllib.request.Request(
        os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/responses",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    proxy = os.getenv("OPENAI_PROXY_URL", "").strip()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy})) if proxy else urllib.request.build_opener()
    started = time.monotonic()
    try:
        with opener.open(request, timeout=360) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        if hasattr(exc, "read"):
            detail = exc.read().decode("utf-8", errors="replace")[:4000]
            raise RuntimeError(f"Luna request failed: {detail}") from exc
        raise
    duration = time.monotonic() - started
    report = json.loads(extract_responses_text(raw))
    return report, raw, duration


def compute_metrics(raw: dict[str, Any], duration: float) -> dict[str, Any]:
    usage = raw.get("usage") or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    searches = sum(1 for item in raw.get("output") or [] if isinstance(item, dict) and item.get("type") == "web_search_call")
    usd = input_tokens * 0.20 / 1_000_000 + output_tokens * 1.20 / 1_000_000 + searches * 0.01
    return {
        "model": raw.get("model") or MODEL,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "search_count": searches,
        "cost_usd": round(usd, 6),
        "cost_cny": round(usd * float(os.getenv("STOCK_RESEARCH_USD_CNY", "7.2")), 4),
        "duration_seconds": round(duration, 3),
    }


def validate_report(report: dict[str, Any]) -> dict[str, Any]:
    evidence = report.get("evidence") or []
    known = {str(item.get("id")) for item in evidence if isinstance(item, dict)}
    referenced: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "evidence_ids" and isinstance(child, list):
                    referenced.extend(str(item) for item in child)
                elif key != "evidence":
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(report)
    invalid = sorted(set(referenced) - known)
    score = report.get("input_stock_score") or {}
    expected = round(float(score.get("barrier", 0)) * 0.4 + float(score.get("profit", 0)) * 0.3 + float(score.get("growth", 0)) * 0.3, 1)
    rankings = report.get("same_chain_core_asset_ranking") or []
    ranking_scores = [float(item.get("core_score", 0)) for item in rankings]
    checks = report.get("audit", {}).get("claim_evidence_checks") or []
    supported = sum(1 for item in checks if item.get("verdict") == "supported")
    correctly_rejected = sum(
        1 for item in checks
        if item.get("verdict") == "not_supported"
        and any(marker in str(item.get("reason") or "") for marker in ("未采用", "未纳入", "不采用"))
    )
    return {
        "all_evidence_ids_exist": not invalid,
        "invalid_evidence_ids": invalid,
        "score_formula_valid": abs(float(score.get("core_score", -1)) - expected) <= 0.11,
        "ranking_descending": ranking_scores == sorted(ranking_scores, reverse=True),
        "self_audited_semantic_support_rate": round(supported / len(checks), 4) if checks else 0,
        "self_audited_decision_pass_rate": round((supported + correctly_rejected) / len(checks), 4) if checks else 0,
        "correctly_rejected_unsupported_claims": correctly_rejected,
        "source_count": len(evidence),
        "a_b_source_count": sum(1 for item in evidence if item.get("source_tier") in {"A", "B"}),
    }


def remove_redundant_dangling_evidence_ids(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Remove safe dangling references without inventing replacement evidence.

    Optional list items whose own citations are all missing are removed as
    unsupported conclusions. Core section citations still fail closed.
    """
    known = {str(item.get("id")) for item in report.get("evidence") or [] if isinstance(item, dict)}
    removed: list[dict[str, Any]] = []
    droppable_lists = {
        "$report.capital_logic.current_catalysts",
        "$report.bom.tree.branches",
        "$report.bom.items",
        "$report.bottleneck.a_share_mapping",
        "$report.profit_flow.ranked_nodes",
        "$report.same_chain_core_asset_ranking",
        "$report.judge.role_conflicts",
    }
    min_one_droppable_lists = {
        "$report.bottleneck_ranking",
        "$report.profit_capture_ranking",
    }

    def own_dangling_ids(value: Any) -> list[str]:
        if not isinstance(value, dict) or not isinstance(value.get("evidence_ids"), list):
            return []
        ids = [str(item) for item in value["evidence_ids"]]
        return ids if ids and not any(item in known for item in ids) else []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                if key == "evidence_ids" and isinstance(child, list):
                    valid = [item for item in child if str(item) in known]
                    invalid = [str(item) for item in child if str(item) not in known]
                    if invalid and not valid:
                        raise RuntimeError(f"Claim has only dangling evidence IDs at {child_path}: {invalid}")
                    if invalid:
                        value[key] = valid
                        removed.append({"path": child_path, "ids": invalid})
                elif key != "evidence":
                    visit(child, child_path)
        elif isinstance(value, list):
            kept = []
            for index, child in enumerate(value):
                dangling = own_dangling_ids(child)
                may_drop = (
                    path in droppable_lists
                    or (path in min_one_droppable_lists and len(value) > 1)
                    or path.endswith(".claims")
                    or path.endswith(".challenges")
                )
                if dangling and may_drop:
                    removed.append({"path": f"{path}[{index}]", "ids": dangling, "action": "dropped_unsupported_item"})
                    continue
                visit(child, f"{path}[{index}]")
                kept.append(child)
            value[:] = kept

    visit(report, "$report")
    return removed


def render_html(report: dict[str, Any]) -> str:
    def esc(value: Any) -> str:
        return html.escape(str(value if value not in (None, "") else "—"))

    evidence_map = {str(item.get("id")): item for item in report.get("evidence") or []}

    def citations(ids: Any) -> str:
        links = []
        for evidence_id in ids if isinstance(ids, list) else []:
            item = evidence_map.get(str(evidence_id))
            if item:
                links.append(f"<a class='cite' href='{esc(item.get('url'))}' target='_blank' rel='noreferrer'>{esc(evidence_id)} · {esc(item.get('title'))}</a>")
        return "<div class='cites'>" + "".join(links) + "</div>"

    def companies(value: Any) -> str:
        if not isinstance(value, list):
            return esc(value)
        return "、".join(esc(f"{item.get('name', '')} {item.get('code', '')}".strip()) if isinstance(item, dict) else esc(item) for item in value)

    def role(index: int, title: str, section: dict[str, Any], body: str = "") -> str:
        challenges = "".join(
            f"<article class='challenge'><b>{esc(item.get('challenger'))} → {esc(item.get('target'))}</b><p>{esc(item.get('issue'))}</p><strong>{esc(item.get('resolution'))}</strong>{citations(item.get('evidence_ids'))}</article>"
            for item in section.get("challenges") or []
        )
        return f"<section class='role'><header><b>{index:02d}</b><div><small>SPECIALIST REVIEW</small><h2>{esc(title)}</h2></div></header><p class='lead'>{esc(section.get('summary'))}</p>{body}<div class='challenge-grid'>{challenges}</div>{citations(section.get('evidence_ids'))}</section>"

    capital = report.get("capital_logic") or {}
    product = report.get("product_path") or {}
    bom = report.get("bom") or {}
    bottleneck = report.get("bottleneck") or {}
    profit = report.get("profit_flow") or {}
    positioning = report.get("positioning") or {}
    judge = report.get("judge") or {}
    score = report.get("input_stock_score") or {}
    speculation = capital.get("speculation_json") or {}

    path_html = "<div class='path'>" + "".join(f"<span>{esc(item)}</span>" for item in product.get("path") or []) + "</div>"
    bom_rows = "".join(
        f"<tr><td>{esc(item.get('node'))}</td><td>{esc(item.get('chain_position'))}</td><td>{companies(item.get('a_share_companies'))}</td><td>{esc(item.get('value_trend'))}</td><td>{esc(item.get('evidence_confidence'))}{citations(item.get('evidence_ids'))}</td></tr>"
        for item in bom.get("items") or []
    )
    bom_table = f"<div class='table'><table><thead><tr><th>BOM节点</th><th>位置</th><th>A股映射</th><th>价值变化</th><th>证据</th></tr></thead><tbody>{bom_rows}</tbody></table></div>"
    profit_rows = "".join(
        f"<tr><td>{esc(item.get('node'))}</td><td>{esc(item.get('stars'))}星</td><td>{esc(item.get('classification'))}</td><td>{esc(item.get('pricing_power'))}</td><td>{esc(item.get('profit_elasticity'))}{citations(item.get('evidence_ids'))}</td></tr>"
        for item in profit.get("ranked_nodes") or []
    )
    profit_table = f"<div class='table'><table><thead><tr><th>环节</th><th>等级</th><th>分类</th><th>定价权</th><th>利润弹性</th></tr></thead><tbody>{profit_rows}</tbody></table></div>"

    def ranking(title: str, rows: list[dict[str, Any]]) -> str:
        cards = "".join(
            f"<li><b>{index}</b><div><strong>{esc(item.get('name'))} · {esc(item.get('code') or item.get('position'))}</strong><span>{esc(item.get('industry_position') or item.get('position'))}</span><p>{esc(item.get('reason'))}</p>{citations(item.get('evidence_ids'))}</div></li>"
            for index, item in enumerate(rows, 1)
        )
        return f"<section class='ranking'><h2>{esc(title)}</h2><ol>{cards or '<li><div>证据不足，暂不排名</div></li>'}</ol></section>"

    evidence_html = "".join(
        f"<a href='{esc(item.get('url'))}' target='_blank' rel='noreferrer'><b>{esc(item.get('id'))} · {esc(item.get('source_tier'))}级</b><span>{esc(item.get('title'))}</span><em>{esc(item.get('publisher'))} · {esc(item.get('published_at'))}</em><p>{esc(item.get('excerpt'))}</p></a>"
        for item in report.get("evidence") or []
    )
    conflicts = "".join(
        f"<article class='challenge'><b>{esc(item.get('challenger'))} → {esc(item.get('target'))}</b><p>{esc(item.get('issue'))}</p><strong>{esc(item.get('resolution'))}</strong>{citations(item.get('evidence_ids'))}</article>"
        for item in judge.get("role_conflicts") or []
    )
    metrics = report.get("meta") or {}
    subject = report.get("subject") or {}
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(subject.get('name'))}产业链逆向研究</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#080a09;color:#eee8db;font-family:Arial,'Microsoft YaHei',sans-serif;line-height:1.65}}main{{max-width:1180px;margin:auto;padding:40px 20px}}h1{{font-size:44px;line-height:1.15;margin:8px 0}}h2{{margin:0 0 14px}}.hero,.role,.score,.ranking,.evidence-section{{border:1px solid #30352e;border-radius:18px;padding:24px;background:#111410;margin:15px 0}}.hero{{border-color:#665526;background:radial-gradient(circle at 90% 0,#352b15 0,transparent 36%),#11140f}}.eyebrow,.role small,.dashboard small,h2{{color:#dfb936}}.meta{{color:#93988f;font-size:13px}}.dashboard{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:15px 0}}.dashboard article{{border:1px solid #30352e;border-radius:14px;padding:18px;background:#10130f}}.dashboard article:last-child{{grid-column:1/-1}}.dashboard p{{font-size:17px}}.score{{display:flex;gap:24px;align-items:center}}.score strong{{font-size:58px;color:#dfb936}}.role>header{{display:flex;gap:14px;align-items:center;border-bottom:1px solid #2d312b;padding-bottom:13px}}.role>header>b{{display:grid;place-items:center;width:42px;height:42px;border:1px solid #665526;border-radius:50%;color:#dfb936}}.lead{{font-size:18px}}.path{{display:flex;gap:26px;overflow:auto;padding:14px 2px}}.path span{{position:relative;white-space:nowrap;border:1px solid #5e5128;border-radius:9px;padding:10px}}.path span:not(:last-child):after{{content:'→';position:absolute;right:-20px;color:#dfb936}}.table{{overflow:auto;border:1px solid #30352e;border-radius:12px}}table{{width:100%;min-width:760px;border-collapse:collapse}}th,td{{padding:11px;text-align:left;vertical-align:top;border-top:1px solid #292d27}}th{{background:#17190f;color:#dfb936}}.cites{{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;min-width:0}}.cite{{display:inline-block;max-width:100%;overflow-wrap:anywhere;color:#d8bd69;border:1px solid #5e512a;border-radius:9px;padding:3px 8px;text-decoration:none;font-size:11px}}.challenge-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}}.challenge{{border:1px solid #504526;border-radius:11px;padding:12px;background:#0d100d}}.challenge strong{{color:#b9bdb5}}.ranking ol{{list-style:none;padding:0;margin:0}}.ranking li{{display:grid;grid-template-columns:38px minmax(0,1fr);gap:12px;padding:14px 0;border-top:1px solid #2a2e28}}.ranking li>b{{color:#dfb936;font-size:21px}}.ranking li>div{{min-width:0}}.ranking li span{{display:block;color:#9ca29a}}.evidence{{display:grid;gap:8px}}.evidence>a{{display:grid;grid-template-columns:100px minmax(0,1fr) auto;color:#eee;text-decoration:none;border:1px solid #2c302a;border-radius:10px;padding:12px}}.evidence a b{{color:#dfb936}}.evidence em{{color:#888;font-style:normal}}.evidence p{{grid-column:2/-1;margin:5px 0 0;color:#aeb3aa}}
@media(max-width:700px){{main{{padding:20px 12px}}h1{{font-size:32px}}.dashboard,.challenge-grid{{grid-template-columns:1fr}}.dashboard article:last-child{{grid-column:auto}}.score{{align-items:flex-start;flex-direction:column}}.evidence>a{{grid-template-columns:1fr}}.evidence p{{grid-column:auto}}}}
</style></head><body><main>
<header class='hero'><div class='eyebrow'>LUNA · SINGLE AGENT SIX-PERSPECTIVE RESEARCH</div><h1>{esc(subject.get('name'))} · {esc(subject.get('code'))}</h1><p>{esc(report.get('headline'))}</p><div class='meta'>输入 {esc(metrics.get('input_tokens'))} tokens · 输出 {esc(metrics.get('output_tokens'))} tokens · 搜索 {esc(metrics.get('search_count'))} 次 · 成本 ¥{esc(metrics.get('cost_cny'))} · 耗时 {esc(metrics.get('duration_seconds'))} 秒</div></header>
<div class='dashboard'><article><small>资金为什么炒</small><p>{esc(capital.get('summary'))}</p></article><article><small>利润真正流向</small><p>{esc(profit.get('summary'))}</p></article><article><small>当前产业瓶颈</small><p>{esc(bottleneck.get('summary'))}</p></article><article><small>输入对象定位</small><p>{esc(positioning.get('summary') or positioning.get('reason'))}</p></article><article><small>最重要证伪信号</small><p>{esc('；'.join(judge.get('disconfirming_signals') or []))}</p></article></div>
<section class='score'><strong>{esc(score.get('core_score'))}</strong><div><h2>输入股票三高评分</h2><p>壁垒 {esc(score.get('barrier'))} · 利润 {esc(score.get('profit'))} · 成长 {esc(score.get('growth'))}</p><p>{esc(score.get('explanation'))}</p><small>不是上涨概率或买入评级</small></div></section>
{ranking('同产业链核心资产', report.get('same_chain_core_asset_ranking') or [])}{ranking('瓶颈环节榜', report.get('bottleneck_ranking') or [])}{ranking('利润捕获榜', report.get('profit_capture_ranking') or [])}
{role(1,'资金逻辑分析',capital,f"<p>事件：{esc(speculation.get('event'))}</p><p>交易逻辑：{esc(speculation.get('logic'))}</p>")}
{role(2,'产品路径映射',product,path_html)}{role(3,'完整 BOM',bom,bom_table)}{role(4,'瓶颈分析',bottleneck)}{role(5,'利润流向分析',profit,profit_table)}
<section class='role'><header><b>06</b><div><small>FUND MANAGER VERDICT</small><h2>基金经理裁决</h2></div></header><p class='lead'>{esc(judge.get('conclusion'))}</p><div class='challenge-grid'>{conflicts}</div>{citations(judge.get('evidence_ids'))}</section>
<section class='evidence-section'><h2>完整证据</h2><div class='evidence'>{evidence_html}</div></section>
</main></body></html>"""


def write_summary(path: Path, *, subject: str, code: str, metrics: dict[str, Any], validation: dict[str, Any], artifact_dir: Path | None = None) -> None:
    lines = [
        f"研究对象：{subject} {code}", f"模型：{metrics['model']}",
        f"输入 tokens：{metrics['input_tokens']}", f"输出 tokens：{metrics['output_tokens']}",
        f"Web Search：{metrics['search_count']} 次", f"耗时：{metrics['duration_seconds']} 秒",
        f"估算成本：人民币 {metrics['cost_cny']:.4f} 元",
        f"证据数量：{validation['source_count']}（A/B级 {validation['a_b_source_count']}）",
        f"证据ID完整：{validation['all_evidence_ids_exist']}",
        f"三高公式正确：{validation['score_formula_valid']}",
        f"同链排名降序：{validation['ranking_descending']}",
        f"模型自审语义支持率：{validation['self_audited_semantic_support_rate']:.2%}",
        f"模型自审决策通过率（含正确拒绝的无证据说法）：{validation['self_audited_decision_pass_rate']:.2%}",
        f"正确拒绝的无证据说法：{validation['correctly_rejected_unsupported_claims']} 条",
        f"清理的冗余悬空证据ID：{len(validation.get('removed_redundant_dangling_evidence_ids') or [])} 处",
    ]
    if artifact_dir:
        lines.append(f"原始响应目录：{artifact_dir}")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", default="华正新材")
    parser.add_argument("--code", default="603186")
    parser.add_argument("--output-dir", type=Path, default=Path.home() / "Desktop")
    parser.add_argument("--repair-existing", type=Path)
    args = parser.parse_args()
    if args.repair_existing:
        envelope = json.loads(args.repair_existing.read_text(encoding="utf-8"))
        report = envelope["report"]
        removed = remove_redundant_dangling_evidence_ids(report)
        validation = validate_report(report)
        validation["removed_redundant_dangling_evidence_ids"] = removed
        envelope["validation"] = validation
        args.repair_existing.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
        args.repair_existing.with_suffix(".html").write_text(render_html(report), encoding="utf-8")
        write_summary(
            args.repair_existing.with_name(args.repair_existing.stem + "_成本摘要.txt"),
            subject=str(report.get("subject", {}).get("name") or args.subject),
            code=str(report.get("subject", {}).get("code") or args.code),
            metrics=envelope["metrics"], validation=validation,
        )
        print(json.dumps({"json": str(args.repair_existing), "html": str(args.repair_existing.with_suffix('.html')), "removed": removed, "validation": validation}, ensure_ascii=False))
        return 0
    prompt = load_prompt(args.subject, args.code)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"{args.subject}_单Agent产业链逆向研究_Luna_{stamp}"
    artifact_dir = ROOT / "artifacts" / "stock-research-single-agent" / stamp
    artifact_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

    report, raw, duration = call_luna(prompt)
    metrics = compute_metrics(raw, duration)
    removed_dangling_ids = remove_redundant_dangling_evidence_ids(report)
    report["meta"] = {**(report.get("meta") or {}), **metrics, "prompt": PROMPT_PATH.name}
    validation = validate_report(report)
    validation["removed_redundant_dangling_evidence_ids"] = removed_dangling_ids
    envelope = {"report": report, "metrics": metrics, "validation": validation}

    (artifact_dir / "raw_response.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    (artifact_dir / "report.json").write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    json_path = args.output_dir / f"{stem}.json"
    html_path = args.output_dir / f"{stem}.html"
    summary_path = args.output_dir / f"{stem}_成本摘要.txt"
    json_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    write_summary(summary_path, subject=args.subject, code=args.code, metrics=metrics, validation=validation, artifact_dir=artifact_dir)
    print(json.dumps({"json": str(json_path), "html": str(html_path), "summary": str(summary_path), "artifacts": str(artifact_dir), **metrics, **validation}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
