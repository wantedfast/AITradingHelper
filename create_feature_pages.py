from pathlib import Path

base = Path("frontend-preview")
index = base / "index.html"
s = index.read_text(encoding="utf-8")
s = s.replace('class="feature-card" href="/v2/">\n            <div class="feature-preview review-preview">', 'class="feature-card" href="review.html">\n            <div class="feature-preview review-preview">', 1)
s = s.replace('class="feature-card" href="/v2/">\n            <div class="feature-preview watch-preview">', 'class="feature-card" href="watch.html">\n            <div class="feature-preview watch-preview">', 1)
index.write_text(s, encoding="utf-8")

shared_css = r'''
:root {
  color-scheme: dark;
  --bg: #050505;
  --text: #f4f0e8;
  --muted: #a29d93;
  --gold-dark: #8A6A2A;
  --gold-main: #C9A646;
  --gold-light: #F5D77A;
  --gold-pale: #FFF1B8;
  --gold-shadow: #3A2A0A;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  color: var(--text);
  background:
    radial-gradient(circle at 78% 18%, rgba(201,166,70,.1), transparent 26%),
    linear-gradient(116deg, #030303, #070707 48%, #111 100%);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
}
a { color: inherit; text-decoration: none; }
.page { position: relative; min-height: 100vh; overflow: hidden; }
.page::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.018) 1px, transparent 1px);
  background-size: 52px 52px;
  mask-image: radial-gradient(circle at 60% 24%, black, transparent 74%);
}
.shell { position: relative; z-index: 1; width: min(1180px, calc(100% - 48px)); margin: 0 auto; padding-bottom: 80px; }
.nav { height: 84px; display: flex; align-items: center; justify-content: space-between; }
.brand { display: inline-flex; align-items: center; gap: 12px; font-weight: 900; }
.brand img { width: 42px; height: 42px; border-radius: 50%; object-fit: contain; }
.back { color: rgba(244,240,232,.62); font-weight: 800; font-size: 14px; }
.hero { padding: 42px 0 34px; display: grid; grid-template-columns: minmax(0, .9fr) minmax(420px, 1.1fr); gap: 46px; align-items: center; }
.tag { display: inline-flex; align-items: center; gap: 9px; border: 1px solid rgba(201,166,70,.45); border-radius: 999px; padding: 8px 14px; color: var(--gold-light); background: rgba(201,166,70,.08); font-size: 13px; font-weight: 900; }
h1 { margin: 26px 0 0; font-family: Georgia, "Times New Roman", serif; font-size: clamp(54px, 6vw, 92px); line-height: .96; font-weight: 500; }
.lead { margin: 22px 0 0; max-width: 650px; color: rgba(244,240,232,.68); font-size: 18px; line-height: 1.7; }
.gold-text { background: linear-gradient(135deg,#8A6A2A 0%,#C9A646 28%,#F5D77A 50%,#B88A2E 72%,#FFF1B8 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.panel {
  border: 1px solid rgba(245,215,122,.16);
  border-radius: 24px;
  background:
    radial-gradient(circle at 28% 18%, rgba(245,215,122,.1), transparent 26%),
    linear-gradient(145deg, rgba(255,255,255,.06), rgba(255,255,255,.018));
  box-shadow: 0 36px 90px rgba(0,0,0,.38);
}
.workspace { min-height: 420px; padding: 26px; overflow: hidden; }
.steps { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 26px; }
.step { padding: 16px; border: 1px solid rgba(255,255,255,.08); border-radius: 16px; background: rgba(0,0,0,.24); }
.step b { display: block; color: var(--gold-light); margin-bottom: 8px; }
.step span { color: rgba(244,240,232,.56); font-size: 13px; line-height: 1.55; }
.cta-row { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 30px; }
.button { min-height: 54px; display: inline-flex; align-items: center; justify-content: center; padding: 0 22px; border-radius: 16px; font-weight: 900; }
.primary { background: linear-gradient(135deg, #0B0B0B, #1A1406); border: 1px solid #C9A646; color: #F5D77A; box-shadow: 0 0 12px rgba(201,166,70,.35), inset 0 0 8px rgba(245,215,122,.15); }
.secondary { border: 1px solid rgba(255,255,255,.12); color: rgba(244,240,232,.72); background: rgba(255,255,255,.035); }
.section-title { margin: 56px 0 18px; font-size: 26px; }
.grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
.card { min-height: 180px; padding: 22px; }
.card h3 { margin: 0; font-size: 20px; }
.card p { margin: 12px 0 0; color: rgba(244,240,232,.58); line-height: 1.65; font-size: 14px; }
@media (max-width: 960px) {
  .hero { grid-template-columns: 1fr; }
  .steps, .grid-3 { grid-template-columns: 1fr; }
}
'''

review_visual = r'''
<div class="review-screen panel workspace">
  <div class="upload-box">
    <div class="upload-icon">↑</div>
    <h2>上传交割单</h2>
    <p>Excel / CSV / 截图 OCR，系统会先结构化成交记录，再进入行情归因。</p>
  </div>
  <div class="review-chart">
    <svg viewBox="0 0 680 190" preserveAspectRatio="none">
      <path d="M10 142 C86 126 122 55 190 84 C260 114 304 28 378 50 C468 76 506 140 672 36" fill="none" stroke="url(#goldLine)" stroke-width="5" stroke-linecap="round"/>
      <defs><linearGradient id="goldLine" x1="0" x2="1"><stop stop-color="#8A6A2A"/><stop offset=".52" stop-color="#F5D77A"/><stop offset="1" stop-color="#C9A646"/></linearGradient></defs>
    </svg>
    <span class="buy">Buy</span>
    <span class="sell">Best Exit</span>
  </div>
</div>
<style>
.upload-box { display: grid; place-items: center; min-height: 170px; border: 1px dashed rgba(245,215,122,.28); border-radius: 18px; background: rgba(0,0,0,.22); text-align: center; }
.upload-icon { width: 58px; height: 58px; border-radius: 18px; display: grid; place-items: center; margin-bottom: 12px; border: 1px solid rgba(245,215,122,.28); background: rgba(201,166,70,.08); font-size: 28px; color: var(--gold-light); }
.upload-box h2 { margin: 0; }
.upload-box p { margin: 8px 0 0; color: rgba(244,240,232,.52); }
.review-chart { position: relative; height: 180px; margin-top: 24px; border-radius: 18px; background: linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px), linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px); background-size: 44px 44px; }
.review-chart svg { position: absolute; inset: 24px; width: calc(100% - 48px); height: calc(100% - 48px); filter: drop-shadow(0 0 20px rgba(245,215,122,.18)); }
.buy,.sell { position: absolute; padding: 7px 10px; border-radius: 999px; font-size: 12px; font-weight: 900; background: rgba(0,0,0,.72); border: 1px solid rgba(245,215,122,.24); color: var(--gold-light); }
.buy { left: 18%; bottom: 48px; }
.sell { right: 14%; top: 34px; }
</style>
'''

watch_visual = r'''
<div class="watch-screen panel workspace">
  <div class="radar">
    <span class="ring r1"></span><span class="ring r2"></span><span class="ring r3"></span>
    <span class="core"></span>
    <span class="node n1"></span><span class="node n2"></span><span class="node n3"></span>
  </div>
  <div class="alerts">
    <div><b>长电科技</b><span>反抽至 82.05 · 减仓/走人</span><em>待触发</em></div>
    <div><b>风华高科</b><span>跌破预案线 · 止损提醒</span><em>监控中</em></div>
    <div><b>指数环境</b><span>沪深300 放量转弱 · 降低仓位</span><em>联动</em></div>
  </div>
</div>
<style>
.watch-screen { display: grid; grid-template-columns: .9fr 1.1fr; gap: 24px; align-items: center; }
.radar { position: relative; min-height: 320px; display: grid; place-items: center; }
.ring { position: absolute; border: 1px solid rgba(245,215,122,.18); border-radius: 50%; animation: spin 18s linear infinite; }
.r1 { width: 270px; height: 270px; }.r2 { width: 190px; height: 190px; animation-direction: reverse; }.r3 { width: 102px; height: 102px; border-color: rgba(245,215,122,.34); }
.core { width: 54px; height: 54px; border-radius: 50%; background: radial-gradient(circle at 36% 28%, #FFF1B8, #C9A646 48%, #3A2A0A 100%); box-shadow: 0 0 42px rgba(201,166,70,.42); }
.node { position: absolute; width: 13px; height: 13px; border-radius: 50%; background: var(--gold-light); box-shadow: 0 0 20px rgba(245,215,122,.6); }
.n1 { transform: translate(128px,-64px); }.n2 { transform: translate(-112px,72px); opacity:.75; }.n3 { transform: translate(48px,132px); opacity:.55; }
@keyframes spin { to { transform: rotate(360deg); } }
.alerts { display: grid; gap: 14px; }
.alerts div { display: grid; grid-template-columns: 1fr auto; gap: 6px 18px; padding: 18px; border: 1px solid rgba(255,255,255,.08); border-radius: 16px; background: rgba(0,0,0,.24); }
.alerts b { font-size: 18px; }.alerts span { color: rgba(244,240,232,.56); }.alerts em { grid-row: 1 / span 2; align-self: center; font-style: normal; color: var(--gold-light); font-weight: 900; }
@media (max-width: 960px) { .watch-screen { grid-template-columns: 1fr; } }
</style>
'''

def page(title, tag, lead, visual, steps, cards, primary):
    step_html = "".join(f"<div class='step'><b>{a}</b><span>{b}</span></div>" for a, b in steps)
    card_html = "".join(f"<article class='card panel'><h3>{a}</h3><p>{b}</p></article>" for a, b in cards)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>{shared_css}</style>
</head>
<body>
  <main class="page">
    <div class="shell">
      <header class="nav">
        <a class="brand" href="index.html"><img src="/frontend/public/brand-logo.png" alt="AI Trading logo" /><span>AI Trading</span></a>
        <a class="back" href="index.html">← Back Home</a>
      </header>
      <section class="hero">
        <div>
          <div class="tag">{tag}</div>
          <h1 class="gold-text">{title}</h1>
          <p class="lead">{lead}</p>
          <div class="cta-row">
            <a class="button primary" href="/v2/">{primary}</a>
            <a class="button secondary" href="index.html#features">View Modules</a>
          </div>
        </div>
        {visual}
      </section>
      <section class="steps">{step_html}</section>
      <h2 class="section-title">核心能力</h2>
      <section class="grid-3">{card_html}</section>
    </div>
  </main>
</body>
</html>"""

(base / "review.html").write_text(page(
    "AI 复盘",
    "Trade Review Workflow",
    "上传交割单后，系统把买卖点结构化，并结合个股 K 线、大盘情绪、板块强弱和产业链定位，生成可执行复盘报告。",
    review_visual,
    [
        ("1. 上传成交", "支持 Excel、CSV、截图 OCR。"),
        ("2. 对齐行情", "补全个股、指数、板块和量能。"),
        ("3. 判断买卖点", "比较实际交易与系统最佳执行点。"),
        ("4. 输出报告", "生成评分、问题、改进和预案。"),
    ],
    [
        ("买点质量", "判断是否顺应主线、量能和指数环境。"),
        ("最佳卖点", "推演更优卖出条件，而不是只评价对错。"),
        ("产业链定位", "说明这只股在题材中的位置、壁垒与弹性。"),
    ],
    "Start Review"
), encoding="utf-8")

(base / "watch.html").write_text(page(
    "AI 盯盘",
    "Trading Watch Workflow",
    "把复盘报告沉淀成盘中预案，价格、量能、指数和板块环境触发后，系统用声音和消息提醒你执行既定策略。",
    watch_visual,
    [
        ("1. 创建预案", "从复盘结论生成止盈、止损、减仓条件。"),
        ("2. 接入行情", "实时监控个股、指数、板块和成交量。"),
        ("3. 触发提醒", "达到条件后播报执行动作。"),
        ("4. 记录执行", "沉淀复盘闭环，优化下一次策略。"),
    ],
    [
        ("价格触发", "例如反抽至 82.05 后按计划减仓。"),
        ("环境联动", "指数转弱或板块退潮时降低仓位。"),
        ("AI 语音提醒", "用更有人味的提示文案提醒执行。"),
    ],
    "Create Watch Plan"
), encoding="utf-8")
