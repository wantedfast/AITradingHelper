from pathlib import Path

ROOT = Path(__file__).resolve().parent
PREVIEW = ROOT / "frontend-preview"

COMMON_STYLE = r"""
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
  --panel: rgba(255,255,255,.045);
  --line: rgba(245,215,122,.16);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  min-height: 100vh;
  color: var(--text);
  background:
    radial-gradient(circle at 78% 18%, rgba(201,166,70,.12), transparent 26%),
    linear-gradient(116deg, #030303, #070707 48%, #111 100%);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
}
a { color: inherit; text-decoration: none; }
button, input, select { font: inherit; }
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
.shell { position: relative; z-index: 1; width: min(1180px, calc(100% - 48px)); margin: 0 auto; padding-bottom: 88px; }
.nav { height: 84px; display: flex; align-items: center; justify-content: space-between; }
.brand { display: inline-flex; align-items: center; gap: 12px; font-weight: 900; }
.brand img { width: 42px; height: 42px; border-radius: 50%; object-fit: contain; }
.back { color: rgba(244,240,232,.66); font-weight: 900; font-size: 14px; }
.hero { padding: 42px 0 34px; display: grid; grid-template-columns: minmax(0, .9fr) minmax(420px, 1.1fr); gap: 46px; align-items: center; }
.tag { display: inline-flex; align-items: center; gap: 9px; border: 1px solid rgba(201,166,70,.45); border-radius: 999px; padding: 8px 14px; color: var(--gold-light); background: rgba(201,166,70,.08); font-size: 13px; font-weight: 900; }
h1 { margin: 26px 0 0; font-family: Georgia, "Times New Roman", serif; font-size: clamp(54px, 6vw, 92px); line-height: .96; font-weight: 500; }
.lead { margin: 22px 0 0; max-width: 650px; color: rgba(244,240,232,.7); font-size: 18px; line-height: 1.7; }
.gold-text { background: linear-gradient(135deg,#8A6A2A 0%,#C9A646 28%,#F5D77A 50%,#B88A2E 72%,#FFF1B8 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.panel {
  border: 1px solid var(--line);
  border-radius: 24px;
  background:
    radial-gradient(circle at 28% 18%, rgba(245,215,122,.1), transparent 26%),
    linear-gradient(145deg, rgba(255,255,255,.06), rgba(255,255,255,.018));
  box-shadow: 0 36px 90px rgba(0,0,0,.38);
}
.workspace { min-height: 420px; padding: 26px; overflow: hidden; }
.cta-row { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 30px; }
.button {
  min-height: 54px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 22px;
  border-radius: 16px;
  font-weight: 900;
  border: 0;
  cursor: pointer;
}
.primary { background: linear-gradient(135deg, #0B0B0B, #1A1406); border: 1px solid #C9A646; color: #F5D77A; box-shadow: 0 0 12px rgba(201,166,70,.35), inset 0 0 8px rgba(245,215,122,.15); }
.secondary { border: 1px solid rgba(255,255,255,.12); color: rgba(244,240,232,.72); background: rgba(255,255,255,.035); }
.button:hover, .clickable:hover { transform: translateY(-1px); border-color: rgba(245,215,122,.36); box-shadow: 0 18px 48px rgba(0,0,0,.32), 0 0 24px rgba(201,166,70,.12); }
.button:active, .clickable:active { transform: translateY(0); }
.steps { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 26px; }
.step {
  text-align: left;
  cursor: pointer;
  padding: 16px;
  border: 1px solid rgba(255,255,255,.08);
  border-radius: 16px;
  background: rgba(0,0,0,.24);
  color: inherit;
  transition: .18s ease;
}
.step b { display: block; color: var(--gold-light); margin-bottom: 8px; }
.step span { color: rgba(244,240,232,.56); font-size: 13px; line-height: 1.55; }
.step.active { border-color: rgba(245,215,122,.42); background: rgba(201,166,70,.08); }
.section-title { margin: 56px 0 18px; font-size: 26px; }
.grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
.card {
  min-height: 180px;
  padding: 22px;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: .18s ease;
}
.card h3 { margin: 0; font-size: 20px; }
.card p { margin: 12px 0 0; color: rgba(244,240,232,.58); line-height: 1.65; font-size: 14px; }
.card.active { border-color: rgba(245,215,122,.45); background: radial-gradient(circle at 24% 0%, rgba(245,215,122,.16), transparent 34%), rgba(255,255,255,.04); }
.detail-panel {
  margin-top: 18px;
  padding: 22px;
  display: grid;
  grid-template-columns: minmax(0, .85fr) minmax(280px, 1.15fr);
  gap: 18px;
  align-items: start;
}
.detail-panel h3 { margin: 0; font-size: 22px; color: var(--gold-light); }
.detail-panel p { margin: 10px 0 0; color: rgba(244,240,232,.66); line-height: 1.72; }
.mini-log { display: grid; gap: 10px; }
.mini-log div { padding: 12px 14px; border-radius: 14px; border: 1px solid rgba(255,255,255,.08); background: rgba(0,0,0,.22); color: rgba(244,240,232,.7); }
.status { color: var(--gold-light); font-weight: 900; }
.toast {
  position: fixed;
  right: 28px;
  bottom: 28px;
  z-index: 9;
  max-width: 360px;
  padding: 15px 16px;
  border: 1px solid rgba(245,215,122,.26);
  border-radius: 16px;
  background: rgba(8,8,8,.92);
  color: rgba(244,240,232,.88);
  box-shadow: 0 24px 80px rgba(0,0,0,.44);
  opacity: 0;
  transform: translateY(12px);
  pointer-events: none;
  transition: .22s ease;
}
.toast.show { opacity: 1; transform: translateY(0); }
@media (max-width: 960px) {
  .shell { width: min(100% - 32px, 720px); }
  .hero { grid-template-columns: 1fr; }
  .steps, .grid-3, .detail-panel { grid-template-columns: 1fr; }
}
"""

REVIEW_HTML = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI 复盘</title>
  <style>
{COMMON_STYLE}
.upload-box {{
  display: grid;
  place-items: center;
  min-height: 170px;
  border: 1px dashed rgba(245,215,122,.32);
  border-radius: 18px;
  background: rgba(0,0,0,.22);
  text-align: center;
  cursor: pointer;
  transition: .18s ease;
}}
.upload-icon {{ width: 58px; height: 58px; border-radius: 18px; display: grid; place-items: center; margin-bottom: 12px; border: 1px solid rgba(245,215,122,.28); background: rgba(201,166,70,.08); font-size: 28px; color: var(--gold-light); }}
.upload-box h2 {{ margin: 0; }}
.upload-box p {{ margin: 8px 0 0; color: rgba(244,240,232,.52); }}
.file-pill {{ display: inline-flex; align-items: center; gap: 8px; margin-top: 14px; padding: 8px 12px; border-radius: 999px; background: rgba(201,166,70,.1); border: 1px solid rgba(245,215,122,.24); color: var(--gold-light); font-size: 13px; font-weight: 900; }}
.review-chart {{ position: relative; height: 180px; margin-top: 24px; border-radius: 18px; background: linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px), linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px); background-size: 44px 44px; }}
.review-chart svg {{ position: absolute; inset: 24px; width: calc(100% - 48px); height: calc(100% - 48px); filter: drop-shadow(0 0 20px rgba(245,215,122,.18)); }}
.buy,.sell {{ position: absolute; padding: 7px 10px; border-radius: 999px; font-size: 12px; font-weight: 900; background: rgba(0,0,0,.72); border: 1px solid rgba(245,215,122,.24); color: var(--gold-light); }}
.buy {{ left: 18%; bottom: 48px; }}
.sell {{ right: 14%; top: 34px; }}
.report-preview {{ display: none; margin-top: 26px; padding: 22px; }}
.report-preview.show {{ display: block; }}
.score-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 16px; }}
.score-row div {{ padding: 14px; border-radius: 14px; border: 1px solid rgba(255,255,255,.08); background: rgba(0,0,0,.22); }}
.score-row b {{ display: block; color: var(--gold-light); font-size: 24px; }}
@media (max-width: 760px) {{ .score-row {{ grid-template-columns: 1fr 1fr; }} }}
  </style>
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
          <div class="tag">Trade Review Workflow</div>
          <h1 class="gold-text">AI 复盘</h1>
          <p class="lead">上传交割单后，系统把买卖点结构化，并结合个股 K 线、大盘情绪、板块强弱和产业链定位，生成可执行复盘报告。</p>
          <div class="cta-row">
            <button class="button primary" id="startReview">Start Review</button>
            <a class="button secondary" href="#capabilities">View Modules</a>
          </div>
        </div>

        <div class="review-screen panel workspace">
          <input id="tradeFile" type="file" hidden accept=".xls,.xlsx,.csv,.txt,image/*" />
          <label class="upload-box clickable" for="tradeFile">
            <div class="upload-icon">↑</div>
            <h2 id="uploadTitle">上传交割单</h2>
            <p id="uploadHint">Excel / CSV / 截图 OCR，系统会先结构化成交记录，再进入行情归因。</p>
            <span class="file-pill" id="filePill">等待选择文件</span>
          </label>
          <div class="review-chart">
            <svg viewBox="0 0 680 190" preserveAspectRatio="none">
              <path d="M10 142 C86 126 122 55 190 84 C260 114 304 28 378 50 C468 76 506 140 672 36" fill="none" stroke="url(#goldLine)" stroke-width="5" stroke-linecap="round"/>
              <defs><linearGradient id="goldLine" x1="0" x2="1"><stop stop-color="#8A6A2A"/><stop offset=".52" stop-color="#F5D77A"/><stop offset="1" stop-color="#C9A646"/></linearGradient></defs>
            </svg>
            <button class="buy clickable" data-detail="buy">Buy</button>
            <button class="sell clickable" data-detail="exit">Best Exit</button>
          </div>
        </div>
      </section>

      <section class="steps">
        <button class="step active" data-step="上传成交"><b>1. 上传成交</b><span>支持 Excel、CSV、截图 OCR。</span></button>
        <button class="step" data-step="对齐行情"><b>2. 对齐行情</b><span>补全个股、指数、板块和量能。</span></button>
        <button class="step" data-step="判断买卖点"><b>3. 判断买卖点</b><span>比较实际交易与系统最佳执行点。</span></button>
        <button class="step" data-step="输出报告"><b>4. 输出报告</b><span>生成评分、问题、改进和预案。</span></button>
      </section>

      <h2 class="section-title" id="capabilities">核心能力</h2>
      <section class="grid-3">
        <button class="card panel active" data-card="buy"><h3>买点质量</h3><p>判断是否顺应主线、量能和指数环境。</p></button>
        <button class="card panel" data-card="exit"><h3>最佳卖点</h3><p>推演更优卖出条件，而不是只评价对错。</p></button>
        <button class="card panel" data-card="chain"><h3>产业链定位</h3><p>说明这只股在题材中的位置、壁垒与弹性。</p></button>
      </section>

      <section class="detail-panel panel" id="detailPanel">
        <div>
          <h3 id="detailTitle">买点质量</h3>
          <p id="detailText">系统会先判断买入当天是否有指数环境支持、板块是否有主攻方向、个股是否强于板块，并结合成交量和日 K 位置给出买点评分。</p>
        </div>
        <div class="mini-log" id="miniLog">
          <div><span class="status">已选模块：</span>买点质量</div>
          <div>输入交割单后，会自动生成买入日大盘、板块、个股三层对照。</div>
        </div>
      </section>

      <section class="report-preview panel" id="reportPreview">
        <h2>复盘报告已生成</h2>
        <p class="lead">示例报告：买点合格，卖点需要规则化。系统建议用“5日线失守或放量长阴”作为纪律卖点，不再凭感觉提前卖飞。</p>
        <div class="score-row">
          <div><span>逻辑</span><b>92</b></div>
          <div><span>买点</span><b>88</b></div>
          <div><span>卖点</span><b>76</b></div>
          <div><span>风控</span><b>84</b></div>
        </div>
      </section>
    </div>
  </main>
  <div class="toast" id="toast"></div>
  <script>
    const details = {{
      buy: ["买点质量", "系统会先判断买入当天是否有指数环境支持、板块是否有主攻方向、个股是否强于板块，并结合成交量和日 K 位置给出买点评分。"],
      exit: ["最佳卖点", "系统不会只说你卖早了，而是推演更优卖点：趋势股看 5 日线、放量长阴、反抽失败；题材股看板块退潮和核心股断板。"],
      chain: ["产业链定位", "参考 WANG-INVESTOR 的思路，把标的放回产业链：上游材料、中游制造、下游需求、壁垒、利润弹性和替代风险。"]
    }};
    const toast = document.getElementById("toast");
    function showToast(text) {{
      toast.textContent = text;
      toast.classList.add("show");
      clearTimeout(window.__toastTimer);
      window.__toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
    }}
    function setDetail(key) {{
      const [title, text] = details[key];
      document.getElementById("detailTitle").textContent = title;
      document.getElementById("detailText").textContent = text;
      document.getElementById("miniLog").innerHTML = `<div><span class="status">已选模块：</span>${{title}}</div><div>${{text}}</div>`;
      document.querySelectorAll(".card").forEach(card => card.classList.toggle("active", card.dataset.card === key));
      document.getElementById("detailPanel").scrollIntoView({{ behavior: "smooth", block: "center" }});
    }}
    document.querySelectorAll("[data-card]").forEach(card => card.addEventListener("click", () => setDetail(card.dataset.card)));
    document.querySelectorAll("[data-detail]").forEach(btn => btn.addEventListener("click", () => setDetail(btn.dataset.detail)));
    document.querySelectorAll(".step").forEach(step => {{
      step.addEventListener("click", () => {{
        document.querySelectorAll(".step").forEach(item => item.classList.remove("active"));
        step.classList.add("active");
        showToast(`已进入流程：${{step.dataset.step}}`);
      }});
    }});
    document.getElementById("startReview").addEventListener("click", () => document.getElementById("tradeFile").click());
    document.getElementById("tradeFile").addEventListener("change", (event) => {{
      const file = event.target.files?.[0];
      if (!file) return;
      document.getElementById("uploadTitle").textContent = "交割单已就绪";
      document.getElementById("uploadHint").textContent = "已进入结构化解析，下一步会对齐行情和板块环境。";
      document.getElementById("filePill").textContent = file.name;
      document.getElementById("reportPreview").classList.add("show");
      showToast("文件已接收，正在生成复盘报告演示。");
      setTimeout(() => document.getElementById("reportPreview").scrollIntoView({{ behavior: "smooth", block: "center" }}), 300);
    }});
  </script>
</body>
</html>
"""

WATCH_HTML = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI 盯盘</title>
  <style>
{COMMON_STYLE}
.watch-screen {{ display: grid; grid-template-columns: .9fr 1.1fr; gap: 24px; align-items: center; }}
.radar {{ position: relative; min-height: 320px; display: grid; place-items: center; }}
.ring {{ position: absolute; border: 1px solid rgba(245,215,122,.18); border-radius: 50%; animation: spin 18s linear infinite; }}
.r1 {{ width: 270px; height: 270px; }}.r2 {{ width: 190px; height: 190px; animation-direction: reverse; }}.r3 {{ width: 102px; height: 102px; border-color: rgba(245,215,122,.34); }}
.core {{ width: 54px; height: 54px; border-radius: 50%; background: radial-gradient(circle at 36% 28%, #FFF1B8, #C9A646 48%, #3A2A0A 100%); box-shadow: 0 0 42px rgba(201,166,70,.42); }}
.node {{ position: absolute; width: 13px; height: 13px; border-radius: 50%; background: var(--gold-light); box-shadow: 0 0 20px rgba(245,215,122,.6); }}
.n1 {{ transform: translate(128px,-64px); }}.n2 {{ transform: translate(-112px,72px); opacity:.75; }}.n3 {{ transform: translate(48px,132px); opacity:.55; }}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
.alerts {{ display: grid; gap: 14px; }}
.alerts button {{ display: grid; grid-template-columns: 1fr auto; gap: 6px 18px; text-align: left; padding: 18px; border: 1px solid rgba(255,255,255,.08); border-radius: 16px; background: rgba(0,0,0,.24); color: inherit; cursor: pointer; }}
.alerts b {{ font-size: 18px; }}.alerts span {{ color: rgba(244,240,232,.56); }}.alerts em {{ grid-row: 1 / span 2; align-self: center; font-style: normal; color: var(--gold-light); font-weight: 900; }}
.plan-panel {{ display: none; margin-top: 26px; padding: 22px; }}
.plan-panel.show {{ display: block; }}
.plan-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; margin-top: 16px; }}
.field {{ display: grid; gap: 7px; }}
.field label {{ color: rgba(244,240,232,.58); font-size: 13px; font-weight: 800; }}
.field input, .field select {{ min-height: 44px; border-radius: 12px; border: 1px solid rgba(245,215,122,.16); background: rgba(0,0,0,.28); color: var(--text); padding: 0 12px; }}
.trigger-log {{ margin-top: 16px; padding: 14px; border-radius: 14px; background: rgba(0,0,0,.22); border: 1px solid rgba(255,255,255,.08); color: rgba(244,240,232,.7); }}
@media (max-width: 960px) {{ .watch-screen, .plan-grid {{ grid-template-columns: 1fr; }} }}
  </style>
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
          <div class="tag">Trading Watch Workflow</div>
          <h1 class="gold-text">AI 盯盘</h1>
          <p class="lead">把复盘报告沉淀成盘中预案，价格、量能、指数和板块环境触发后，系统用声音和消息提醒你执行既定策略。</p>
          <div class="cta-row">
            <button class="button primary" id="createPlan">Create Watch Plan</button>
            <a class="button secondary" href="#capabilities">View Modules</a>
            <button class="button secondary" id="simulateTrigger">模拟触发 82.05</button>
          </div>
        </div>

        <div class="watch-screen panel workspace">
          <div class="radar">
            <span class="ring r1"></span><span class="ring r2"></span><span class="ring r3"></span>
            <span class="core"></span>
            <span class="node n1"></span><span class="node n2"></span><span class="node n3"></span>
          </div>
          <div class="alerts">
            <button class="clickable alert" data-alert="长电科技"><b>长电科技</b><span>反抽至 82.05 · 减仓/走人</span><em id="alertStatus">待触发</em></button>
            <button class="clickable alert" data-alert="风华高科"><b>风华高科</b><span>跌破预案线 · 止损提醒</span><em>监控中</em></button>
            <button class="clickable alert" data-alert="指数环境"><b>指数环境</b><span>沪深300 放量转弱 · 降低仓位</span><em>联动</em></button>
          </div>
        </div>
      </section>

      <section class="steps">
        <button class="step active" data-step="创建预案"><b>1. 创建预案</b><span>从复盘结论生成止盈、止损、减仓条件。</span></button>
        <button class="step" data-step="接入行情"><b>2. 接入行情</b><span>实时监控个股、指数、板块和成交量。</span></button>
        <button class="step" data-step="触发提醒"><b>3. 触发提醒</b><span>达到条件后播报执行动作。</span></button>
        <button class="step" data-step="记录执行"><b>4. 记录执行</b><span>沉淀复盘闭环，优化下一次策略。</span></button>
      </section>

      <section class="plan-panel panel show" id="planPanel">
        <h2>盯盘预案</h2>
        <p class="lead">这里不是摆设。你可以改标的、触发价、动作和提醒文案，然后点击“模拟触发 82.05”测试声音与状态变化。</p>
        <div class="plan-grid">
          <div class="field"><label>标的</label><input id="stockName" value="长电科技" /></div>
          <div class="field"><label>触发价</label><input id="triggerPrice" value="82.05" /></div>
          <div class="field"><label>执行动作</label><select id="action"><option>减仓/走人</option><option>止损</option><option>继续观察</option></select></div>
          <div class="field"><label>语气</label><select id="tone"><option>可爱但凶巴巴</option><option>冷静交易员</option><option>幽默吐槽</option></select></div>
        </div>
        <div class="field" style="margin-top:14px"><label>提醒文案</label><input id="voiceLine" value="别恋战，剧本写好了，现在执行。" /></div>
        <div class="trigger-log" id="triggerLog">状态：等待触发。</div>
      </section>

      <h2 class="section-title" id="capabilities">核心能力</h2>
      <section class="grid-3">
        <button class="card panel active" data-card="price"><h3>价格触发</h3><p>例如反抽至 82.05 后按计划减仓。</p></button>
        <button class="card panel" data-card="env"><h3>环境联动</h3><p>指数转弱或板块退潮时降低仓位。</p></button>
        <button class="card panel" data-card="voice"><h3>AI 语音提醒</h3><p>用更有人味的提示文案提醒执行。</p></button>
      </section>

      <section class="detail-panel panel" id="detailPanel">
        <div>
          <h3 id="detailTitle">价格触发</h3>
          <p id="detailText">盯盘不是只看价格，而是把价格触发和预案动作绑定：到价后提醒你执行减仓、止损或继续观察。</p>
        </div>
        <div class="mini-log" id="miniLog">
          <div><span class="status">已选模块：</span>价格触发</div>
          <div>当前演示预案：长电科技反抽至 82.05，提醒减仓/走人。</div>
        </div>
      </section>
    </div>
  </main>
  <div class="toast" id="toast"></div>
  <script>
    const details = {{
      price: ["价格触发", "盯盘不是只看价格，而是把价格触发和预案动作绑定：到价后提醒你执行减仓、止损或继续观察。"],
      env: ["环境联动", "同一个价格，在指数强势和指数转弱时意义不同。系统会把沪深300、板块涨幅、成交量变化一起纳入提醒。"],
      voice: ["AI 语音提醒", "提醒文案可以由 Agent 生成，再由 TTS 播报。目标是把交易纪律拉回来，而不是吓你一跳。"]
    }};
    const toast = document.getElementById("toast");
    function showToast(text) {{
      toast.textContent = text;
      toast.classList.add("show");
      clearTimeout(window.__toastTimer);
      window.__toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
    }}
    function setDetail(key) {{
      const [title, text] = details[key];
      document.getElementById("detailTitle").textContent = title;
      document.getElementById("detailText").textContent = text;
      document.getElementById("miniLog").innerHTML = `<div><span class="status">已选模块：</span>${{title}}</div><div>${{text}}</div>`;
      document.querySelectorAll(".card").forEach(card => card.classList.toggle("active", card.dataset.card === key));
      document.getElementById("detailPanel").scrollIntoView({{ behavior: "smooth", block: "center" }});
    }}
    function speak(text) {{
      if (!("speechSynthesis" in window)) return;
      speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "zh-CN";
      utterance.rate = 1.04;
      utterance.pitch = 1.18;
      speechSynthesis.speak(utterance);
    }}
    function triggerPlan() {{
      const stock = document.getElementById("stockName").value || "长电科技";
      const price = document.getElementById("triggerPrice").value || "82.05";
      const action = document.getElementById("action").value;
      const line = document.getElementById("voiceLine").value || "别恋战，剧本写好了，现在执行。";
      document.getElementById("alertStatus").textContent = "已触发";
      document.getElementById("triggerLog").innerHTML = `状态：<span class="status">${{stock}} 已触发 ${{price}}，执行动作：${{action}}。</span><br>播报：${{line}}`;
      showToast(`${{stock}} 到达 ${{price}}，提醒执行：${{action}}`);
      speak(line);
      document.getElementById("planPanel").scrollIntoView({{ behavior: "smooth", block: "center" }});
    }}
    document.getElementById("createPlan").addEventListener("click", () => {{
      document.getElementById("planPanel").classList.add("show");
      document.getElementById("planPanel").scrollIntoView({{ behavior: "smooth", block: "center" }});
      showToast("盯盘预案已打开，可以编辑条件。");
    }});
    document.getElementById("simulateTrigger").addEventListener("click", triggerPlan);
    document.querySelectorAll(".alert").forEach(alert => alert.addEventListener("click", () => showToast(`已选中告警：${{alert.dataset.alert}}`)));
    document.querySelectorAll("[data-card]").forEach(card => card.addEventListener("click", () => setDetail(card.dataset.card)));
    document.querySelectorAll(".step").forEach(step => {{
      step.addEventListener("click", () => {{
        document.querySelectorAll(".step").forEach(item => item.classList.remove("active"));
        step.classList.add("active");
        showToast(`已进入流程：${{step.dataset.step}}`);
      }});
    }});
  </script>
</body>
</html>
"""

(PREVIEW / "review.html").write_text(REVIEW_HTML, encoding="utf-8")
(PREVIEW / "watch.html").write_text(WATCH_HTML, encoding="utf-8")
print("interactive preview pages rebuilt")
