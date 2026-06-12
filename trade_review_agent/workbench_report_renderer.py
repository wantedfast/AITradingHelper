from __future__ import annotations

from html import escape
from typing import Any


def render_workbench_report(data: dict[str, Any]) -> str:
    company = _d(data.get("company"))
    hero = _d(data.get("hero"))
    profit = _d(data.get("profit_flow"))
    gap = _d(data.get("expectation_gap"))
    trade = _d(data.get("trade_review"))
    action = _d(data.get("next_action"))
    memos = _d(data.get("deep_memos"))
    diagnostics = _d(data.get("generation_diagnostics"))

    name = _s(company.get("name"), "个股")
    subtitle = _s(company.get("subtitle"), "")
    claims = _list(hero.get("claims"))[:4]
    tags = _list(hero.get("tags"))[:5]
    profit_items = _list(profit.get("items"))[:6]
    logic = _list(data.get("logic_tree"))[:6]

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(name)} AI 复盘分析</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #070b0c;
      --panel: #101718;
      --panel-2: #151d1e;
      --line: #283536;
      --gold: #f2cf67;
      --gold-2: #b99034;
      --cyan: #6fd5df;
      --green: #82d38a;
      --red: #ff8d7b;
      --text: #f2eee0;
      --muted: #aeb8b5;
      --soft: #d9c897;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at 15% 0%, rgba(111, 213, 223, .16), transparent 28%),
        radial-gradient(circle at 82% 5%, rgba(242, 207, 103, .12), transparent 24%),
        linear-gradient(90deg, rgba(111, 213, 223, .045) 1px, transparent 1px),
        linear-gradient(0deg, rgba(111, 213, 223, .035) 1px, transparent 1px),
        var(--bg);
      background-size: auto, auto, 48px 48px, 48px 48px, auto;
      color: var(--text);
      font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
      letter-spacing: 0;
    }}
    .page {{ width: min(1200px, calc(100vw - 36px)); margin: 0 auto; padding: 36px 0 64px; }}
    .topbar {{ display: flex; align-items: center; justify-content: space-between; color: var(--muted); font-size: 15px; margin-bottom: 26px; }}
    .brand {{ color: var(--gold); font-weight: 800; font-size: 20px; }}
    .nav {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    .nav span {{ border: 1px solid rgba(242,207,103,.28); border-radius: 999px; padding: 8px 12px; color: var(--soft); }}
    .hero {{ min-height: 520px; display: grid; grid-template-columns: 1.02fr .98fr; gap: 26px; align-items: stretch; border-bottom: 1px solid rgba(242,207,103,.18); padding-bottom: 34px; }}
    .hero-left {{ display: flex; flex-direction: column; justify-content: center; padding: 34px 0; }}
    .kicker, .eyebrow {{ color: var(--cyan); font-size: 17px; font-weight: 900; letter-spacing: .12em; text-transform: uppercase; }}
    h1 {{ margin: 16px 0 0; font-size: clamp(56px, 8vw, 104px); line-height: .95; font-weight: 900; letter-spacing: -.05em; }}
    .ticker {{ margin-top: 18px; color: var(--soft); font-size: 25px; font-weight: 800; }}
    .lead {{ margin-top: 22px; color: #dbe1dc; font-size: 18px; line-height: 1.8; max-width: 720px; }}
    .rating-row {{ display: flex; gap: 14px; margin-top: 30px; flex-wrap: wrap; }}
    .rating, .tag {{ border: 1px solid rgba(242,207,103,.34); background: rgba(242,207,103,.08); border-radius: 8px; padding: 12px 16px; color: var(--gold); font-size: 18px; font-weight: 900; }}
    .tag {{ color: var(--text); background: rgba(16,23,24,.86); }}
    .hero-card, .section {{ border: 1px solid var(--line); background: linear-gradient(180deg, rgba(21,29,30,.96), rgba(13,19,20,.96)); border-radius: 8px; box-shadow: 0 24px 60px rgba(0,0,0,.24); }}
    .hero-card {{ padding: 34px; display: grid; align-content: center; }}
    .hero-card h2, .section h2 {{ margin: 0 0 16px; font-size: 32px; color: var(--gold); }}
    .claim-list {{ display: grid; gap: 18px; margin-top: 20px; }}
    .claim {{ display: grid; grid-template-columns: 10px 1fr; gap: 14px; align-items: start; color: #f6efd5; font-size: 24px; line-height: 1.35; font-weight: 900; }}
    .dot {{ width: 10px; height: 10px; margin-top: 12px; border-radius: 50%; background: var(--cyan); box-shadow: 0 0 18px rgba(111,213,223,.75); }}
    .hero-note {{ margin-top: 26px; color: var(--muted); font-size: 17px; line-height: 1.75; }}
    .section {{ margin-top: 28px; padding: 28px; }}
    .section-head {{ display: flex; justify-content: space-between; gap: 20px; align-items: end; margin-bottom: 22px; }}
    .section-head p, .muted {{ margin: 0; color: var(--muted); font-size: 16px; line-height: 1.65; }}
    .pill {{ border: 1px solid rgba(111,213,223,.35); color: var(--cyan); border-radius: 999px; padding: 8px 13px; font-size: 14px; font-weight: 900; white-space: nowrap; }}
    .sankey {{ display: grid; grid-template-columns: 180px 1fr 230px; gap: 24px; align-items: center; min-height: 310px; }}
    .source-box, .target-box {{ border: 1px solid rgba(242,207,103,.28); background: rgba(242,207,103,.08); border-radius: 8px; padding: 20px; }}
    .source-box strong {{ display: block; font-size: 28px; color: var(--gold); margin-bottom: 8px; }}
    .flow-list {{ display: grid; gap: 12px; }}
    .flow {{ display: grid; grid-template-columns: 120px 1fr 58px; gap: 12px; align-items: center; font-size: 17px; color: #e9eadf; }}
    .bar {{ height: 18px; background: #263132; border-radius: 999px; overflow: hidden; }}
    .fill {{ height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--gold-2), #ffe28a); }}
    .highlight .fill {{ background: linear-gradient(90deg, var(--cyan), #aaf4fb); box-shadow: 0 0 20px rgba(111,213,223,.35); }}
    .target-box {{ border-color: rgba(111,213,223,.44); background: rgba(111,213,223,.07); }}
    .target-box strong {{ display: block; color: var(--cyan); font-size: 30px; margin-bottom: 8px; }}
    .logic-row {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 14px; }}
    .logic-card {{ border: 1px solid rgba(111,213,223,.35); background: rgba(111,213,223,.06); border-radius: 8px; padding: 18px; min-height: 138px; }}
    .logic-card h3 {{ margin: 0 0 22px; font-size: 20px; }}
    .logic-card b {{ color: var(--gold); font-size: 34px; }}
    .expect-grid {{ display: grid; grid-template-columns: 1fr 210px 1fr; gap: 24px; align-items: stretch; }}
    .expect-box, .mini-card {{ border: 1px solid rgba(242,207,103,.22); background: rgba(242,207,103,.055); border-radius: 8px; padding: 20px; }}
    .expect-box h3, .mini-card h3 {{ margin: 0 0 14px; color: #f1d996; font-size: 22px; }}
    .expect-box ul, .list {{ margin: 0; padding-left: 20px; color: #d7ded9; line-height: 1.85; }}
    .gap-score {{ display: grid; place-items: center; text-align: center; border: 1px solid rgba(242,207,103,.44); background: rgba(242,207,103,.08); border-radius: 8px; }}
    .gap-score b {{ display: block; color: var(--gold); font-size: 56px; line-height: 1; }}
    .two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
    .three {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }}
    .metric {{ border: 1px solid rgba(242,207,103,.22); background: rgba(242,207,103,.06); border-radius: 8px; padding: 18px; }}
    .metric span {{ color: var(--muted); font-size: 14px; }}
    .metric b {{ display: block; color: var(--gold); font-size: 30px; margin-top: 8px; }}
    .status-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
    .alert {{ border: 1px solid rgba(255,141,123,.42); background: rgba(255,141,123,.08); border-radius: 8px; padding: 18px; }}
    .alert h3 {{ margin: 0 0 10px; color: var(--red); font-size: 22px; }}
    .kv {{ display: grid; grid-template-columns: 150px 1fr; gap: 10px; color: #d7ded9; line-height: 1.65; }}
    .kv b {{ color: var(--gold); }}
    .memo {{ white-space: pre-wrap; color: #d7ded9; line-height: 1.8; font-size: 16px; max-height: 520px; overflow: auto; }}
    .trade-table {{ width: 100%; border-collapse: collapse; }}
    .trade-table th, .trade-table td {{ border-bottom: 1px solid rgba(242,207,103,.14); padding: 12px 10px; text-align: left; }}
    .trade-table th {{ color: var(--gold); }}
    footer {{ margin-top: 24px; color: #73807b; font-size: 13px; }}
    @media (max-width: 980px) {{ .hero, .two, .sankey, .expect-grid {{ grid-template-columns: 1fr; }} .three, .logic-row {{ grid-template-columns: 1fr 1fr; }} }}
    @media (max-width: 640px) {{ .three, .logic-row {{ grid-template-columns: 1fr; }} h1 {{ font-size: 44px; }} }}
  </style>
</head>
<body>
  <main class="page">
    <header class="topbar">
      <div class="brand">Research Workbench</div>
      <nav class="nav"><span>AI 复盘分析</span><span>{escape(_s(company.get("code"), ""))}</span></nav>
    </header>

    <section class="hero">
      <div class="hero-left">
        <div class="kicker">{escape(_s(hero.get("kicker"), "这家公司值得研究吗？"))}</div>
        <h1>{escape(name)}</h1>
        <div class="ticker">{escape(subtitle)}</div>
        <div class="rating-row">
          <span class="rating">产业评级 {escape(_s(hero.get("industry_rating"), "待验证"))}</span>
          <span class="rating">投资评级 {escape(_s(hero.get("investment_rating"), "待验证"))}</span>
        </div>
        <div class="rating-row">{_tags(tags)}</div>
      </div>
      <div class="hero-card">
        <h2>一句话结论</h2>
        <div class="claim-list">{_claims(claims)}</div>
        <p class="hero-note">{escape(_s(hero.get("note"), ""))}</p>
      </div>
    </section>

    {_diagnostic_panel(diagnostics, trade)}

    <section class="section">
      <div class="section-head">
        <div><h2>利润流向图</h2><p>{escape(_s(profit.get("description"), "用利润池解释为什么是它。"))}</p></div>
        <span class="pill">核心模块</span>
      </div>
      <div class="sankey">
        <div class="source-box"><strong>{escape(_s(profit.get("value_pool"), "价值池待验证"))}</strong></div>
        <div class="flow-list">{_profit_rows(profit_items)}</div>
        <div class="target-box"><span>高亮位置</span><strong>{escape(name)}</strong><p class="muted">{escape(_s(profit.get("company_position"), ""))}<br>{escape(_s(profit.get("why_profit_flows_here"), ""))}</p></div>
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <div><h2>产业逻辑树</h2><p>把上涨逻辑拆成节点，显示每一步的确定性，暴露逻辑链最脆弱的位置。</p></div>
        <span class="pill">因果链</span>
      </div>
      <div class="logic-row">{_logic_cards(logic)}</div>
    </section>

    <section class="section">
      <div class="section-head">
        <div><h2>市场预期差</h2><p>股票上涨来自“比市场想得更好”，这里展示市场叙事和研究判断之间的差距。</p></div>
        <span class="pill">涨幅来源</span>
      </div>
      <div class="expect-grid">
        <div class="expect-box"><h3>市场认为</h3><ul>{_li(_list(gap.get("market_believes")))}</ul></div>
        <div class="gap-score"><div><b>{_score_text(gap.get("gap_score"))}</b><span>预期差</span></div></div>
        <div class="expect-box"><h3>实际情况</h3><ul>{_li(_list(gap.get("analyst_view")))}</ul></div>
      </div>
    </section>

    <section class="section">
      <div class="section-head"><div><h2>产业壁垒与验证清单</h2><p>这里保留 Agent 的关键判断，防止图表把研究结论过度压扁。</p></div><span class="pill">moat</span></div>
      <div class="three">
        <article class="mini-card"><h3>壁垒</h3><ul class="list">{_li(_list(_d(data.get("moat")).get("items")))}</ul></article>
        <article class="mini-card"><h3>财务验证</h3><ul class="list">{_li(_list(data.get("financial_validation")))}</ul></article>
        <article class="mini-card"><h3>反证点</h3><ul class="list">{_li(_list(data.get("disconfirming_signals")))}</ul></article>
      </div>
    </section>

    <section class="section">
      <div class="section-head"><div><h2>估值赔率、催化剂和下一步</h2><p>把“能不能研究”进一步落到“现在该怎么跟踪”。</p></div><span class="pill">decision</span></div>
      <div class="three">
        <article class="mini-card"><h3>估值赔率</h3><p class="muted">{escape(_s(data.get("valuation_odds"), "待验证"))}</p></article>
        <article class="mini-card"><h3>催化剂</h3><ul class="list">{_li(_list(data.get("catalysts")))}</ul></article>
        <article class="mini-card"><h3>复查条件</h3><ul class="list">{_li(_list(action.get("recheck_conditions")))}</ul></article>
      </div>
    </section>

    <footer>本报告由 AI 自动生成，用于研究训练，不构成投资建议。</footer>
  </main>
</body>
</html>"""


def _tags(items: list[Any]) -> str:
    return "".join(f'<span class="tag">{escape(_s(item, ""))}</span>' for item in items if _s(item, ""))


def _claims(items: list[Any]) -> str:
    if not items:
        items = ["结论待生成"]
    return "".join(f'<div class="claim"><span class="dot"></span><span>{escape(_s(item, ""))}</span></div>' for item in items)


def _profit_rows(items: list[Any]) -> str:
    rows = []
    if not items:
        return '<p class="muted">待验证</p>'
    for item in items:
        item = _d(item)
        pct = _optional_num(item.get("share_pct"))
        cls = "flow highlight" if item.get("highlight") else "flow"
        if pct is None:
            rows.append(
                f'<div class="{cls}"><span>{escape(_s(item.get("name"), "环节"))}</span>'
                '<div class="bar"></div><b>待验证</b></div>'
            )
            continue
        pct = max(0, min(100, pct))
        rows.append(
            f'<div class="{cls}"><span>{escape(_s(item.get("name"), "环节"))}</span><div class="bar"><div class="fill" style="width:{pct:.1f}%"></div></div><b>{pct:.0f}%</b></div>'
        )
    return "".join(rows)


def _logic_cards(items: list[Any]) -> str:
    rows = []
    if not items:
        return '<article class="logic-card"><h3>尚未生成</h3><b>待验证</b></article>'
    for item in items:
        item = _d(item)
        certainty = _optional_num(item.get("certainty_pct"))
        certainty_text = f"{max(0, min(100, certainty)):.0f}%" if certainty is not None else "待验证"
        rows.append(
            f'<article class="logic-card"><h3>{escape(_s(item.get("node"), "逻辑节点"))}</h3>'
            f"<b>{certainty_text}</b></article>"
        )
    return "".join(rows)


def _metric(label: str, value: str) -> str:
    return f'<div class="metric"><span>{escape(label)}</span><b>{escape(value)}</b></div>'


def _diagnostic_panel(diagnostics: dict[str, Any], trade: dict[str, Any]) -> str:
    status = _s(diagnostics.get("status"), "unknown")
    errors = _list(diagnostics.get("errors"))
    timings = _d(diagnostics.get("timings"))
    token_usage = _d(diagnostics.get("token_usage"))
    cost = _d(token_usage.get("cost_estimate"))
    llm_calls = _list(diagnostics.get("llm_calls"))
    cache = _d(diagnostics.get("cache_diagnostics"))
    rows = _list(trade.get("rows"))
    timing_items = [
        ("Total", timings.get("total_report_generation_seconds")),
        ("行情拉取", timings.get("market_fetch_seconds")),
        ("Workbench Agents", timings.get("workbench_agents_seconds")),
        ("交易执行", timings.get("trade_execution_seconds")),
        ("交易执行 LLM", timings.get("trade_execution_llm_seconds")),
        ("V3 Pipeline", timings.get("v3_pipeline_seconds")),
        ("Presenter", timings.get("presenter_seconds")),
        ("Analysis", timings.get("analysis_seconds")),
        ("Write", timings.get("write_artifacts_seconds")),
    ]
    timing_html = "".join(
        f"<div><b>{escape(label)}</b><span>{_format_seconds(value)}</span></div>"
        for label, value in timing_items
        if value not in (None, "")
    )
    token_html = "".join(
        [
            f"<div><b>LLM calls</b><span>{_num(token_usage.get('observed_call_count'), 0):.0f} observed / {_num(token_usage.get('missing_usage_call_count'), 0):.0f} missing usage</span></div>",
            f"<div><b>Actual tokens</b><span>{_num(token_usage.get('actual_total_tokens'), 0):.0f} total ({_num(token_usage.get('actual_input_tokens'), 0):.0f} in / {_num(token_usage.get('actual_output_tokens'), 0):.0f} out)</span></div>",
            f"<div><b>Estimated tokens</b><span>{_num(token_usage.get('estimated_total_tokens'), 0):.0f}</span></div>",
            f"<div><b>Actual cost</b><span>${_num(cost.get('usd'), 0):.4f} / RMB {_num(cost.get('cny'), 0):.2f}</span></div>",
            f"<div><b>Estimated cost</b><span>${_num(cost.get('estimated_usd'), 0):.4f} / RMB {_num(cost.get('estimated_cny'), 0):.2f}</span></div>",
            f"<div><b>Cache</b><span>hit={escape(_s(cache.get('cache_hit'), 'False'))} stale={escape(_s(cache.get('cache_stale'), 'False'))}</span></div>",
        ]
    )
    call_html = _llm_call_rows(llm_calls)
    error_html = _li(errors) if errors else "<li>未记录到 Agent 错误。</li>"
    return f"""
    <section class="section">
      <div class="section-head">
        <div><h2>生成状态</h2><p>如果 AI 供应商失败，报告会保留交易事实和错误原因，避免生成空报告。</p></div>
        <span class="pill">{escape(status)}</span>
      </div>
      <div class="status-grid">
        <article class="alert">
          <h3>失败或降级原因</h3>
          <ul class="list">{error_html}</ul>
        </article>
        <article class="mini-card">
          <h3>环节耗时</h3>
          <div class="kv">{timing_html or '<div><b>暂无</b><span>未记录</span></div>'}</div>
        </article>
      </div>
      <div class="status-grid" style="margin-top:18px">
        <article class="mini-card">
          <h3>Token & Cost</h3>
          <div class="kv">{token_html}</div>
        </article>
        <article class="mini-card">
          <h3>LLM Calls</h3>
          <div class="kv">{call_html or '<div><b>None</b><span>not recorded</span></div>'}</div>
        </article>
      </div>
      <div style="margin-top:18px">
        <h2>交易记录</h2>
        <table class="trade-table"><thead><tr><th>日期</th><th>方向</th><th>价格</th><th>数量</th><th>金额</th></tr></thead><tbody>{_trade_rows(rows)}</tbody></table>
      </div>
    </section>
"""


def _llm_call_rows(items: list[Any]) -> str:
    rows = []
    for item in items[:8]:
        item = _d(item)
        stage = _s(item.get("stage"), "unknown")
        status = _s(item.get("status"), "unknown")
        tokens = _num(item.get("actual_total_tokens") or item.get("estimated_total_tokens"), 0)
        seconds = _format_seconds(item.get("seconds"))
        suffix = " actual" if _num(item.get("actual_total_tokens"), 0) else " estimated"
        flags = []
        if item.get("fallback_used"):
            flags.append("fallback")
        if item.get("cache_hit"):
            flags.append("cache")
        if item.get("retry_after"):
            flags.append(f"retry_after={_s(item.get('retry_after'), '')}")
        flag_text = f" | {', '.join(flags)}" if flags else ""
        rows.append(
            f"<div><b>{escape(stage)}</b><span>{escape(status)} | {seconds} | {tokens:.0f}{suffix}{escape(flag_text)}</span></div>"
        )
    return "".join(rows)


def _format_seconds(value: Any) -> str:
    try:
        return f"{float(value):.2f}s"
    except Exception:
        return "未记录"


def _trade_rows(items: list[Any]) -> str:
    if not items:
        return '<tr><td colspan="5">交易记录待识别</td></tr>'
    rows = []
    for item in items:
        item = _d(item)
        trade_date = _s(item.get("date") or item.get("trade_date"), "")
        rows.append(
            f"<tr><td>{escape(trade_date[:10])}</td><td>{escape(_s(item.get('side'), ''))}</td><td>{_num(item.get('price'), 0):.3f}</td><td>{_num(item.get('quantity'), 0):.0f}</td><td>{_num(item.get('amount'), 0):.2f}</td></tr>"
        )
    return "".join(rows)


def _li(items: list[Any]) -> str:
    if not items:
        items = ["待验证"]
    return "".join(f"<li>{escape(_s(item, '待验证'))}</li>" for item in items)


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [item for item in value if item not in (None, "", [], {})]
    if isinstance(value, tuple):
        return [item for item in value if item not in (None, "", [], {})]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _s(value: Any, fallback: str) -> str:
    if value not in (None, "", [], {}):
        return str(value)
    return fallback


def _num(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(fallback)


def _int(value: Any, fallback: int) -> int:
    return int(round(_num(value, fallback)))


def _optional_num(value: Any) -> float | None:
    if value in (None, "", [], {}, "missing", "pending", "pending verification", "待验证", "尚未生成"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _score_text(value: Any) -> str:
    score = _optional_num(value)
    return f"{score:.0f}" if score is not None else "待验证"
