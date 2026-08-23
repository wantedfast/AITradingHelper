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
    normalize_sources,
    run_job,
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

    def section(title: str, key: str) -> str:
        value = report.get(key) if isinstance(report.get(key), dict) else {}
        ids = " ".join(f"<i>{esc(item)}</i>" for item in value.get("evidence_ids", []) or [])
        return f"<article><small>{esc(title)}</small><p>{esc(value.get('summary') or '证据不足')}</p><div>{ids}</div></article>"

    score = report.get("input_stock_score") or {}
    ranking = "".join(
        f"<li><b>{index}. {esc(item.get('name'))}</b><span>{esc(item.get('position'))} · {esc(item.get('reason'))}</span></li>"
        for index, item in enumerate(report.get("core_asset_ranking") or [], 1)
    )
    evidence = "".join(
        f"<a href='{esc(item.get('url'))}' target='_blank'><b>{esc(item.get('id'))} · {esc(item.get('source_tier'))}级</b><span>{esc(item.get('title'))}</span><em>{esc(item.get('publisher'))}</em></a>"
        for item in report.get("evidence") or []
    )
    subject = report.get("subject") if isinstance(report.get("subject"), dict) else {}
    return f"""<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>华正新材产业链逆向研究</title>
    <style>body{{margin:0;background:#080a09;color:#eee8db;font-family:Arial,'Microsoft YaHei';line-height:1.7}}main{{max-width:1100px;margin:auto;padding:48px 22px}}header{{border:1px solid #544723;border-radius:20px;padding:30px;background:#12140f}}h1{{font-size:42px;margin:8px 0}}header span,article small,h2{{color:#d4af43}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:16px 0}}article,section{{border:1px solid #30352e;border-radius:15px;padding:20px;background:#111410}}article p{{font-size:17px}}i{{font-style:normal;border:1px solid #5e512a;color:#d7bc65;border-radius:20px;padding:2px 7px;margin-right:6px}}.score{{display:flex;align-items:center;gap:22px}}.score strong{{font-size:55px;color:#d4af43}}li{{display:grid;padding:12px;border-top:1px solid #2a2e28}}li span{{color:#9aa099}}.evidence{{display:grid;gap:8px}}.evidence a{{display:grid;grid-template-columns:90px 1fr auto;color:#eee;text-decoration:none;border:1px solid #2c302a;border-radius:10px;padding:12px}}.evidence a b{{color:#d4af43}}.evidence em{{color:#888;font-style:normal}}@media(max-width:650px){{.grid{{grid-template-columns:1fr}}h1{{font-size:32px}}.evidence a{{grid-template-columns:1fr}}}}</style>
    <main><header><span>SIX-ROLE REVERSE RESEARCH</span><h1>{esc(subject.get('name'))} · {esc(subject.get('code'))}</h1><p>{esc(report.get('headline'))}</p></header>
    <div class='grid'>{section('资金为什么炒','capital_logic')}{section('利润真正流向','profit_flow')}{section('当前产业瓶颈','bottleneck')}{section('输入对象定位','positioning')}{section('最重要证伪信号','judge')}</div>
    <section class='score'><div><h2>三高综合评分</h2><strong>{esc(score.get('core_score'))}</strong><p>壁垒 {esc(score.get('barrier'))} · 利润 {esc(score.get('profit'))} · 成长 {esc(score.get('growth'))}</p></div><small>不是上涨概率或买入评级</small></section>
    <section><h2>同产业链核心资产</h2><ol>{ranking}</ol></section><section><h2>完整证据</h2><div class='evidence'>{evidence}</div></section></main></html>"""


def replay_debug_directory(debug_dir: Path) -> int:
    files = sorted(debug_dir.glob("luna_response_*.json"))
    if len(files) < 7:
        raise SystemExit("需要至少7份 Luna 原始响应")
    responses = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    outputs = [json.loads(extract_responses_text(item)) for item in responses]
    sources = normalize_sources(outputs[0].get("evidence"))
    board = {
        "subject": {"type": "stock", "name": "华正新材", "code": "603186"},
        "facts": outputs[0].get("facts") or [], "hypotheses": [], "conflicts": [],
        "evidence_gaps": outputs[0].get("evidence_gaps") or [],
    }
    role_names = ("capital_logic", "product_path", "bom", "bottleneck", "profit_flow")
    roles = {}
    for role, output in zip(role_names, outputs[1:6]):
        roles[role] = output
        merge_role_into_board(board, role, output)
    judge_index = 6
    if len(outputs) >= 8:
        supplement = outputs[6]
        known = {item["id"] for item in sources}
        sources.extend(item for item in normalize_sources(supplement.get("evidence")) if item["id"] not in known)
        board["supplemental_facts"] = supplement.get("facts") or []
        board["supplement_search_completed"] = True
        judge_index = 7
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
        outputs[judge_index], NormalizedSubject("stock", "华正新材", "603186"),
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
