from pathlib import Path
import re

preview = Path("frontend-preview/index.html")
s = preview.read_text(encoding="utf-8")

css_start = s.index("    .features {")
css_end = s.index("    .flow-card {", css_start)
new_css = r'''    .features {
      position: relative;
      padding: 16px 0 118px;
    }

    .section-heading {
      max-width: 760px;
      margin: 0 auto 48px;
      text-align: center;
    }

    .section-heading p {
      margin: 0 0 14px;
      color: var(--gold);
      font-size: 14px;
      font-weight: 900;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .section-heading h2 {
      margin: 0;
      color: rgba(244, 240, 232, 0.86);
      font-size: clamp(30px, 3.2vw, 48px);
      line-height: 1.08;
      font-weight: 900;
    }

    .feature-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(320px, 1fr));
      gap: 34px;
    }

    .feature-card {
      display: block;
      min-width: 0;
      color: inherit;
    }

    .feature-preview {
      position: relative;
      min-height: 260px;
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, 0.09);
      border-radius: 24px;
      background:
        radial-gradient(circle at 68% 36%, rgba(201, 166, 70, 0.12), transparent 30%),
        linear-gradient(145deg, #050505, #0c0c0c 58%, #111 100%);
      box-shadow: 0 36px 90px rgba(0, 0, 0, 0.42);
    }

    .feature-card:hover .feature-preview {
      border-color: rgba(245, 215, 122, 0.28);
      box-shadow: 0 44px 110px rgba(0, 0, 0, 0.52), 0 0 34px rgba(201, 166, 70, 0.12);
    }

    .review-preview::before {
      content: "";
      position: absolute;
      inset: 26px;
      border-radius: 18px;
      background:
        linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px),
        linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px);
      background-size: 42px 42px;
      opacity: 0.65;
      mask-image: radial-gradient(circle at 48% 54%, black, transparent 76%);
    }

    .chart-line {
      position: absolute;
      left: 34px;
      right: 34px;
      bottom: 66px;
      height: 92px;
    }

    .chart-line svg {
      width: 100%;
      height: 100%;
      overflow: visible;
      filter: drop-shadow(0 0 18px rgba(245, 215, 122, 0.22));
    }

    .trade-dot {
      position: absolute;
      width: 13px;
      height: 13px;
      border: 2px solid #050505;
      border-radius: 50%;
      background: var(--gold-light);
      box-shadow: 0 0 24px rgba(245, 215, 122, 0.55);
    }

    .dot-buy { left: 24%; bottom: 96px; }
    .dot-sell { left: 68%; bottom: 150px; }

    .watch-preview {
      background:
        radial-gradient(circle at 50% 46%, rgba(245, 215, 122, 0.10), transparent 34%),
        radial-gradient(circle at 68% 28%, rgba(255, 255, 255, 0.06), transparent 20%),
        linear-gradient(145deg, #050505, #101010 56%, #090806 100%);
    }

    .watch-orbit {
      position: absolute;
      inset: 32px;
      display: grid;
      place-items: center;
    }

    .watch-ring {
      position: absolute;
      border: 1px solid rgba(245, 215, 122, 0.16);
      border-radius: 50%;
      animation: slowSpin 18s linear infinite;
    }

    .ring-a { width: 210px; height: 210px; }
    .ring-b { width: 150px; height: 150px; animation-duration: 13s; animation-direction: reverse; }
    .ring-c { width: 84px; height: 84px; border-color: rgba(245, 215, 122, 0.32); }

    .watch-core {
      width: 48px;
      height: 48px;
      border-radius: 50%;
      background: radial-gradient(circle at 36% 28%, #fff1b8, #c9a646 48%, #3a2a0a 100%);
      box-shadow: 0 0 34px rgba(201, 166, 70, 0.38);
    }

    .watch-pulse {
      position: absolute;
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: var(--gold-light);
      box-shadow: 0 0 18px rgba(245, 215, 122, 0.52);
    }

    .pulse-a { transform: translate(104px, -40px); }
    .pulse-b { transform: translate(-96px, 58px); opacity: 0.72; }
    .pulse-c { transform: translate(36px, 106px); opacity: 0.54; }

    @keyframes slowSpin {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }

    .feature-meta {
      display: grid;
      grid-template-columns: 54px minmax(0, 1fr);
      gap: 16px;
      align-items: start;
      padding: 18px 4px 0;
    }

    .feature-icon {
      width: 48px;
      height: 48px;
      display: grid;
      place-items: center;
      border-radius: 50%;
      color: var(--gold-light);
      background: #1b1b1b;
      border: 1px solid rgba(245, 215, 122, 0.15);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.08);
      font-size: 22px;
    }

    .feature-kicker {
      margin: 0 0 5px;
      color: rgba(244, 240, 232, 0.44);
      font-size: 13px;
      font-weight: 900;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .feature-card h3 {
      margin: 0;
      color: var(--text);
      font-size: 24px;
      line-height: 1.18;
      font-weight: 900;
    }

    .feature-card p {
      margin: 10px 0 0;
      max-width: 560px;
      color: rgba(244, 240, 232, 0.56);
      font-size: 15px;
      line-height: 1.65;
    }

'''
s = s[:css_start] + new_css + s[css_end:]

features = (
    '<section id="features" class="features">\n'
    '        <div class="section-heading">\n'
    '          <p>Two Core Modules</p>\n'
    '          <h2>Build your trading workflow from review to watch.</h2>\n'
    '        </div>\n\n'
    '        <div class="feature-grid">\n'
    '          <a class="feature-card" href="/v2/">\n'
    '            <div class="feature-preview review-preview">\n'
    '              <div class="chart-line">\n'
    '                <svg viewBox="0 0 420 120" preserveAspectRatio="none" aria-hidden="true">\n'
    '                  <path d="M6 98 C62 86 78 40 128 58 C180 78 196 16 246 30 C304 46 320 88 414 22" fill="none" stroke="url(#reviewGold)" stroke-width="5" stroke-linecap="round"/>\n'
    '                  <defs><linearGradient id="reviewGold" x1="0" x2="1"><stop stop-color="#8A6A2A"/><stop offset=".52" stop-color="#F5D77A"/><stop offset="1" stop-color="#C9A646"/></linearGradient></defs>\n'
    '                </svg>\n'
    '              </div>\n'
    '              <span class="trade-dot dot-buy"></span>\n'
    '              <span class="trade-dot dot-sell"></span>\n'
    '            </div>\n'
    '            <div class="feature-meta">\n'
    '              <div class="feature-icon">↗</div>\n'
    '              <div>\n'
    '                <div class="feature-kicker">Trade Review</div>\n'
    '                <h3>AI 复盘</h3>\n'
    '                <p>上传交割单，自动还原买卖点、市场环境、板块共振和产业链定位。</p>\n'
    '              </div>\n'
    '            </div>\n'
    '          </a>\n\n'
    '          <a class="feature-card" href="/v2/">\n'
    '            <div class="feature-preview watch-preview">\n'
    '              <div class="watch-orbit">\n'
    '                <span class="watch-ring ring-a"></span>\n'
    '                <span class="watch-ring ring-b"></span>\n'
    '                <span class="watch-ring ring-c"></span>\n'
    '                <span class="watch-core"></span>\n'
    '                <span class="watch-pulse pulse-a"></span>\n'
    '                <span class="watch-pulse pulse-b"></span>\n'
    '                <span class="watch-pulse pulse-c"></span>\n'
    '              </div>\n'
    '            </div>\n'
    '            <div class="feature-meta">\n'
    '              <div class="feature-icon">◎</div>\n'
    '              <div>\n'
    '                <div class="feature-kicker">Trading Watch</div>\n'
    '                <h3>AI 盯盘</h3>\n'
    '                <p>把复盘结论变成盘中预案，价格、量能和指数环境触发后提醒执行。</p>\n'
    '              </div>\n'
    '            </div>\n'
    '          </a>\n'
    '        </div>\n\n'
    '        <div class="flow-card">\n'
    '          <span>Upload trades</span><i></i>\n'
    '          <span>AI review</span><i></i>\n'
    '          <span>Build strategy</span><i></i>\n'
    '          <span>Watch & execute</span>\n'
    '        </div>\n'
    '      </section>'
)
s = re.sub(r'<section id="features" class="features">.*?</section>', features, s, count=1, flags=re.S)

p = preview
p.write_text(s, encoding="utf-8")
