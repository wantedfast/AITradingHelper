// 量能宽广度监控：涨家占比 / 涨额占比 / 额价差 / Arms / 麦克连摆
// 运行：node breadth.mjs   然后打开 http://localhost:3210
// 数据来源：腾讯公开行情接口 qt.gtimg.cn（沪深京全部 A 股），无需任何依赖。
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// ---------- 可调参数 ----------
const CFG = {
  port: Number(process.env.PORT) || 3210,
  refreshSec: 60,          // 盘中刷新间隔（秒）
  // 预警阈值是我设的起点，不是博主给的；视频里 12 号上午的读数是 39% / 65.43% / 26 / 0.34
  warn: { upCountBelow: 45, spreadAbove: 15, armsBelow: 0.6 },
  bigN: 300,               // 总市值前 300 只算大盘蓝筹，其余算中小盘
  bigGap: 15,              // 大盘股上涨比例比中小盘高出这么多个点，才算"钱在蓝筹"
};
// ------------------------------

const DIR = path.dirname(fileURLToPath(import.meta.url));
const DATA = path.join(DIR, 'data');
fs.mkdirSync(DATA, { recursive: true });
const DAILY_FILE = path.join(DATA, 'daily.json');
const INDEXES = ['sh000001', 'sz399001', 'sh000300', 'sh000016', 'sh000905', 'sh000852'];

const readJson = (f, d) => { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch { return d; } };
const bj = () => new Date(Date.now() + 8 * 3600e3); // 北京时间（用 UTC 方法读取）
const bjDate = () => bj().toISOString().slice(0, 10);
const bjHM = () => bj().toISOString().slice(11, 16);
function isTrading() {
  const d = bj(), day = d.getUTCDay(), m = d.getUTCHours() * 60 + d.getUTCMinutes();
  if (day === 0 || day === 6) return false;
  return (m >= 565 && m <= 690) || (m >= 780 && m <= 905); // 9:25-11:30, 13:00-15:05
}

// 腾讯行情：一次请求可带几百个代码，返回 GBK 文本，字段用 ~ 分隔
async function quote(codes) {
  for (let i = 0; i < 3; i++) {
    try {
      const r = await fetch('https://qt.gtimg.cn/q=' + codes.join(','), { signal: AbortSignal.timeout(15000) });
      if (r.ok) {
        const txt = new TextDecoder('gbk').decode(await r.arrayBuffer());
        return txt.split(';').map(s => s.split('~')).filter(f => f.length > 40)
          .map(f => ({ code: f[0].match(/v_(\w+)=/)?.[1], name: f[1], price: Number(f[3]), f3: Number(f[32]), f6: Number(f[37]) * 1e4, cap: Number(f[45]) }));
      }
    } catch { /* retry */ }
    await new Promise(r => setTimeout(r, 600 * (i + 1)));
  }
  throw new Error('行情请求失败');
}

async function quoteMany(codes) {
  const chunks = []; for (let i = 0; i < codes.length; i += 800) chunks.push(codes.slice(i, i + 800));
  const out = [];
  await Promise.all(Array.from({ length: 4 }, async () => { while (chunks.length) out.push(...await quote(chunks.shift())); }));
  return out;
}

// A 股代码段：沪主板、科创板、深主板、创业板、北交所。每天扫一次，之后只查有效代码。
function candidates() {
  const c = [], add = (p, a, b) => { for (let i = a; i <= b; i++) c.push(p + String(i).padStart(6, '0')); };
  add('sh', 600000, 605999); add('sh', 688000, 689999); add('sz', 1, 3999); add('sz', 300000, 301999); add('bj', 920000, 920999);
  return c;
}

let codeCache = { date: null, codes: null };
async function fetchAllStocks() {
  const today = bjDate();
  if (codeCache.date !== today) {
    const f = path.join(DATA, 'codes.json'), saved = readJson(f, null);
    if (saved?.date === today) codeCache = saved;
    else {
      const all = await quoteMany(candidates());
      codeCache = { date: today, codes: all.map(r => r.code).filter(Boolean) };
      fs.writeFileSync(f, JSON.stringify(codeCache));
      if (all.length < 4000) throw new Error(`代码扫描只得到 ${all.length} 只，本次作废`);
      return all;
    }
  }
  const rows = await quoteMany(codeCache.codes);
  if (rows.length < codeCache.codes.length * 0.98) throw new Error(`只取到 ${rows.length}/${codeCache.codes.length} 只，本次作废`);
  return rows;
}

function tally(list) {
  let up = 0, down = 0, flat = 0, upAmt = 0, downAmt = 0, flatAmt = 0;
  for (const r of list) {
    if (r.f3 > 0) { up++; upAmt += r.f6; } else if (r.f3 < 0) { down++; downAmt += r.f6; } else { flat++; flatAmt += r.f6; }
  }
  const n = up + down + flat, amt = upAmt + downAmt + flatAmt;
  const pcts = list.map(r => r.f3).sort((a, b) => a - b);
  return { n, up, down, flat, upAmt, downAmt, amt, upCountPct: n ? up / n * 100 : null, median: n ? pcts[n >> 1] : null };
}

function compute(rows) {
  const live = rows.filter(r => Number.isFinite(r.f3) && Number.isFinite(r.f6) && r.f6 > 0); // 剔除停牌/无成交
  const all = tally(live);
  const upAmtPct = all.amt ? all.upAmt / all.amt * 100 : null;      // 涨额占比
  const spread = all.upCountPct != null && upAmtPct != null ? upAmtPct - all.upCountPct : null; // 额价差
  const arms = all.up && all.down && all.upAmt && all.downAmt ? (all.up / all.down) / (all.upAmt / all.downAmt) : null; // Arms(TRIN)，用成交额
  // 按总市值排序，前 bigN 只算大盘蓝筹，其余算中小盘
  const byCap = [...live].sort((a, b) => (b.cap || 0) - (a.cap || 0));
  const big = tally(byCap.slice(0, CFG.bigN)), small = tally(byCap.slice(CFG.bigN));
  const grp = g => ({ n: g.n, upCountPct: g.upCountPct, median: g.median, amtShare: all.amt ? g.amt / all.amt * 100 : null, upAmtShare: all.upAmt ? g.upAmt / all.upAmt * 100 : null });
  return { ...all, upAmtPct, spread, arms, big: grp(big), small: grp(small) };
}

// 麦克连摆：比率调整版 = EMA19 - EMA39，输入为 (涨家-跌家)/(涨家+跌家)*1000
function mcclellan(daily) {
  const days = Object.keys(daily).sort();
  if (!days.length) return { days: 0, value: null, series: [] };
  let e19 = null, e39 = null; const series = [];
  for (const d of days) {
    const { up, down } = daily[d]; const x = (up - down) / (up + down) * 1000;
    e19 = e19 == null ? x : e19 + 0.1 * (x - e19);
    e39 = e39 == null ? x : e39 + 0.05 * (x - e39);
    series.push({ d, v: e19 - e39 });
  }
  const v = series.at(-1).v, prev = series.at(-4)?.v ?? null; // 和 3 个交易日前比，看方向
  return { days: days.length, value: v, rising: prev == null ? null : v > prev, series: series.slice(-60) };
}

// 三层推断：大资金在干什么 → 可不可持续 → 接下来大概率怎么走
// 推断逻辑照搬视频；判断线是自定的，历史表现见 hist（来自 backtest.mjs）
function verdict(s, idx, mcl) {
  const sh = idx.find(i => i.code === '000001'); const w = CFG.warn;
  if (s.upCountPct == null || !sh) return { key: 'none', level: 'none', title: '暂无数据', evidence: [] };
  const f = (x, n = 1) => x == null ? '–' : x.toFixed(n), sg = x => (x > 0 ? '+' : '') + f(x, 2) + '%';
  const up = sh.pct > 0, gap = s.big.upCountPct - s.small.upCountPct;
  const crowd = s.upCountPct < w.upCountBelow && s.spread > w.spreadAbove && s.arms != null && s.arms < w.armsBelow;
  const inBig = gap >= CFG.bigGap;
  const ev = [
    `上证指数 ${sg(sh.pct)}，全市场股票涨跌幅中位数 ${sg(s.median)}`,
    `上涨股票占 ${f(s.upCountPct)}%（涨 ${s.up} / 跌 ${s.down}）`,
    `上涨股票拿走了 ${f(s.upAmtPct)}% 的成交额，额价差 ${f(s.spread)}，Arms ${f(s.arms, 2)}`,
    `市值前 ${CFG.bigN} 的大盘股有 ${f(s.big.upCountPct)}% 在涨，其余中小盘有 ${f(s.small.upCountPct)}% 在涨；大盘股占全市场成交额 ${f(s.big.amtShare)}%`,
  ];
  if (mcl?.days >= 39) ev.push(`麦克连摆 ${f(mcl.value, 0)}，${mcl.rising ? '在上行' : '在下行'}（${mcl.value > 0 ? '零轴上方' : '零轴下方'}）`);
  const R = (key, level, title, money, sustain, next) => ({ key, level, title, money, sustain, next, evidence: ev });

  if (up && crowd && inBig) return R('fake', 'warn', '假反弹：大资金抱团蓝筹拉指数',
    '钱集中在大盘蓝筹，指数被拉红，多数股票在跌', '不可持续：靠少数权重股撑不住整个市场', '按视频逻辑，上方空间有限，大概率转头向下');
  if (up && crowd) return R('fake', 'warn', '假上涨：资金抱团少数股票',
    '钱集中在少数上涨股票上，但不是大盘蓝筹，多数股票在跌', '不可持续：上涨没有扩散', '按视频逻辑，指数的涨不可信，大概率回落');
  if (up && s.upCountPct >= 60 && Math.abs(s.spread) < 10) return R('real', 'good', '真普涨：资金全面进场',
    '钱分散在大多数股票上，大盘股和中小盘一起涨', '可持续性较好：上涨有广度', '大概率延续修复');
  if (!up && s.upCountPct <= 30) return R('selloff', 'bad', '真下跌：资金全面撤退',
    '多数股票在跌，没有资金托底', '下跌是真实的，不是指数失真', '未见止跌信号');
  if (!up && s.upCountPct < 45 && inBig) return R('prop', 'bad', '蓝筹护盘：实际比指数更弱',
    '大盘蓝筹相对抗跌，中小盘跌得更多', '指数被蓝筹托着，掩盖了多数股票的弱势', '偏弱，护盘资金一松指数会补跌');
  if (!up && s.upCountPct >= 55) return R('drag', 'good', '权重拖累：实际比指数更强',
    '指数被权重股拖着跌，多数股票在涨', '视频没有讲这种情况，这里按同一逻辑反推', '个股行情好于指数表现');
  if (up) return R('none', 'none', '普通上涨：谈不上普涨，也没有明显抱团',
    '没有看出大资金的明确动作', '证据不足', '没有结论');
  return R('none', 'none', '普通下跌：没有极端特征', '没有看出大资金的明确动作', '证据不足', '没有结论');
}

const state = { updated: null, error: null, trading: false, snap: null, indexes: [], intraday: [], mcl: null, verdict: null, cfg: CFG.warn };
let intradayDate = null;

async function tick() {
  try {
    const today = bjDate();
    const file = path.join(DATA, `intraday-${today}.json`);
    if (intradayDate !== today) { intradayDate = today; state.intraday = readJson(file, []); }
    const [rows, ix] = await Promise.all([fetchAllStocks(), quote(INDEXES)]);
    const s = compute(rows);
    state.indexes = INDEXES.map(c => ix.find(i => i.code === c)).filter(Boolean).map(i => ({ code: i.code.slice(2), name: i.name, price: i.price, pct: i.f3 }));
    state.snap = s; state.trading = isTrading(); state.updated = `${today} ${bjHM()}`; state.error = null;
    const day = bj().getUTCDay(), weekday = day >= 1 && day <= 5;
    if (state.trading) {
      if (state.intraday.at(-1)?.t === bjHM()) state.intraday.pop(); // 同一分钟只留一个点
      state.intraday.push({ t: bjHM(), c: s.upCountPct, a: s.upAmtPct, sp: s.spread, ar: s.arms, sh: state.indexes[0]?.pct ?? null });
      fs.writeFileSync(file, JSON.stringify(state.intraday));
    }
    // 交易日 9:25 之后的最新一次读数记为当日值（收盘后即为收盘值），供麦克连摆使用
    const mins = bj().getUTCHours() * 60 + bj().getUTCMinutes();
    const daily = readJson(DAILY_FILE, {});
    if (weekday && mins >= 565 && s.up + s.down > 0) {
      daily[today] = { up: s.up, down: s.down, upAmtPct: s.upAmtPct, arms: s.arms };
      fs.writeFileSync(DAILY_FILE, JSON.stringify(daily, null, 1));
    }
    state.mcl = mcclellan(daily);
    state.verdict = verdict(s, state.indexes, state.mcl);
    state.verdict.hist = readJson(path.join(DATA, 'backtest-result.json'), null)?.classes?.[state.verdict.key] ?? null;
    state.histBase = readJson(path.join(DATA, 'backtest-result.json'), null)?.classBase ?? null;
    const f = (x, n = 1) => x == null ? '-' : x.toFixed(n);
    console.log(`[${state.updated}] 涨家 ${f(s.upCountPct)}%  涨额 ${f(s.upAmtPct)}%  额价差 ${f(s.spread)}  Arms ${f(s.arms, 2)}  大盘/中小盘上涨 ${f(s.big.upCountPct)}%/${f(s.small.upCountPct)}%  | ${state.verdict.title}`);
  } catch (e) {
    state.error = String(e.message || e); console.error('刷新失败:', state.error);
  }
}

const PAGE = fs.readFileSync(path.join(DIR, 'dashboard.html'), 'utf8');
http.createServer((req, res) => {
  if (req.url.startsWith('/api/state')) {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    return res.end(JSON.stringify(state));
  }
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(PAGE);
}).listen(CFG.port, '127.0.0.1', () => console.log(`已启动：http://localhost:${CFG.port}`));

await tick();
setInterval(() => { if (isTrading() || !state.snap) tick(); }, CFG.refreshSec * 1000);
// 收盘后补记一次收盘值
setInterval(() => { const m = bj().getUTCHours() * 60 + bj().getUTCMinutes(); if (m >= 906 && m <= 908) tick(); }, 60 * 1000);
