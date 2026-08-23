from __future__ import annotations

import html
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from trade_review_agent.auth_system import init_auth_db
from trade_review_agent.review.final_wang_agent.agent import extract_responses_text
from trade_review_agent.stock_research import (
    NormalizedSubject,
    create_job,
    finalize_report,
    get_job,
    get_report,
    init_schema,
    merge_role_into_board,
    merge_supplement_sources,
    normalize_sources,
    normalize_role_output_for_contract,
    run_job,
    validate_role_output,
    validate_report,
)


def main() -> int:
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise SystemExit("OPENAI_API_KEY is required")
    desktop = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"华正新材_产业链逆向研究_Luna_{stamp}"
    debug_dir = desktop / f"{stem}_原始响应"
    os.environ["STOCK_RESEARCH_DEBUG_DIR"] = str(debug_dir)

    with tempfile.TemporaryDirectory(prefix="stock-research-live-", ignore_cleanup_errors=True) as temp_dir:
        db_path = Path(temp_dir) / "auth.sqlite"
        init_auth_db(db_path)
        init_schema(db_path)
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with sqlite3.connect(db_path) as conn:
            admin_id = int(conn.execute(
                """INSERT INTO users(phone,username,email,email_verified,password_hash,password_salt,role,status,invite_code,created_at)
                   VALUES('live-admin','liveadmin','live-admin@example.com',1,'x','y','admin','active','LIVEADMIN',?)""",
                (now,),
            ).lastrowid)
        job = create_job(
            db_path,
            user={"id": admin_id, "role": "admin"},
            payload={"type": "stock", "value": "华正新材"},
            provider_name="luna",
            start=False,
        )
        run_job(db_path, job["id"], allow_provider_retry=False)
        completed = get_job(db_path, job["id"], user_id=admin_id)
        if completed["status"] != "completed":
            failure_path = desktop / f"{stem}_失败.json"
            failure_path.write_text(json.dumps(completed, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"status": completed["status"], "error_code": completed["error_code"], "error": completed["error_message"], "failure_file": str(failure_path), "debug_dir": str(debug_dir)}, ensure_ascii=False))
            return 1
        record = get_report(db_path, completed["report_id"], user_id=admin_id)
        report = record["report"]

    json_path = desktop / f"{stem}.json"
    summary_path = desktop / f"{stem}_成本摘要.txt"
    html_path = desktop / f"{stem}.html"
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    meta = report.get("meta") or {}
    summary = (
        f"研究对象：华正新材 603186\n"
        f"引擎：{meta.get('provider', 'luna')}\n"
        f"输入 tokens：{meta.get('input_tokens', 0)}\n"
        f"输出 tokens：{meta.get('output_tokens', 0)}\n"
        f"Web Search 调用：{meta.get('search_count', 0)}\n"
        f"实际估算成本：人民币 {float(meta.get('cost_cny', 0)):.4f} 元\n"
        f"证据数量：{len(report.get('evidence') or [])}\n"
    )
    summary_path.write_text(summary, encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    print(json.dumps({
        "status": "completed",
        "input_tokens": meta.get("input_tokens", 0),
        "output_tokens": meta.get("output_tokens", 0),
        "search_count": meta.get("search_count", 0),
        "cost_cny": meta.get("cost_cny", 0),
        "source_count": len(report.get("evidence") or []),
        "json_file": str(json_path),
        "summary_file": str(summary_path),
        "html_file": str(html_path),
    }, ensure_ascii=False))
    return 0


def render_html(report: dict) -> str:
    def esc(value: object) -> str:
        return html.escape(str(value or ""))

    evidence_map = {str(item.get("id")): item for item in report.get("evidence") or []}

    def citations(ids: object) -> str:
        links = []
        for evidence_id in ids if isinstance(ids, list) else []:
            item = evidence_map.get(str(evidence_id))
            if item:
                links.append(f"<a class='cite' href='{esc(item.get('url'))}' target='_blank' rel='noreferrer'>来源：{esc(item.get('title'))}</a>")
        return "".join(links)

    def text(value: object) -> str:
        if value in (None, ""):
            return "—"
        if isinstance(value, list):
            return "、".join(text(item) for item in value)
        if isinstance(value, dict):
            return esc(value.get("name") or value.get("label") or value.get("summary") or "—")
        return esc(value)

    def facts(items: list[tuple[str, object]]) -> str:
        visible = [(label, value) for label, value in items if value not in (None, "", [])]
        return "<dl class='facts'>" + "".join(f"<div><dt>{esc(label)}</dt><dd>{text(value)}</dd></div>" for label, value in visible) + "</dl>" if visible else ""

    def role(index: str, title: str, value: dict, body: str = "") -> str:
        return (
            f"<section class='role'><header><b>{index}</b><div><small>SPECIALIST REVIEW</small><h2>{esc(title)}</h2></div></header>"
            f"<p class='summary'>{esc(value.get('summary') or '证据不足，暂不下结论')}</p>{body}"
            f"<div class='cites'>{citations(value.get('evidence_ids'))}</div></section>"
        )

    capital = report.get("capital_logic") or {}
    speculation = capital.get("speculation_json") or {}
    product = report.get("product_path") or {}
    bom = report.get("bom") or {}
    bottleneck = report.get("bottleneck") or {}
    profit = report.get("profit_flow") or {}
    judge = report.get("judge") or {}
    path = "<div class='path'>" + "".join(f"<span>{esc(item)}</span>" for item in product.get("path") or []) + "</div>"
    bom_rows = "".join(
        "<tr>" + "".join(f"<td>{text(cell)}</td>" for cell in (
            item.get("node"), item.get("chain_position"), item.get("a_share_companies"),
            item.get("value_trend"), item.get("evidence_confidence"),
        )) + "</tr>" for item in bom.get("items") or []
    )
    bom_table = f"<div class='table'><table><thead><tr><th>BOM 节点</th><th>产业位置</th><th>对应 A 股</th><th>价值变化</th><th>可信度</th></tr></thead><tbody>{bom_rows}</tbody></table></div>"
    profit_rows = "".join(
        "<tr>" + "".join(f"<td>{text(cell)}</td>" for cell in (
            item.get("node"), f"{item.get('stars', '—')} 星", item.get("classification"),
            item.get("pricing_power"), item.get("profit_elasticity"),
        )) + "</tr>" for item in profit.get("ranked_nodes") or []
    )
    profit_table = f"<div class='table'><table><thead><tr><th>环节</th><th>等级</th><th>定位</th><th>定价权</th><th>利润弹性</th></tr></thead><tbody>{profit_rows}</tbody></table></div>"
    conflict_cards = "".join(
        f"<article class='conflict'><small>争议 {index}</small><p>{esc(item.get('issue') if isinstance(item, dict) else item)}</p>"
        f"<strong>{esc(item.get('resolution') if isinstance(item, dict) else '')}</strong>"
        f"{citations(item.get('evidence_ids') if isinstance(item, dict) else [])}</article>"
        for index, item in enumerate(judge.get("role_conflicts") or [], 1)
    )
    judge_body = f"<div class='judge'><h3>最终裁决</h3><p>{esc(judge.get('conclusion'))}</p></div><div class='conflicts'>{conflict_cards}</div>"
    score = report.get("input_stock_score") or {}
    def ranking(title: str, rows: list[dict]) -> str:
        content = "".join(
            f"<li><b>{index}</b><div><strong>{esc(item.get('name'))}{' · ' + esc(item.get('code')) if item.get('code') else ''}</strong>"
            f"<span>{esc(item.get('position') or item.get('industry_position'))} · {esc(item.get('reason'))}</span></div>{citations(item.get('evidence_ids'))}</li>"
            for index, item in enumerate(rows, 1)
        )
        return f"<section class='ranking'><h2>{esc(title)}</h2><ol>{content or '<li>证据不足，暂不排名</li>'}</ol></section>"
    evidence = "".join(
        f"<a href='{esc(item.get('url'))}' target='_blank'><b>{esc(item.get('id'))} · {esc(item.get('source_tier'))}级</b><span>{esc(item.get('title'))}</span><em>{esc(item.get('publisher'))}</em></a>"
        for item in report.get("evidence") or []
    )
    subject = report.get("subject") if isinstance(report.get("subject"), dict) else {}
    meta = report.get("meta") or {}
    return f"""<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>华正新材产业链逆向研究</title>
    <style>body{{margin:0;background:#080a09;color:#eee8db;font-family:Arial,'Microsoft YaHei';line-height:1.7}}main{{max-width:1160px;margin:auto;padding:48px 22px}}.hero,.role,.score,.ranking,.evidence-section{{border:1px solid #30352e;border-radius:18px;padding:24px;background:#111410}}.hero{{border-color:#544723;background:radial-gradient(circle at 90% 0,#302816 0,transparent 35%),#12140f}}h1{{font-size:42px;margin:8px 0}}h2,.hero>span,.role small{{color:#d4af43}}.meta{{color:#7d837c;font-size:13px}}.dashboard{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:16px 0}}.dashboard article{{border:1px solid #30352e;border-radius:14px;padding:18px;background:#10130f}}.dashboard article:last-child{{grid-column:1/-1}}.dashboard small{{color:#d4af43}}.roles{{display:grid;gap:16px;margin:18px 0}}.role>header{{display:flex;gap:14px;align-items:center;border-bottom:1px solid #2c302a;padding-bottom:12px}}.role>header>b{{display:grid;place-items:center;width:42px;height:42px;border:1px solid #665629;border-radius:50%;color:#d4af43}}.role h2{{margin:0;color:#eee8db}}.summary{{font-size:17px}}.facts{{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#30332d;border:1px solid #30332d;border-radius:11px;overflow:hidden}}.facts div{{background:#0c0f0c;padding:12px}}dt{{color:#b59a49;font-size:12px}}dd{{margin:4px 0 0}}.path{{display:flex;gap:26px;overflow:auto;padding:14px 2px}}.path span{{position:relative;white-space:nowrap;border:1px solid #574b25;border-radius:9px;padding:10px}}.path span:not(:last-child):after{{content:'→';position:absolute;right:-20px;color:#b99738}}.table{{overflow:auto;border:1px solid #30352e;border-radius:11px}}table{{width:100%;min-width:720px;border-collapse:collapse}}th,td{{text-align:left;padding:11px;border-top:1px solid #292d27}}th{{color:#d4af43;background:#17180f}}.cite{{display:inline-block;color:#d8bd69;border:1px solid #5e512a;border-radius:99px;padding:2px 8px;margin:4px;text-decoration:none;font-size:11px}}.conflicts{{display:grid;grid-template-columns:1fr 1fr;gap:9px}}.conflict{{border:1px solid #504526;border-radius:11px;padding:12px}}.conflict strong{{color:#b9bdb5}}.score{{display:flex;align-items:center;gap:22px;margin:16px 0}}.score strong{{font-size:55px;color:#d4af43}}.ranking{{margin:14px 0}}ol{{padding:0;list-style:none}}.ranking li{{display:grid;grid-template-columns:34px 1fr auto;gap:10px;padding:13px;border-top:1px solid #2a2e28}}.ranking li>b{{color:#d4af43;font-size:20px}}.ranking li div{{display:grid}}.ranking li span{{color:#969c95}}.evidence{{display:grid;gap:8px}}.evidence>a{{display:grid;grid-template-columns:90px 1fr auto;color:#eee;text-decoration:none;border:1px solid #2c302a;border-radius:10px;padding:12px}}.evidence a b{{color:#d4af43}}.evidence em{{color:#888;font-style:normal}}@media(max-width:650px){{.dashboard,.facts,.conflicts{{grid-template-columns:1fr}}.dashboard article:last-child{{grid-column:auto}}h1{{font-size:32px}}.ranking li{{grid-template-columns:28px 1fr}}.ranking .cite{{grid-column:2}}.evidence>a{{grid-template-columns:1fr}}}}</style>
    <main><header class='hero'><span>SIX-ROLE REVERSE RESEARCH</span><h1>{esc(subject.get('name'))} · {esc(subject.get('code'))}</h1><p>{esc(report.get('headline'))}</p><div class='meta'>引擎 {esc(meta.get('provider'))} · Skill {esc(str(meta.get('skill_version') or '')[:10])} · {len(evidence_map)} 条证据 · 成本 ¥{float(meta.get('cost_cny') or 0):.2f}</div></header>
    <div class='dashboard'><article><small>资金为什么炒</small><p>{esc(capital.get('summary'))}</p></article><article><small>利润真正流向</small><p>{esc(profit.get('summary'))}</p></article><article><small>当前产业瓶颈</small><p>{esc(bottleneck.get('summary'))}</p></article><article><small>输入对象定位</small><p>{esc((report.get('positioning') or {}).get('summary'))}</p></article><article><small>最重要证伪信号</small><p>{esc('；'.join(judge.get('disconfirming_signals') or []))}</p></article></div>
    <section class='score'><div><h2>输入股票三高评分</h2><strong>{esc(score.get('core_score'))}</strong><p>壁垒 {esc(score.get('barrier'))} · 利润 {esc(score.get('profit'))} · 成长 {esc(score.get('growth'))}</p></div><small>不是上涨概率或买入评级</small></section>
    {ranking('同产业链核心资产', report.get('same_chain_core_asset_ranking') or [])}{ranking('瓶颈环节榜', report.get('bottleneck_ranking') or [])}{ranking('利润捕获榜', report.get('profit_capture_ranking') or [])}
    <div class='roles'>{role('01','资金逻辑分析',capital,facts([('事件',speculation.get('event')),('交易逻辑',speculation.get('logic')),('行业趋势',speculation.get('industry_trend')),('证据可信度',speculation.get('evidence_confidence'))]))}{role('02','产品路径映射',product,path)}{role('03','产业 BOM 拆解',bom,bom_table)}{role('04','瓶颈分析',bottleneck,facts([('当前瓶颈',bottleneck.get('current')),('瓶颈类型',bottleneck.get('type')),('谁先涨价',bottleneck.get('first_price_response')),('扩产难度',bottleneck.get('expansion_difficulty')),('利润兑现',bottleneck.get('profit_realization')),('下一瓶颈',bottleneck.get('next_bottleneck'))]))}{role('05','利润流向分析',profit,profit_table)}{role('06','基金经理裁决',judge,judge_body)}</div>
    <section class='evidence-section'><h2>完整证据</h2><div class='evidence'>{evidence}</div></section></main></html>"""


def replay_debug_directory(debug_dir: Path) -> int:
    files = sorted(debug_dir.glob("luna_response_*.json"))
    if len(files) < 7:
        raise SystemExit("需要至少7份 Luna 原始响应")
    responses = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    outputs = [json.loads(extract_responses_text(item)) for item in responses]
    sources = normalize_sources(outputs[0].get("evidence"))
    board = {
        "input_stocks": [{"type": "stock", "name": "华正新材", "code": "603186"}],
        "subject": {"type": "stock", "name": "华正新材", "code": "603186"},
        "facts": outputs[0].get("facts") or [], "current_catalysts": [], "product_paths": [],
        "bom_tree": {}, "bottlenecks": [], "profit_flow": [], "conflicts": [],
        "evidence_confidence": {},
        "evidence_gaps": outputs[0].get("evidence_gaps") or [],
    }
    role_markers = {
        "capital_logic": "speculation_logic",
        "product_path": "real_product_line",
        "bom": "bom_tree",
        "bottleneck": "current_bottleneck",
        "profit_flow": "ranked_nodes",
    }
    roles: dict[str, dict] = {}
    supplements: list[dict] = []
    judge: dict | None = None
    for output in outputs[1:]:
        matched = next((role for role, marker in role_markers.items() if marker in output), None)
        if matched:
            roles[matched] = output  # a later same-role response is its contract repair
        elif "headline" in output and "judge" in output:
            judge = output
        elif "evidence" in output and "facts" in output:
            supplements.append(output)
    missing_roles = [role for role in role_markers if role not in roles]
    if missing_roles or judge is None:
        raise SystemExit(f"原始响应不完整，缺少角色={missing_roles} judge={judge is not None}")
    for supplement in supplements:
        sources = merge_supplement_sources(sources, normalize_sources(supplement.get("evidence")))
        board.setdefault("supplemental_facts", []).extend(supplement.get("facts") or [])
        board["supplement_search_completed"] = True
    for role in role_markers:
        output = normalize_role_output_for_contract(roles[role], sources)
        validate_role_output(role, output, sources)
        roles[role] = output
        merge_role_into_board(board, role, output)
    usage = {"input_tokens": 0, "output_tokens": 0, "search_count": 0, "cost_cny": 0.0}
    for response in responses:
        item_usage = response.get("usage") or {}
        input_tokens = int(item_usage.get("input_tokens") or 0)
        output_tokens = int(item_usage.get("output_tokens") or 0)
        searches = sum(1 for item in response.get("output", []) if isinstance(item, dict) and item.get("type") == "web_search_call")
        usage["input_tokens"] += input_tokens
        usage["output_tokens"] += output_tokens
        usage["search_count"] += searches
        usage["cost_cny"] += (input_tokens * 0.20 / 1_000_000 + output_tokens * 1.20 / 1_000_000 + searches * 0.01) * 7.2
    report = finalize_report(
        judge, NormalizedSubject("stock", "华正新材", "603186"),
        board, roles, sources, "luna", usage,
    )
    validate_report(report)
    stem = debug_dir.name.removesuffix("_原始响应")
    desktop = debug_dir.parent
    json_path = desktop / f"{stem}.json"
    summary_path = desktop / f"{stem}_成本摘要.txt"
    html_path = desktop / f"{stem}.html"
    record = {"provider": "luna", "report": report}
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(
        f"研究对象：华正新材 603186\n引擎：luna\n输入 tokens：{usage['input_tokens']}\n"
        f"输出 tokens：{usage['output_tokens']}\nWeb Search 调用：{usage['search_count']}\n"
        f"实际估算成本：人民币 {usage['cost_cny']:.4f} 元\n证据数量：{len(sources)}\n",
        encoding="utf-8",
    )
    html_path.write_text(render_html(report), encoding="utf-8")
    print(json.dumps({"status": "completed", **usage, "source_count": len(sources), "json_file": str(json_path), "summary_file": str(summary_path), "html_file": str(html_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--replay-debug":
        raise SystemExit(replay_debug_directory(Path(sys.argv[2])))
    raise SystemExit(main())
