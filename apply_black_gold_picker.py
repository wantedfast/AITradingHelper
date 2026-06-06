from pathlib import Path

p = Path("frontend-preview/index.html")
s = p.read_text(encoding="utf-8")

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
    "#f8fbff": "#fff0bf",
    "#dfe6ee": "#ffe6a8",
}
for old, new in repls.items():
    s = s.replace(old, new)

s = s.replace(
    "radial-gradient(circle at 40% 34%, rgba(230, 236, 242, 0.045), transparent 20%),\n"
    "        radial-gradient(circle at 50% 50%, rgba(30, 34, 40, 0.26), transparent 60%);\n"
    "      filter: blur(34px);\n"
    "      opacity: 0.32;",
    "radial-gradient(circle at 50% 50%, rgba(0, 0, 0, 0.42), transparent 62%);\n"
    "      filter: blur(34px);\n"
    "      opacity: 0.42;",
)

old_stage = (
    '.cube-stage::before {\n'
    '      content: "";\n'
    '      position: absolute;\n'
    '      width: 112%;\n'
    '      height: 30%;\n'
    '      left: -6%;\n'
    '      bottom: -7%;\n'
    '      background: radial-gradient(ellipse at center, rgba(220, 226, 232, 0.04), rgba(16, 18, 22, 0.18) 42%, transparent 72%);\n'
    '      filter: blur(34px);\n'
    '      transform: rotate(-5deg);\n'
    '      opacity: 0.22;\n'
    '    }'
)
new_stage = (
    '.cube-stage::before {\n'
    '      content: none;\n'
    '      display: none;\n'
    '    }'
)
s = s.replace(old_stage, new_stage)

css_insert = """

    .gold-picker {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 22px;
      color: rgba(244, 240, 232, 0.6);
      font-size: 13px;
      font-weight: 700;
    }

    .gold-swatches {
      display: flex;
      gap: 9px;
      flex-wrap: wrap;
    }

    .gold-swatch {
      width: 28px;
      height: 28px;
      border: 1px solid rgba(255, 255, 255, 0.22);
      border-radius: 999px;
      background: var(--swatch);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.36), 0 0 16px color-mix(in srgb, var(--swatch), transparent 64%);
      cursor: pointer;
    }

    .gold-swatch.active {
      outline: 2px solid rgba(255, 255, 255, 0.72);
      outline-offset: 3px;
    }
"""
s = s.replace("    .visual {\n", css_insert + "\n    .visual {\n", 1)

picker = """
          <div class="gold-picker">
            <span>Gold tone</span>
            <div class="gold-swatches" aria-label="Choose gold color">
              <button class="gold-swatch active" style="--swatch:#d8af4b" data-gold="#d8af4b" data-bright="#ffe08a" aria-label="Classic gold"></button>
              <button class="gold-swatch" style="--swatch:#c49a2c" data-gold="#c49a2c" data-bright="#f4cf71" aria-label="Antique gold"></button>
              <button class="gold-swatch" style="--swatch:#e0b85a" data-gold="#e0b85a" data-bright="#ffe6a6" aria-label="Champagne gold"></button>
              <button class="gold-swatch" style="--swatch:#b88924" data-gold="#b88924" data-bright="#eac667" aria-label="Deep gold"></button>
            </div>
          </div>
"""
s = s.replace('          <div class="actions">\n            <a class="primary" href="/v2/">Upload Trades</a>\n            <a class="secondary" href="#features">Explore Features</a>\n          </div>', '          <div class="actions">\n            <a class="primary" href="/v2/">Upload Trades</a>\n            <a class="secondary" href="#features">Explore Features</a>\n          </div>' + picker, 1)

# Tag materials by role and collect them for live palette switching.
s = s.replace(
    'return [\n'
    '        new THREE.MeshPhysicalMaterial({ ...options, color: "#c99d37", emissive: gold, emissiveIntensity: 0.025 }),\n'
    '        new THREE.MeshPhysicalMaterial({ ...options, color: "#080706" }),\n'
    '        new THREE.MeshPhysicalMaterial({ ...options, color: "#f0c869", emissive: gold, emissiveIntensity: 0.035 }),\n'
    '        new THREE.MeshPhysicalMaterial({ ...options, color: "#12100b" }),\n'
    '        new THREE.MeshPhysicalMaterial({ ...options, color: "#17130b" }),\n'
    '        new THREE.MeshPhysicalMaterial({ ...options, color: "#050505" })\n'
    '      ];',
    'const materials = [\n'
    '        new THREE.MeshPhysicalMaterial({ ...options, color: "#c99d37", emissive: gold, emissiveIntensity: 0.025 }),\n'
    '        new THREE.MeshPhysicalMaterial({ ...options, color: "#080706" }),\n'
    '        new THREE.MeshPhysicalMaterial({ ...options, color: "#f0c869", emissive: gold, emissiveIntensity: 0.035 }),\n'
    '        new THREE.MeshPhysicalMaterial({ ...options, color: "#12100b" }),\n'
    '        new THREE.MeshPhysicalMaterial({ ...options, color: "#17130b" }),\n'
    '        new THREE.MeshPhysicalMaterial({ ...options, color: "#050505" })\n'
    '      ];\n'
    '      materials[0].userData.tone = "gold";\n'
    '      materials[2].userData.tone = "bright";\n'
    '      return materials;',
)

s = s.replace(
    '    scene.add(glow);\n\n    const scratchGroup = new THREE.Group();',
    '    // No floor glow: keep the cube background pure black, without the fan-shaped stage wash.\n\n    const scratchGroup = new THREE.Group();',
)

switcher = """

    function applyGold(goldHex, brightHex) {
      const goldColor = new THREE.Color(goldHex);
      const brightColor = new THREE.Color(brightHex);
      document.documentElement.style.setProperty("--gold", goldHex);
      document.documentElement.style.setProperty("--gold-2", brightHex);
      edgeMaterial.color.set(brightHex);
      key.color.set(brightHex);
      softTop.color.set(brightHex);
      rim.color.set(brightHex);
      cubelets.forEach((cubelet) => {
        cubelet.material.forEach((material) => {
          if (material.userData.tone === "gold") {
            material.color.copy(goldColor);
            material.emissive.copy(goldColor);
          }
          if (material.userData.tone === "bright") {
            material.color.copy(brightColor);
            material.emissive.copy(goldColor);
          }
        });
      });
    }

    document.querySelectorAll(".gold-swatch").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".gold-swatch").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        applyGold(button.dataset.gold, button.dataset.bright);
      });
    });
"""
s = s.replace("    function resize() {\n", switcher + "\n    function resize() {\n", 1)

p.write_text(s, encoding="utf-8")
