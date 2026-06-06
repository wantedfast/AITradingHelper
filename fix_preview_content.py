from pathlib import Path
import re

p = Path("frontend-preview/index.html")
s = p.read_text(encoding="utf-8")

hero = (
    '<div class="hero-copy">\n'
    '          <div class="eyebrow">AI Trade Review Agent</div>\n'
    '          <h1>AI Trading for Beginners</h1>\n'
    '          <p class="headline-sub">Stop Guessing. Start Trading With Your Best Strategy.</p>\n'
    '          <p class="cn-slogan">\u6446\u8131\u76f2\u4ece\uff0c\u4f9d\u6258\u4f18\u7b56\u3002</p>\n'
    '          <p class="description">\n'
    '            \u4ece\u4ea4\u5272\u5355\u5f00\u59cb\uff0cAI \u81ea\u52a8\u8fd8\u539f\u4f60\u7684\u4ea4\u6613\u73b0\u573a\uff1a'
    '\u5e02\u573a\u60c5\u7eea\u3001\u677f\u5757\u65b9\u5411\u3001\u4e2a\u80a1\u5f3a\u5ea6\u3001\u4ea7\u4e1a\u94fe\u4f4d\u7f6e\u548c\u6700\u4f73\u6267\u884c\u65b9\u6848\u3002\n'
    '          </p>\n'
    '          <div class="actions">\n'
    '            <a class="primary" href="/v2/">Upload Trades</a>\n'
    '            <a class="secondary" href="#features">Explore Features</a>\n'
    '          </div>\n'
    '        </div>'
)
s = re.sub(r'<div class="hero-copy">.*?</div>\s*\n\n        <div class="visual"', hero + '\n\n        <div class="visual"', s, count=1, flags=re.S)

features = (
    '<section id="features" class="features">\n'
    '        <div class="section-heading">\n'
    '          <p>Two Core Modules</p>\n'
    '          <h2>\u4ece\u590d\u76d8\u5230\u76ef\u76d8\uff0c\u53ea\u4fdd\u7559\u771f\u6b63\u5f71\u54cd\u4ea4\u6613\u51b3\u7b56\u7684\u529f\u80fd\u3002</h2>\n'
    '        </div>\n\n'
    '        <div class="feature-grid">\n'
    '          <article class="feature-card">\n'
    '            <div class="feature-top">\n'
    '              <div class="feature-icon">\u2197</div>\n'
    '              <div>\n'
    '                <span>Trade Review</span>\n'
    '                <h3>AI \u590d\u76d8</h3>\n'
    '              </div>\n'
    '            </div>\n'
    '            <p>\u4e0a\u4f20\u4ea4\u5272\u5355\u540e\uff0c\u7cfb\u7edf\u81ea\u52a8\u7ed3\u6784\u5316\u4e70\u5356\u70b9\uff0c\u7ed3\u5408\u4e2a\u80a1 K \u7ebf\u3001\u5927\u76d8\u60c5\u7eea\u3001\u677f\u5757\u5f3a\u5f31\u548c\u4ea7\u4e1a\u94fe\u5b9a\u4f4d\uff0c\u7ed9\u51fa\u53ef\u6267\u884c\u7684\u590d\u76d8\u7ed3\u8bba\u3002</p>\n'
    '            <ul>\n'
    '              <li>\u4e70\u5356\u70b9\u8bc4\u5206</li>\n'
    '              <li>\u6700\u4f73\u5356\u70b9\u63a8\u6f14</li>\n'
    '              <li>\u677f\u5757\u4e0e\u6307\u6570\u5171\u632f</li>\n'
    '              <li>\u4ea7\u4e1a\u94fe\u4f4d\u7f6e\u5224\u65ad</li>\n'
    '            </ul>\n'
    '          </article>\n\n'
    '          <article class="feature-card">\n'
    '            <div class="feature-top">\n'
    '              <div class="feature-icon">\u25ce</div>\n'
    '              <div>\n'
    '                <span>Trading Watch</span>\n'
    '                <h3>AI \u76ef\u76d8</h3>\n'
    '              </div>\n'
    '            </div>\n'
    '            <p>\u628a\u590d\u76d8\u7ed3\u8bba\u53d8\u6210\u76d8\u4e2d\u9884\u6848\uff1a\u4ef7\u683c\u3001\u6da8\u8dcc\u5e45\u3001\u91cf\u80fd\u3001\u6307\u6570\u73af\u5883\u89e6\u53d1\u540e\u63d0\u9192\u4ea4\u6613\u8005\u6267\u884c\uff0c\u907f\u514d\u4e34\u76d8\u51ed\u611f\u89c9\u6539\u5267\u672c\u3002</p>\n'
    '            <ul>\n'
    '              <li>\u9884\u6848\u89e6\u53d1</li>\n'
    '              <li>\u58f0\u97f3\u63d0\u9192</li>\n'
    '              <li>\u98ce\u9669\u6761\u4ef6</li>\n'
    '              <li>\u6267\u884c\u8bb0\u5f55</li>\n'
    '            </ul>\n'
    '          </article>\n'
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
p.write_text(s, encoding="utf-8")
