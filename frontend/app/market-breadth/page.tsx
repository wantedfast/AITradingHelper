"use client";

import type { EChartsOption } from "echarts";
import { Activity, AlertTriangle, ArrowRight, BarChart3, CheckCircle2, Clock3, Loader2, LockKeyhole, RefreshCcw, ShieldAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { FinancialDisclaimer } from "@/components/financial-disclaimer";
import { MainSidebar, MobileFeatureNav } from "@/components/main-sidebar";
import { MarketBreadthChart } from "@/components/market-breadth-chart";
import { ApiError, apiFetch, getAuthToken, storeUser, usageBillingText, type UserProfile } from "@/lib/auth-client";

type BillingStatus = "charged" | "pending_view" | "membership_free" | "admin_free";

type AccessPayload = {
  billing_status: BillingStatus;
  billing_cost?: number;
  billing_date?: string;
  user?: UserProfile;
};

type BreadthGroup = {
  n: number;
  upCountPct: number;
  median: number;
  amtShare: number;
  upAmtShare: number;
};

type BreadthSnapshot = {
  n: number;
  up: number;
  down: number;
  flat: number;
  upAmt: number;
  downAmt: number;
  amt: number;
  upCountPct: number;
  upAmtPct: number;
  spread: number;
  arms: number;
  median: number;
  big: BreadthGroup;
  small: BreadthGroup;
};

type HistoricalWindow = { n: number; mean: number; median: number; downRate: number };
type HistoricalPerformance = { n: number; d5?: HistoricalWindow; d20?: HistoricalWindow };

type BreadthState = {
  updated: string | null;
  error: string | null;
  trading: boolean;
  snap: BreadthSnapshot | null;
  indexes: Array<{ code: string; name: string; price: number; pct: number }>;
  intraday: Array<{ t: string; c: number; a: number; sp: number; ar: number; sh: number | null }>;
  mcl: { days: number; value: number | null; rising?: boolean | null; series: Array<{ d: string; v: number }> } | null;
  verdict: {
    key: "fake" | "real" | "selloff" | "prop" | "drag" | "none";
    level: "warn" | "good" | "bad" | "none";
    title: string;
    money: string;
    sustain: string;
    next: string;
    evidence: string[];
    hist: HistoricalPerformance | null;
  } | null;
  histBase?: HistoricalPerformance | null;
  cfg?: { upCountBelow?: number; spreadAbove?: number; armsBelow?: number };
};

const AXIS = "rgba(236,231,214,.48)";
const GRID = "rgba(236,231,214,.09)";
const TOOLTIP: EChartsOption["tooltip"] = {
  trigger: "axis",
  backgroundColor: "rgba(8,12,12,.96)",
  borderColor: "rgba(226,188,66,.45)",
  textStyle: { color: "#f4efdf" },
};

export default function MarketBreadthPage() {
  const router = useRouter();
  const [access, setAccess] = useState<AccessPayload | null>(null);
  const [state, setState] = useState<BreadthState | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState("");

  const loadState = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const payload = await apiFetch<BreadthState>("/api/market-breadth/state");
      setState(payload);
      setMessage("");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        router.replace(`/auth?redirect=${encodeURIComponent("/market-breadth")}`);
        return;
      }
      setMessage(error instanceof Error ? error.message : "读取市场实时数据失败，请稍后重试。");
    } finally {
      if (!silent) setLoading(false);
    }
  }, [router]);

  const loadAccess = useCallback(async () => {
    if (!getAuthToken()) {
      router.replace(`/auth?redirect=${encodeURIComponent("/market-breadth")}`);
      return;
    }
    setLoading(true);
    try {
      const payload = await apiFetch<AccessPayload>("/api/market-breadth/access");
      if (payload.user) storeUser(payload.user);
      setAccess(payload);
      if (payload.billing_status !== "pending_view") await loadState();
      else setLoading(false);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        router.replace(`/auth?redirect=${encodeURIComponent("/market-breadth")}`);
        return;
      }
      setMessage(error instanceof Error ? error.message : "读取访问状态失败，请稍后重试。");
      setLoading(false);
    }
  }, [loadState, router]);

  useEffect(() => {
    void loadAccess();
  }, [loadAccess]);

  const canRead = Boolean(access && access.billing_status !== "pending_view");

  useEffect(() => {
    if (!canRead) return;
    const timer = window.setInterval(() => void loadState(true), 60_000);
    return () => window.clearInterval(timer);
  }, [canRead, loadState]);

  async function confirmAccess() {
    setConfirming(true);
    setMessage("");
    try {
      const payload = await apiFetch<AccessPayload>("/api/market-breadth/ack", { method: "POST" });
      if (payload.user) {
        storeUser(payload.user);
        setMessage(`今天已解锁。${usageBillingText(payload.user)}`);
      }
      setAccess(payload);
      await loadState();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "确认查看失败，请稍后重试。");
    } finally {
      setConfirming(false);
    }
  }

  const intradayOption = useMemo<EChartsOption>(() => ({
    animation: false,
    tooltip: TOOLTIP,
    legend: { top: 0, textStyle: { color: "#b9c2bd" }, data: ["上涨家数占比", "上涨成交额占比", "额价差"] },
    grid: { left: 44, right: 22, top: 48, bottom: 30 },
    xAxis: { type: "category", boundaryGap: false, data: state?.intraday.map((row) => row.t) || [], axisLabel: { color: AXIS }, axisLine: { lineStyle: { color: GRID } } },
    yAxis: { type: "value", axisLabel: { color: AXIS, formatter: "{value}%" }, splitLine: { lineStyle: { color: GRID } } },
    series: [
      { name: "上涨家数占比", type: "line", showSymbol: false, data: state?.intraday.map((row) => round(row.c)) || [], lineStyle: { color: "#e95757", width: 2 }, itemStyle: { color: "#e95757" } },
      { name: "上涨成交额占比", type: "line", showSymbol: false, data: state?.intraday.map((row) => round(row.a)) || [], lineStyle: { color: "#e4bd43", width: 2 }, itemStyle: { color: "#e4bd43" } },
      { name: "额价差", type: "line", showSymbol: false, data: state?.intraday.map((row) => round(row.sp)) || [], lineStyle: { color: "#65c5cf", width: 2 }, itemStyle: { color: "#65c5cf" } },
    ],
  }), [state?.intraday]);

  const armsOption = useMemo<EChartsOption>(() => ({
    animation: false,
    tooltip: TOOLTIP,
    grid: { left: 44, right: 22, top: 18, bottom: 30 },
    xAxis: { type: "category", boundaryGap: false, data: state?.intraday.map((row) => row.t) || [], axisLabel: { color: AXIS }, axisLine: { lineStyle: { color: GRID } } },
    yAxis: { type: "value", axisLabel: { color: AXIS }, splitLine: { lineStyle: { color: GRID } } },
    series: [{ name: "Arms", type: "line", showSymbol: false, data: state?.intraday.map((row) => round(row.ar, 3)) || [], lineStyle: { color: "#b997ff", width: 2 }, itemStyle: { color: "#b997ff" }, markLine: { silent: true, symbol: "none", lineStyle: { color: "rgba(226,188,66,.55)", type: "dashed" }, data: [{ yAxis: .6, name: "抱团参考线" }] } }],
  }), [state?.intraday]);

  const mclOption = useMemo<EChartsOption>(() => ({
    animation: false,
    tooltip: TOOLTIP,
    grid: { left: 52, right: 22, top: 18, bottom: 34 },
    xAxis: { type: "category", boundaryGap: false, data: state?.mcl?.series.map((row) => row.d.slice(5)) || [], axisLabel: { color: AXIS }, axisLine: { lineStyle: { color: GRID } } },
    yAxis: { type: "value", axisLabel: { color: AXIS }, splitLine: { lineStyle: { color: GRID } } },
    series: [{ name: "麦克连摆", type: "line", showSymbol: false, areaStyle: { color: "rgba(101,197,207,.12)" }, data: state?.mcl?.series.map((row) => round(row.v)) || [], lineStyle: { color: "#65c5cf", width: 2 }, itemStyle: { color: "#65c5cf" } }],
  }), [state?.mcl?.series]);

  const snap = state?.snap;
  const verdict = state?.verdict;

  return (
    <main className="review-workbench-page market-breadth-page">
      <MainSidebar activeKey="market-breadth" note={<>看清指数是真涨真跌，<br />还是少数权重股造成的假象。</>} />
      <section className="review-workbench-main market-breadth-main">
        <header className="market-breadth-topbar">
          <div>
            <span>REAL MARKET STRENGTH</span>
            <h1>市场真实强弱</h1>
          </div>
          <button type="button" onClick={() => void (canRead ? loadState() : loadAccess())} disabled={loading || confirming}>
            <RefreshCcw className={loading ? "spin-icon" : ""} />刷新
          </button>
        </header>

        <FinancialDisclaimer compact />

        {message ? <div className="market-breadth-message" role="status"><AlertTriangle />{message}</div> : null}

        {access?.billing_status === "pending_view" ? (
          <section className="market-breadth-lock" aria-labelledby="market-breadth-lock-title">
            <div className="market-breadth-lock-icon"><LockKeyhole /></div>
            <div>
              <span>每天首次查看</span>
              <h2 id="market-breadth-lock-title">确认后查看今天的市场真实强弱</h2>
              <p>普通用户今天首次查看扣除 {access.billing_cost ?? 2} 次使用机会。今天刷新或重新进入，不会重复扣除。</p>
            </div>
            <button type="button" onClick={confirmAccess} disabled={confirming}>
              {confirming ? <Loader2 className="spin-icon" /> : <CheckCircle2 />}
              确认查看并扣除 {access.billing_cost ?? 2} 次
            </button>
          </section>
        ) : loading && !state ? (
          <section className="market-breadth-loading"><Loader2 className="spin-icon" /><h2>正在读取全市场实时数据</h2><p>系统会汇总沪深京股票后再给出结论。</p></section>
        ) : canRead && state && !snap ? (
          <section className="market-breadth-loading"><Clock3 /><h2>实时数据正在准备</h2><p>{state.error || "首次汇总需要一点时间，请稍后刷新。"}</p></section>
        ) : canRead && snap && verdict ? (
          <>
            {state?.error ? <div className="market-breadth-data-warning"><ShieldAlert />最近一次刷新失败，当前展示最后一份有效数据：{state.error}</div> : null}

            <section className={`market-breadth-verdict is-${verdict.level}`}>
              <div className="market-breadth-verdict-copy">
                <div className="market-breadth-live-row">
                  <span className={state.trading ? "is-live" : ""}>{state.trading ? "盘中实时" : "非交易时段"}</span>
                  <time>{state.updated ? `数据更新：${state.updated}` : "等待更新时间"}</time>
                </div>
                <p>现在市场到底强不强？</p>
                <h2>{verdict.title}</h2>
                <div className="market-breadth-reasoning">
                  <article><span>大资金在做什么</span><b>{verdict.money}</b></article>
                  <ArrowRight />
                  <article><span>行情能否持续</span><b>{verdict.sustain}</b></article>
                  <ArrowRight />
                  <article><span>接下来观察什么</span><b>{verdict.next}</b></article>
                </div>
              </div>
              <HistoricalCard current={verdict.hist} baseline={state.histBase || null} />
            </section>

            <section className="market-breadth-grid market-breadth-summary-grid">
              <article className="market-breadth-panel market-breadth-evidence">
                <header><Activity /><div><span>判断依据</span><h2>为什么得出这个结论</h2></div></header>
                <ul>{verdict.evidence.map((item, index) => <li key={`${item}-${index}`}><span>{index + 1}</span>{item}</li>)}</ul>
              </article>
              <article className="market-breadth-panel">
                <header><BarChart3 /><div><span>全市场温度</span><h2>{snap.up} 家上涨，{snap.down} 家下跌</h2></div></header>
                <div className="market-breadth-countbar"><i style={{ width: `${Math.max(0, Math.min(100, snap.upCountPct))}%` }} /></div>
                <div className="market-breadth-counts"><b className="is-up">上涨 {snap.up}</b><span>平盘 {snap.flat}</span><b className="is-down">下跌 {snap.down}</b></div>
                <p>全市场涨跌幅中位数：<strong className={changeClass(snap.median)}>{signed(snap.median)}%</strong></p>
              </article>
            </section>

            <section className="market-breadth-metrics" aria-label="市场宽度指标">
              <Metric label="上涨家数占比" value={`${format(snap.upCountPct)}%`} help="上涨股票占全部有效股票的比例，越高说明上涨越普遍。" tone={snap.upCountPct >= 50 ? "up" : "down"} />
              <Metric label="上涨成交额占比" value={`${format(snap.upAmtPct)}%`} help="上涨股票贡献的成交额比例，用来观察资金是否集中在上涨方向。" tone={snap.upAmtPct >= 50 ? "up" : "down"} />
              <Metric label="额价差" value={`${signed(snap.spread)}%`} help="上涨成交额占比减去上涨家数占比。数值过高，可能代表资金只集中在少数股票。" />
              <Metric label="Arms 指标" value={format(snap.arms, 3)} help="比较涨跌家数与成交额。明显低于 1 时，资金可能集中在少数上涨股票。" />
              <Metric label="大盘股上涨比例" value={`${format(snap.big.upCountPct)}%`} help="总市值前 300 只股票中上涨股票的比例。" />
              <Metric label="中小盘上涨比例" value={`${format(snap.small.upCountPct)}%`} help="其余股票中上涨股票的比例，用来和大盘股对比。" />
              <Metric label="麦克连摆" value={state.mcl?.value == null ? "数据不足" : signed(state.mcl.value)} help={`根据涨跌家数变化观察市场内部趋势，当前累计 ${state.mcl?.days || 0} 个交易日。`} tone={state.mcl?.value == null ? undefined : state.mcl.value >= 0 ? "up" : "down"} />
            </section>

            <section className="market-breadth-panel market-breadth-index-panel">
              <header><BarChart3 /><div><span>六大指数</span><h2>指数和全市场是否同向</h2></div></header>
              <div className="market-breadth-indexes">
                {state.indexes.map((index) => <article key={index.code}><span>{index.name}</span><b>{format(index.price, 2)}</b><strong className={changeClass(index.pct)}>{signed(index.pct)}%</strong></article>)}
              </div>
            </section>

            <section className="market-breadth-grid market-breadth-chart-grid">
              <article className="market-breadth-panel market-breadth-chart-panel">
                <header><Activity /><div><span>盘中变化</span><h2>上涨范围与资金分布</h2></div></header>
                <MarketBreadthChart option={intradayOption} ariaLabel="上涨家数、上涨成交额和额价差盘中走势" empty={state.intraday.length ? undefined : "今天还没有盘中记录"} />
              </article>
              <article className="market-breadth-panel market-breadth-chart-panel">
                <header><Activity /><div><span>资金集中度</span><h2>Arms 指标盘中走势</h2></div></header>
                <MarketBreadthChart option={armsOption} ariaLabel="Arms 指标盘中走势" empty={state.intraday.length ? undefined : "今天还没有盘中记录"} />
              </article>
            </section>

            <section className="market-breadth-panel market-breadth-chart-panel">
              <header><Activity /><div><span>中期内部趋势</span><h2>麦克连摆最近 60 个交易日</h2></div></header>
              <MarketBreadthChart option={mclOption} ariaLabel="麦克连摆最近六十个交易日走势" empty={state.mcl?.series.length ? undefined : "历史数据不足，暂时无法绘制"} />
            </section>

            <section className="market-breadth-method">
              <h2>怎么看待这份结论</h2>
              <div>
                <p>判断线是本功能根据公开案例自行设定，并不是原视频作者提供的固定规则。</p>
                <p>两年收盘回测中，“真普涨”的历史表现相对更稳定；“假反弹”样本只有 28 次，20 日结果与基准的差距没有达到统计显著。</p>
                <p>历史回测使用收盘数据，页面结论使用盘中实时数据，两者并不完全对应。</p>
                <p>“蓝筹护盘”和“权重拖累”是沿用同一逻辑扩展的推断，原视频没有直接讨论这两种情况。</p>
              </div>
            </section>
          </>
        ) : null}
      </section>
      <MobileFeatureNav activeKey="market-breadth" />
    </main>
  );
}

function Metric({ label, value, help, tone }: { label: string; value: string; help: string; tone?: "up" | "down" }) {
  return <article><span>{label}</span><b className={tone ? `is-${tone}` : ""}>{value}</b><p>{help}</p></article>;
}

function HistoricalCard({ current, baseline }: { current: HistoricalPerformance | null; baseline: HistoricalPerformance | null }) {
  return <aside className="market-breadth-history">
    <span>同类信号的历史表现</span>
    {current?.d20 ? <>
      <b>{current.n} 次样本</b>
      <div><span>之后 20 日下跌比例</span><strong>{format(current.d20.downRate)}%</strong></div>
      <div><span>全部交易日基准</span><strong>{baseline?.d20 ? `${format(baseline.d20.downRate)}%` : "暂无"}</strong></div>
      <small>历史统计只用于理解信号，不代表未来一定重复。</small>
    </> : <p>这个结论暂时没有可比的历史回测。</p>}
  </aside>;
}

function round(value: number, digits = 2) { return Number(Number(value || 0).toFixed(digits)); }
function format(value: number, digits = 1) { return Number.isFinite(value) ? value.toFixed(digits) : "-"; }
function signed(value: number) { return `${value > 0 ? "+" : ""}${format(value)}`; }
function changeClass(value: number) { return value > 0 ? "is-up" : value < 0 ? "is-down" : ""; }
