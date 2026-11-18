from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BREADTH = ROOT / "market_breadth" / "breadth.mjs"


class MarketBreadthVerdictRulesTest(unittest.TestCase):
    def test_blue_chip_support_precedes_overlapping_selloff(self) -> None:
        result = self._run_verdict(
            sh_pct=-0.2,
            up_count_pct=25,
            big_up_count_pct=50,
            small_up_count_pct=20,
        )
        self.assertEqual(result["key"], "prop")

    def test_ordinary_selloff_without_blue_chip_strength_stays_selloff(self) -> None:
        result = self._run_verdict(
            sh_pct=-0.2,
            up_count_pct=25,
            big_up_count_pct=25,
            small_up_count_pct=20,
        )
        self.assertEqual(result["key"], "selloff")

    def _run_verdict(
        self,
        *,
        sh_pct: float,
        up_count_pct: float,
        big_up_count_pct: float,
        small_up_count_pct: float,
    ) -> dict[str, object]:
        script = r"""
const fs = require('node:fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('function verdict(');
const end = source.indexOf('\n}\n\nconst state', start) + 2;
if (start < 0 || end < 2) throw new Error('verdict function not found');
const verdictSource = source.slice(start, end);
const CFG = {
  warn: { upCountBelow: 45, spreadAbove: 15, armsBelow: 0.6 },
  bigN: 300,
  bigGap: 15,
};
const verdict = Function('CFG', `${verdictSource}; return verdict;`)(CFG);
const input = JSON.parse(process.argv[2]);
const snapshot = {
  upCountPct: input.upCountPct,
  median: -1,
  up: 1000,
  down: 3000,
  upAmtPct: 30,
  spread: 5,
  arms: 1,
  big: { upCountPct: input.bigUpCountPct, amtShare: 40 },
  small: { upCountPct: input.smallUpCountPct },
};
const result = verdict(snapshot, [{ code: '000001', pct: input.shPct }], null);
process.stdout.write(JSON.stringify(result));
"""
        payload = json.dumps(
            {
                "shPct": sh_pct,
                "upCountPct": up_count_pct,
                "bigUpCountPct": big_up_count_pct,
                "smallUpCountPct": small_up_count_pct,
            }
        )
        completed = subprocess.run(
            ["node", "-e", script, str(BREADTH), payload],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return json.loads(completed.stdout)


if __name__ == "__main__":
    unittest.main()
