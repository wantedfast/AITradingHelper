from pathlib import Path

preview = Path("frontend-preview/index.html")
s = preview.read_text(encoding="utf-8")

repls = {
    "--gold: #d8af4b;": "--gold: #C9A646;\n      --gold-dark: #8A6A2A;\n      --gold-light: #F5D77A;\n      --gold-pale: #FFF1B8;\n      --gold-shadow: #3A2A0A;",
    "--gold-2: #ffe08a;": "--gold-2: #F5D77A;",
    "#d8af4b": "#C9A646",
    "#ffe08a": "#F5D77A",
    "#c99d37": "#C9A646",
    "#f0c869": "#F5D77A",
    "#ffda74": "#F5D77A",
    "#fff0bf": "#FFF1B8",
    "#ffe6a8": "#FFF1B8",
    "rgba(216, 175, 75": "rgba(201, 166, 70",
    "rgba(255, 224, 138": "rgba(245, 215, 122",
}
for old, new in repls.items():
    s = s.replace(old, new)

s = s.replace(
    "background: linear-gradient(135deg, var(--gold-2), var(--gold));\n"
    "      box-shadow: 0 18px 44px rgba(201, 166, 70, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.4);",
    "background: linear-gradient(135deg, #0B0B0B, #1A1406);\n"
    "      border: 1px solid var(--gold);\n"
    "      color: var(--gold-light);\n"
    "      box-shadow:\n"
    "        0 0 12px rgba(201, 166, 70, 0.35),\n"
    "        inset 0 0 8px rgba(245, 215, 122, 0.15);",
)

s = s.replace(
    ".cn-slogan {\n"
    "      margin: 18px 0 0;\n"
    "      color: var(--gold-2);",
    ".cn-slogan {\n"
    "      margin: 18px 0 0;\n"
    "      background: linear-gradient(135deg, #8A6A2A 0%, #C9A646 28%, #F5D77A 50%, #B88A2E 72%, #FFF1B8 100%);\n"
    "      -webkit-background-clip: text;\n"
    "      -webkit-text-fill-color: transparent;\n"
    "      background-clip: text;\n"
    "      color: var(--gold-light);",
)

s = s.replace(
    '<button class="gold-swatch active" style="--swatch:#C9A646" data-gold="#C9A646" data-bright="#F5D77A" aria-label="Classic gold"></button>',
    '<button class="gold-swatch active" style="--swatch:#C9A646" data-gold="#C9A646" data-bright="#F5D77A" aria-label="Premium gold"></button>',
)
s = s.replace(
    '<button class="gold-swatch" style="--swatch:#c49a2c" data-gold="#c49a2c" data-bright="#f4cf71" aria-label="Antique gold"></button>',
    '<button class="gold-swatch" style="--swatch:#8A6A2A" data-gold="#8A6A2A" data-bright="#C9A646" aria-label="Dark gold"></button>',
)
s = s.replace(
    '<button class="gold-swatch" style="--swatch:#e0b85a" data-gold="#e0b85a" data-bright="#ffe6a6" aria-label="Champagne gold"></button>',
    '<button class="gold-swatch" style="--swatch:#F5D77A" data-gold="#C9A646" data-bright="#FFF1B8" aria-label="Champagne gold"></button>',
)
s = s.replace(
    '<button class="gold-swatch" style="--swatch:#b88924" data-gold="#b88924" data-bright="#eac667" aria-label="Deep gold"></button>',
    '<button class="gold-swatch" style="--swatch:#B88A2E" data-gold="#B88A2E" data-bright="#F5D77A" aria-label="Deep gold"></button>',
)

preview.write_text(s, encoding="utf-8")

for path in [Path("frontend/app/globals.css"), Path("frontend/components/gold-magic-cube.tsx")]:
    s = path.read_text(encoding="utf-8")
    for old, new in repls.items():
        s = s.replace(old, new)
    s = s.replace(
        "background: linear-gradient(135deg, var(--gold-2), var(--gold));\n"
        "  box-shadow: 0 18px 44px rgba(201, 166, 70, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.4);",
        "background: linear-gradient(135deg, #0B0B0B, #1A1406);\n"
        "  border: 1px solid var(--gold);\n"
        "  color: var(--gold-light);\n"
        "  box-shadow:\n"
        "    0 0 12px rgba(201, 166, 70, 0.35),\n"
        "    inset 0 0 8px rgba(245, 215, 122, 0.15);",
    )
    s = s.replace(
        ".cn-slogan {\n"
        "  margin: 18px 0 0;\n"
        "  color: var(--gold-2);",
        ".cn-slogan {\n"
        "  margin: 18px 0 0;\n"
        "  background: linear-gradient(135deg, #8A6A2A 0%, #C9A646 28%, #F5D77A 50%, #B88A2E 72%, #FFF1B8 100%);\n"
        "  -webkit-background-clip: text;\n"
        "  -webkit-text-fill-color: transparent;\n"
        "  background-clip: text;\n"
        "  color: var(--gold-light);",
    )
    path.write_text(s, encoding="utf-8")
