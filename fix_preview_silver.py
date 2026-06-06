from pathlib import Path
import re

p = Path("frontend-preview/index.html")
s = p.read_text(encoding="utf-8")

repls = {
    "--gold: #d8af4b;": "--gold: #c9d1d9;",
    "--gold-2: #ffe08a;": "--gold-2: #f4f7fb;",
    "rgba(216, 175, 75": "rgba(195, 204, 214",
    "rgba(255, 224, 138": "rgba(238, 242, 246",
    "#d8af4b": "#c9d1d9",
    "#ffe08a": "#f4f7fb",
    "#c99d37": "#bfc5cc",
    "#f0c869": "#eef2f6",
    "#ffda74": "#f3f6fb",
    "#fff0bf": "#f8fbff",
    "#fff2c7": "#eef2f6",
    "#ffe6a8": "#dfe6ee",
}
for old, new in repls.items():
    s = s.replace(old, new)

s = s.replace(
    "radial-gradient(circle at 38% 31%, rgba(238, 242, 246, 0.08), transparent 18%),\n"
    "        radial-gradient(circle at 62% 68%, rgba(255, 255, 255, 0.03), transparent 22%),\n"
    "        radial-gradient(circle at 50% 50%, rgba(195, 204, 214, 0.045), transparent 58%);\n"
    "      filter: blur(28px);\n"
    "      opacity: 0.34;",
    "radial-gradient(circle at 40% 34%, rgba(230, 236, 242, 0.045), transparent 20%),\n"
    "        radial-gradient(circle at 50% 50%, rgba(30, 34, 40, 0.26), transparent 60%);\n"
    "      filter: blur(34px);\n"
    "      opacity: 0.32;",
)

s = s.replace(
    "background: radial-gradient(ellipse at center, rgba(238, 242, 246, 0.08), rgba(195, 204, 214, 0.025) 36%, transparent 68%);\n"
    "      filter: blur(28px);\n"
    "      transform: rotate(-5deg);\n"
    "      opacity: 0.28;",
    "background: radial-gradient(ellipse at center, rgba(220, 226, 232, 0.04), rgba(16, 18, 22, 0.18) 42%, transparent 72%);\n"
    "      filter: blur(34px);\n"
    "      transform: rotate(-5deg);\n"
    "      opacity: 0.22;",
)

s = re.sub(
    r'<p class="cn-slogan">.*?</p>',
    '<p class="cn-slogan">\u6446\u8131\u76f2\u4ece\uff0c\u4f9d\u6258\u4f18\u7b56\u3002</p>',
    s,
    flags=re.S,
)
s = re.sub(
    r'<p class="description">.*?</p>',
    '<p class="description">\n'
    '            \u4ece\u4ea4\u5272\u5355\u5f00\u59cb\uff0cAI \u81ea\u52a8\u8fd8\u539f\u4f60\u7684\u4ea4\u6613\u73b0\u573a\uff1a'
    '\u5e02\u573a\u60c5\u7eea\u3001\u677f\u5757\u65b9\u5411\u3001\u4e2a\u80a1\u5f3a\u5ea6\u3001\u4ea7\u4e1a\u94fe\u4f4d\u7f6e\u548c\u6700\u4f73\u6267\u884c\u65b9\u6848\u3002\n'
    '          </p>',
    s,
    count=1,
    flags=re.S,
)
s = re.sub(
    r'<h2>.*?</h2>\s*</div>\s*\n\n        <div class="feature-grid">',
    '<h2>\u4ece\u590d\u76d8\u5230\u76ef\u76d8\uff0c\u53ea\u4fdd\u7559\u771f\u6b63\u5f71\u54cd\u4ea4\u6613\u51b3\u7b56\u7684\u529f\u80fd\u3002</h2>\n'
    '        </div>\n\n        <div class="feature-grid">',
    s,
    count=1,
    flags=re.S,
)

feature1 = (
    '<article class="feature-card">\n'
    '            <div class="feature-top">\n'
    '              <div class="feature-icon">\u2197</div>\n'
    '              <div>\n'
    '                <span>Trade Review</span>\n'
    '                <h3>AI \u590d\u76d8</h3>\n'
    '              </div>\n'
    '            </div>\n'
    '            <p>\u4e0a\u4f20\u4ea4\u5272\u5355\u540e\uff0c\u7cfb\u7edf\u81ea\u52a8\u7ed3\u6784\u5316\u4e70\u5356\u70b9\uff0c'
    '\u7ed3\u5408\u4e2a\u80a1 K \u7ebf\u3001\u5927\u76d8\u60c5\u7eea\u3001\u677f\u5757\u5f3a\u5f31\u548c\u4ea7\u4e1a\u94fe\u5b9a\u4f4d\uff0c'
    '\u7ed9\u51fa\u53ef\u6267\u884c\u7684\u590d\u76d8\u7ed3\u8bba\u3002</p>\n'
    '            <ul>\n'
    '              <li>\u4e70\u5356\u70b9\u8bc4\u5206</li>\n'
    '              <li>\u6700\u4f73\u5356\u70b9\u63a8\u6f14</li>\n'
    '              <li>\u677f\u5757\u4e0e\u6307\u6570\u5171\u632f</li>\n'
    '              <li>\u4ea7\u4e1a\u94fe\u4f4d\u7f6e\u5224\u65ad</li>\n'
    '            </ul>\n'
    '          </article>'
)
feature2 = (
    '<article class="feature-card">\n'
    '            <div class="feature-top">\n'
    '              <div class="feature-icon">\u25ce</div>\n'
    '              <div>\n'
    '                <span>Trading Watch</span>\n'
    '                <h3>AI \u76ef\u76d8</h3>\n'
    '              </div>\n'
    '            </div>\n'
    '            <p>\u628a\u590d\u76d8\u7ed3\u8bba\u53d8\u6210\u76d8\u4e2d\u9884\u6848\uff1a'
    '\u4ef7\u683c\u3001\u6da8\u8dcc\u5e45\u3001\u91cf\u80fd\u3001\u6307\u6570\u73af\u5883\u89e6\u53d1\u540e\u63d0\u9192\u4ea4\u6613\u8005\u6267\u884c\uff0c'
    '\u907f\u514d\u4e34\u76d8\u51ed\u611f\u89c9\u6539\u5267\u672c\u3002</p>\n'
    '            <ul>\n'
    '              <li>\u9884\u6848\u89e6\u53d1</li>\n'
    '              <li>\u58f0\u97f3\u63d0\u9192</li>\n'
    '              <li>\u98ce\u9669\u6761\u4ef6</li>\n'
    '              <li>\u6267\u884c\u8bb0\u5f55</li>\n'
    '            </ul>\n'
    '          </article>'
)
s = re.sub(
    r'<article class="feature-card">.*?</article>\s*\n\n          <article class="feature-card">.*?</article>',
    feature1 + "\n\n          " + feature2,
    s,
    count=1,
    flags=re.S,
)

p.write_text(s, encoding="utf-8")
