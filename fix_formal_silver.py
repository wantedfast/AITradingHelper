from pathlib import Path

files = [
    Path("frontend/app/globals.css"),
    Path("frontend/components/gold-magic-cube.tsx"),
]

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

for path in files:
    s = path.read_text(encoding="utf-8")
    for old, new in repls.items():
        s = s.replace(old, new)
    s = s.replace(
        "radial-gradient(circle at 38% 31%, rgba(238, 242, 246, 0.08), transparent 18%),\n"
        "    radial-gradient(circle at 62% 68%, rgba(255, 255, 255, 0.03), transparent 22%),\n"
        "    radial-gradient(circle at 50% 50%, rgba(195, 204, 214, 0.045), transparent 58%);\n"
        "  filter: blur(28px);\n"
        "  opacity: 0.34;",
        "radial-gradient(circle at 40% 34%, rgba(230, 236, 242, 0.045), transparent 20%),\n"
        "    radial-gradient(circle at 50% 50%, rgba(30, 34, 40, 0.26), transparent 60%);\n"
        "  filter: blur(34px);\n"
        "  opacity: 0.32;",
    )
    s = s.replace(
        "background: radial-gradient(ellipse at center, rgba(238, 242, 246, 0.08), rgba(195, 204, 214, 0.025) 36%, transparent 68%);\n"
        "  filter: blur(28px);\n"
        "  transform: rotate(-5deg);\n"
        "  opacity: 0.28;",
        "background: radial-gradient(ellipse at center, rgba(220, 226, 232, 0.04), rgba(16, 18, 22, 0.18) 42%, transparent 72%);\n"
        "  filter: blur(34px);\n"
        "  transform: rotate(-5deg);\n"
        "  opacity: 0.22;",
    )
    path.write_text(s, encoding="utf-8")
