from pathlib import Path

for path in [Path("frontend/app/globals.css"), Path("frontend/components/gold-magic-cube.tsx")]:
    s = path.read_text(encoding="utf-8")
    repls = {
        "--gold: #c9d1d9;": "--gold: #d8af4b;",
        "--gold-2: #f4f7fb;": "--gold-2: #ffe08a;",
        "rgba(195, 204, 214": "rgba(216, 175, 75",
        "rgba(238, 242, 246": "rgba(255, 224, 138",
        "#c9d1d9": "#d8af4b",
        "#f4f7fb": "#ffe08a",
        "#bfc5cc": "#c99d37",
        "#eef2f6": "#f0c869",
        "#f3f6fb": "#ffda74",
        "#fff0bf": "#fff0bf",
        "#dfe6ee": "#ffe6a8",
    }
    for old, new in repls.items():
        s = s.replace(old, new)
    s = s.replace(
        ".cube-stage::before {\n"
        '  content: "";\n'
        "  position: absolute;\n"
        "  width: 112%;\n"
        "  height: 30%;\n"
        "  left: -6%;\n"
        "  bottom: -7%;\n"
        "  background: radial-gradient(ellipse at center, rgba(220, 226, 232, 0.04), rgba(16, 18, 22, 0.18) 42%, transparent 72%);\n"
        "  filter: blur(34px);\n"
        "  transform: rotate(-5deg);\n"
        "  opacity: 0.22;\n"
        "}",
        ".cube-stage::before {\n"
        "  content: none;\n"
        "  display: none;\n"
        "}",
    )
    s = s.replace(
        "radial-gradient(circle at 40% 34%, rgba(230, 236, 242, 0.045), transparent 20%),\n"
        "    radial-gradient(circle at 50% 50%, rgba(30, 34, 40, 0.26), transparent 60%);\n"
        "  filter: blur(34px);\n"
        "  opacity: 0.32;",
        "radial-gradient(circle at 50% 50%, rgba(0, 0, 0, 0.42), transparent 62%);\n"
        "  filter: blur(34px);\n"
        "  opacity: 0.42;",
    )
    s = s.replace("    scene.add(glow);\n", "    // No floor glow: keep the cube background pure black.\n")
    path.write_text(s, encoding="utf-8")
