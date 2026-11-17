// 回测：按收盘数据重算每天的 涨家占比 / 涨额占比 / 额价差 / Arms，
// 统计"抱团护指数"信号出现后 1/5/20 个交易日指数的表现。
// 运行：node backtest.mjs        （首次下载约几分钟，之后用缓存）
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const DIR = path.dirname(fileURLToPath(import.meta.url));
const DATA = path.join(DIR, 'data');
const AGG = path.join(DATA, 'backtest-agg.json');
const DAYS = 520; // 约两年
const readJson = (f, d) => { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch { return d; } };

async function get(url) {
  for (let i = 0; i < 4; i++) {
    try { const r = await fetch(url, { signal: AbortSignal.timeout(15000) }); if (r.ok) return await r.json(); } catch { /* retry */ }
    await new Promise(r => setTimeout(r, 800 * (i + 1)));
  }
  return null;
}

async function download() {
  const codes = readJson(path.join(DATA, 'codes.json'), null)?.codes;
  if (!codes) throw new Error('缺少 data/codes.json，请先运行一次 node breadth.mjs');
  const agg = {}; let done = 0, failed = 0;
  const queue = [...codes];
  await Promise.all(Array.from({ length: 8 }, async () => {
    while (queue.length) {
      const c = queue.shift();
      const j = await get(`https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get?param=${c},day,,,${DAYS},qfq`);
      const rows = j?.data?.[c]?.qfqday || j?.data?.[c]?.day;
      if (!rows) failed++;
      else for (let i = 1; i < rows.length; i++) {
        const prev = Number(rows[i - 1][2]), close = Number(rows[i][2]), amt = Number(rows[i][8]);
        if (!(prev > 0) || !(amt > 0)) continue;
        const a = agg[rows[i][0]] ??= { up: 0, down: 0, flat: 0, upAmt: 0, downAmt: 0, flatAmt: 0 };
        const pct = Math.round((close / prev - 1) * 1e4);
        if (pct > 0) { a.up++; a.upAmt += amt; } else if (pct < 0) { a.down++; a.downAmt += amt; } else { a.flat++; a.flatAmt += amt; }
      }
      if (++done % 500 === 0) console.log(`已下载 ${done}/${codes.length}`);
    }
  }));
  const idx = {};
  for (const c of ['sh000001', 'sh000300', 'sh000852']) {
    const j = await get(`https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${c},day,,,${DAYS + 40},qfq`);
    idx[c] = (j.data[c].day || j.data[c].qfqday).map(r => [r[0], Number(r[2])]);
  }
  const out = { stocks: codes.length, failed, agg, idx };
  fs.writeFileSync(AGG, JSON.stringify(out));
  console.log(`下载完成：${codes.length} 只，失败 ${failed} 只`);
  return out;
}

const D = readJson(AGG, null) || await download();
const today = new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
const sh = D.idx.sh000001, shMap = new Map(sh.map((r, i) => [r[0], i]));
const closeOf = c => new Map(D.idx[c]);
const c300 = closeOf('sh000300'), c1000 = closeOf('sh000852');

// 每天的指标
const days = Object.keys(D.agg).sort().filter(d => d < today && shMap.has(d) && D.agg[d].up + D.agg[d].down > 3000).map(d => {
  const a = D.agg[d], n = a.up + a.down + a.flat, amt = a.upAmt + a.downAmt + a.flatAmt, i = shMap.get(d);
  const upC = a.up / n * 100, upA = a.upAmt / amt * 100;
  return { d, i, upC, upA, spread: upA - upC, arms: (a.up / a.down) / (a.upAmt / a.downAmt), shPct: (sh[i][1] / sh[i - 1][1] - 1) * 100 };
});

const fwd = (map, arr, i, k) => { const a = map.get(arr[i][0]), b = arr[i + k] && map.get(arr[i + k][0]); return a && b ? (b / a - 1) * 100 : null; };
const shClose = new Map(sh);
const mean = xs => xs.reduce((s, x) => s + x, 0) / xs.length;
const median = xs => { const s = [...xs].sort((a, b) => a - b), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
function stats(set, map) {
  const out = {};
  for (const k of [1, 5, 20]) {
    const xs = set.map(x => fwd(map, sh, x.i, k)).filter(v => v != null);
    out[k] = xs.length ? { n: xs.length, mean: mean(xs), median: median(xs), downRate: xs.filter(v => v < 0).length / xs.length * 100 } : null;
  }
  return out;
}
const fmt = s => [1, 5, 20].map(k => s[k] ? `${k}日: 均值 ${s[k].mean.toFixed(2)}% 中位 ${s[k].median.toFixed(2)}% 下跌占比 ${s[k].downRate.toFixed(0)}% (n=${s[k].n})` : `${k}日: 无`).join('\n    ');

const rules = {
  '严格版（监控页现在用的）：上证收红 且 涨家<45 且 额价差>15 且 Arms<0.6': x => x.shPct > 0 && x.upC < 45 && x.spread > 15 && x.arms < 0.6,
  '宽松版：上证收红 且 涨家<50 且 额价差>10': x => x.shPct > 0 && x.upC < 50 && x.spread > 10,
  '仅背离：上证收红 且 涨家<45': x => x.shPct > 0 && x.upC < 45,
  '对照：上证收红 且 涨家>=60（普涨）': x => x.shPct > 0 && x.upC >= 60,
};

console.log(`\n样本区间 ${days[0].d} 至 ${days.at(-1).d}，共 ${days.length} 个交易日，${D.stocks} 只股票（下载失败 ${D.failed}）`);
const result = { range: [days[0].d, days.at(-1).d], nDays: days.length, rules: {} };
console.log('\n【基准】所有交易日之后上证指数的表现');
const base = stats(days, shClose); console.log('    ' + fmt(base)); result.base = base;
for (const [name, fn] of Object.entries(rules)) {
  const set = days.filter(fn);
  console.log(`\n【${name}】触发 ${set.length} 天`);
  const s = { sh: stats(set, shClose), hs300: stats(set, c300), zz1000: stats(set, c1000) };
  console.log('  上证:\n    ' + fmt(s.sh)); console.log('  中证1000:\n    ' + fmt(s.zz1000));
  if (set.length <= 25) console.log('  触发日期: ' + set.map(x => `${x.d}(涨家${x.upC.toFixed(0)} 差${x.spread.toFixed(0)} Arms${x.arms.toFixed(2)})`).join(', '));
  result.rules[name] = { n: set.length, dates: set.map(x => x.d), ...s };
}
// 额价差分五档，看和后续收益有没有单调关系
console.log('\n【额价差分五档】之后 5 日上证 / 中证1000 均值');
const sorted = [...days].sort((a, b) => a.spread - b.spread), q = Math.floor(sorted.length / 5);
result.quintiles = [];
for (let g = 0; g < 5; g++) {
  const set = sorted.slice(g * q, g === 4 ? sorted.length : (g + 1) * q);
  const a = stats(set, shClose)[5], b = stats(set, c1000)[5];
  console.log(`  第${g + 1}档 额价差 ${set[0].spread.toFixed(1)} ~ ${set.at(-1).spread.toFixed(1)}: 上证 ${a.mean.toFixed(2)}%  中证1000 ${b.mean.toFixed(2)}%  (n=${a.n})`);
  result.quintiles.push({ lo: set[0].spread, hi: set.at(-1).spread, sh5: a.mean, zz5: b.mean, n: a.n });
}
const nov = days.filter(x => x.d >= '2026-11-09');
console.log('\n【最近几天收盘读数】'); for (const x of nov) console.log(`  ${x.d} 上证 ${x.shPct.toFixed(2)}%  涨家 ${x.upC.toFixed(1)}  涨额 ${x.upA.toFixed(1)}  额价差 ${x.spread.toFixed(1)}  Arms ${x.arms.toFixed(2)}`);
// 监控页每种结论的历史表现（收盘数据；"蓝筹护盘"需要历史市值，没有回测）
const classes = {
  fake: x => x.shPct > 0 && x.upC < 45 && x.spread > 15 && x.arms < 0.6,
  real: x => x.shPct > 0 && x.upC >= 60 && Math.abs(x.spread) < 10,
  selloff: x => x.shPct <= 0 && x.upC <= 30,
  drag: x => x.shPct <= 0 && x.upC >= 55,
};
const brief = set => { const s = stats(set, shClose); return { n: set.length, d5: s[5], d20: s[20] }; };
result.classBase = brief(days); result.classes = {};
console.log('\n【监控页各结论的历史表现】之后 5 日 / 20 日上证');
for (const [k, fn] of Object.entries(classes)) {
  const b = result.classes[k] = brief(days.filter(fn));
  console.log(`  ${k}: ${b.n} 天  5日 均值 ${b.d5?.mean.toFixed(2)}% 下跌占比 ${b.d5?.downRate.toFixed(0)}%  |  20日 均值 ${b.d20?.mean.toFixed(2)}% 下跌占比 ${b.d20?.downRate.toFixed(0)}%`);
}
fs.writeFileSync(path.join(DATA, 'backtest-result.json'), JSON.stringify(result, null, 1));

// 把历史每日涨跌家数写进 daily.json，监控页的麦克连摆就不用再等 39 天
const dailyFile = path.join(DATA, 'daily.json'), daily = readJson(dailyFile, {});
for (const d of Object.keys(D.agg)) if (d < today && !daily[d] && D.agg[d].up + D.agg[d].down > 3000) daily[d] = { up: D.agg[d].up, down: D.agg[d].down };
fs.writeFileSync(dailyFile, JSON.stringify(daily));
console.log(`\ndaily.json 现有 ${Object.keys(daily).length} 个交易日`);
