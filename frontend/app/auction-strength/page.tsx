"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { BarChart3, CalendarDays, Database, Flame, Loader2, LockKeyhole, RefreshCcw, ShieldAlert, Sparkles, Timer, Trophy } from "lucide-react";
import { getAuthToken, storeUser, type UserProfile } from "@/lib/auth-client";
import { MainSidebar } from "@/components/main-sidebar";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8600" : "");

type AuctionSummary = {
  one_sentence: string;
  selection_logic: string;
  data_limit: string;
};

type AuctionConclusion = {
  strongest_stock_at_925: string;
  strongest_theme_cluster: string;
  most_over_expected_stock: string;
  best_capacity_confirmation: string;
  biggest_negative_feedback: string;
  one_sentence_for_930: string;
  limit_open_emotion_anchors?: AuctionAnchor[];
};

type StrongStock = {
  rank: number;
  code: string;
  name: string;
  theme: string;
  today_open_change: string;
  label: string;
  theme_level: string;
  reason: string;
  observe_after_930: string;
};

type AvoidStock = {
  rank: number;
  code: string;
  name: string;
  theme: string;
  today_open_change: string;
  label: string;
  theme_level: string;
  reason: string;
  risk_after_930: string;
};

type AuctionReport = {
  id: string;
  request_id: string;
  received_at: string;
  source_ip: string;
  trade_date: string;
  analysis_time: string;
  summary: AuctionSummary;
  top5_strong_stocks: StrongStock[];
  top5_avoid_stocks: AvoidStock[];
  global_conclusion: AuctionConclusion;
  theme_gate_result?: ThemeGateResult;
  emotion_anchors?: AuctionAnchor[];
  timings?: Record<string, number>;
  quote_provider?: string;
  source_csv?: string;
  data_limit?: string[];
  warnings?: string[];
};

type AuctionPayload = {
  latest?: AuctionReport | null;
  reports?: AuctionReport[];
  count?: number;
  total?: number;
  billing_status?: "no_data" | "pending_view" | "charged";
  billing_trade_date?: string;
  user?: UserProfile;
  error?: string;
};

type AuctionAckPayload = {
  ok?: boolean;
  error?: string;
  billing_status?: "charged";
  billing_trade_date?: string;
  user?: UserProfile;
};

type ThemeCandidate = {
  theme?: string;
  confidence?: string;
  reason?: string;
  leader_candidates?: Array<{
    code?: string;
    name?: string;
    role?: string;
    today_open_change?: string | number;
    reason?: string;
  }>;
};

type ThemeGateResult = {
  type?: string;
  compact_gate?: string;
  admitted_themes?: ThemeCandidate[];
  excluded_themes?: Array<{
    theme?: string;
    reason?: string;
  }>;
  strongest_theme?: string;
  summary?: string;
};

type AuctionAnchor = {
  code?: string;
  name?: string;
  theme?: string;
  today_open_change?: string | number;
  today_open_change_pct?: string | number;
  reason?: string;
  participation_note?: string;
};

function todayIsoDate() {
  const today = new Date();
  return `${today.getFullYear()}-${`${today.getMonth() + 1}`.padStart(2, "0")}-${`${today.getDate()}`.padStart(2, "0")}`;
}

function changeTone(value: string) {
  const number = Number(value);
  if (Number.isNaN(number)) return "flat";
  if (number > 0) return "up";
  if (number < 0) return "down";
  return "flat";
}

function globalConclusionText(report: AuctionReport | null) {
  if (!report) return "";
  const conclusion = report.global_conclusion;
  const parts = [
    conclusion.strongest_stock_at_925 ? `9:25 最强个股是 ${conclusion.strongest_stock_at_925}` : "",
    conclusion.strongest_theme_cluster ? `最强题材集群是 ${conclusion.strongest_theme_cluster}` : "",
    conclusion.most_over_expected_stock ? `最超预期标的是 ${conclusion.most_over_expected_stock}` : "",
    conclusion.best_capacity_confirmation ? `容量确认重点为 ${conclusion.best_capacity_confirmation}` : "",
    conclusion.biggest_negative_feedback ? `最大负反馈来自 ${conclusion.biggest_negative_feedback}` : "",
  ].filter(Boolean);
  const lead = parts.length ? `${parts.join("，")}。` : "";
  return `${lead}${conclusion.one_sentence_for_930 || ""}`.trim();
}

function formatTiming(seconds: number | undefined) {
  if (typeof seconds !== "number" || Number.isNaN(seconds)) return "--";
  if (seconds >= 60) return `${(seconds / 60).toFixed(1)} 分钟`;
  return `${seconds.toFixed(seconds >= 10 ? 1 : 2)} 秒`;
}

function anchorLabel(anchor: AuctionAnchor) {
  return [anchor.name, anchor.code].filter(Boolean).join(" ") || "--";
}

export default function AuctionStrengthPage() {
  const router = useRouter();
  const [latest, setLatest] = useState<AuctionReport | null>(null);
  const [reports, setReports] = useState<AuctionReport[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selectedDate, setSelectedDate] = useState(todayIsoDate());
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [billingMessage, setBillingMessage] = useState("");
  const ackedDatesRef = useRef<Set<string>>(new Set());

  const selectedReport = useMemo(() => {
    if (!reports.length) return latest;
    return reports.find((report) => report.id === selectedId) || latest || reports[0];
  }, [latest, reports, selectedId]);

  const conclusionText = useMemo(() => globalConclusionText(selectedReport), [selectedReport]);
  const isToday = selectedDate === todayIsoDate();

  function handleDateChange(value: string) {
    setSelectedDate(value);
    setConfirmed(false);
    setLatest(null);
    setReports([]);
    setSelectedId("");
    setMessage("");
    setBillingMessage("");
  }

  function confirmView() {
    const token = getAuthToken();
    if (!token) {
      router.push(`/auth?redirect=/auction-strength`);
      return;
    }
    setConfirmed(true);
    setMessage("");
    setBillingMessage("");
  }

  const acknowledgeVisibleReport = useCallback(async (tradeDate: string) => {
    const token = getAuthToken();
    const key = tradeDate || selectedDate;
    if (!token || !key || ackedDatesRef.current.has(key)) return;
    ackedDatesRef.current.add(key);
    try {
      const response = await fetch(`${API_BASE}/api/auction-strength/ack`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ trade_date: key }),
        cache: "no-store",
      });
      const payload = (await response.json()) as AuctionAckPayload;
      if (!response.ok) throw new Error(payload.error || "竞价分析已展示，但扣除使用次数失败");
      if (payload.user) {
        storeUser(payload.user);
        const credits = typeof payload.user.credits === "number" ? `剩余 ${payload.user.credits} 次。` : "";
        setBillingMessage(`竞价分析已展示，已按交易日确认扣除 1 次使用机会。${credits}`);
      }
    } catch (error) {
      ackedDatesRef.current.delete(key);
      setBillingMessage(error instanceof Error ? error.message : "竞价分析已展示，但扣除使用次数失败");
    }
  }, [selectedDate]);

  const loadReports = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const token = getAuthToken();
      if (!token) {
        router.push(`/auth?redirect=/auction-strength`);
        return;
      }
      const params = new URLSearchParams({ limit: "20" });
      if (selectedDate) params.set("date", selectedDate);
      const response = await fetch(`${API_BASE}/api/auction-strength?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      const text = await response.text();
      const payload = text ? (JSON.parse(text) as AuctionPayload) : {};
      if (!response.ok) throw new Error(payload.error || `读取失败：HTTP ${response.status}`);
      const nextReports = payload.reports || [];
      const nextLatest = payload.latest || nextReports[0] || null;
      setReports(nextReports);
      setLatest(nextLatest);
      setSelectedId((current) => {
        if (current && nextReports.some((report) => report.id === current)) return current;
        return nextLatest?.id || nextReports[0]?.id || "";
      });
      if (!silent) {
        setMessage(nextLatest ? "已刷新竞价强者数据。" : "当前日期暂无竞价强者数据。");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取竞价强者数据失败");
    } finally {
      setLoading(false);
    }
  }, [router, selectedDate]);

  useEffect(() => {
    if (!confirmed) {
      setLoading(false);
      return;
    }
    loadReports();
  }, [confirmed, loadReports]);

  useEffect(() => {
    if (!confirmed || !isToday) return;
    const timer = window.setInterval(() => loadReports(true), 10000);
    return () => window.clearInterval(timer);
  }, [confirmed, isToday, loadReports]);

  useEffect(() => {
    if (!confirmed || !selectedReport) return;
    void acknowledgeVisibleReport(selectedReport.trade_date || selectedDate);
  }, [acknowledgeVisibleReport, confirmed, selectedDate, selectedReport]);

  return (
    <main className="review-workbench-page auction-page">
      <MainSidebar
        activeKey="auction-strength"
        note="09:25 竞价强弱映射，确认查看后展示强势标的、回避标的和全局结论。"
      />

      <section className="review-workbench-main auction-main">
        <header className="auction-topbar">
          <div>
            <span>AUCTION STRENGTH</span>
            <b>竞价强者数据看板</b>
          </div>
          <div className="auction-topbar-actions">
            <label className="auction-date-picker">
              <CalendarDays className="h-4 w-4" />
              <input type="date" value={selectedDate} onChange={(event) => handleDateChange(event.target.value)} />
            </label>
            {confirmed ? (
              <button type="button" onClick={() => loadReports()} disabled={loading}>
                {loading ? <Loader2 className="spin-icon" /> : <RefreshCcw className="h-4 w-4" />}
                <span>刷新数据</span>
              </button>
            ) : null}
          </div>
        </header>

        <section className="auction-hero">
          <div>
            <p className="auction-kicker">
              <Flame className="h-4 w-4" />
              {selectedReport?.trade_date || selectedDate || "等待数据"} · {confirmed ? selectedReport?.analysis_time || "09:25 集合竞价后" : "确认后查看"}
            </p>
            <h1>{confirmed ? selectedReport?.summary.one_sentence || "当前日期暂无竞价强者数据。" : "查看竞价分析会扣除 1 次使用机会。"}</h1>
            <span className="auction-buy-note">建议以买限价格买入</span>
            <p>{confirmed ? selectedReport?.global_conclusion.one_sentence_for_930 || "当日数据进入后，页面会自动刷新并展示 9:30 前执行重点。" : "确认查看后才会加载 Top5 强势标的、回避标的和全局结论；没有数据或读取失败不会扣次数。"}</p>
          </div>
          <div className="auction-status-strip">
            <article>
              <span>所选日期</span>
              <b>{selectedDate || "--"}</b>
            </article>
            <article>
              <span>记录数</span>
              <b>{reports.length}</b>
            </article>
            <article>
              <span>刷新状态</span>
              <b>{confirmed ? isToday ? "当日自动刷新" : "历史手动刷新" : "待确认查看"}</b>
            </article>
          </div>
        </section>

        {!confirmed ? (
          <section className="auction-panel auction-confirm-panel">
            <PanelHead icon={<LockKeyhole className="h-5 w-5" />} title="确认查看竞价分析" text="查看所选交易日的竞价分析会扣除 1 次使用机会；同一交易日重复刷新或切换记录不会重复扣。" />
            <div className="auction-confirm-actions">
              <button type="button" onClick={confirmView}>
                确认查看并扣次
              </button>
              <span>如果所选日期暂无数据，或数据读取失败，不会扣次数。</span>
            </div>
          </section>
        ) : (
          <>
            {billingMessage ? <p className="auction-message">{billingMessage}</p> : null}
            <section className="auction-grid">
              <section className="auction-panel auction-strong-panel">
                <PanelHead icon={<Trophy className="h-5 w-5" />} title="Top5 强势标的" text="按后端 JSON 的 rank 顺序展示竞价强者。" />
                <div className="auction-stock-list">
                  {selectedReport?.top5_strong_stocks.length ? selectedReport.top5_strong_stocks.map((stock) => (
                    <article className="auction-stock-card" key={`${stock.rank}-${stock.code}`}>
                      <div className="auction-stock-rank">{stock.rank}</div>
                      <div>
                        <header>
                          <h2>{stock.name} <small>{stock.code}</small></h2>
                          <strong data-tone={changeTone(stock.today_open_change)}>{stock.today_open_change}%</strong>
                        </header>
                        <div className="auction-chip-row">
                          <span>{stock.theme}</span>
                          <span>{stock.label}</span>
                          <span>{stock.theme_level}</span>
                        </div>
                        <p>{stock.reason}</p>
                        <em>{stock.observe_after_930}</em>
                      </div>
                    </article>
                  )) : <EmptyState text="所选日期还没有强势标的数据。" />}
                </div>
              </section>

              <section className="auction-panel auction-avoid-panel">
                <PanelHead icon={<ShieldAlert className="h-5 w-5" />} title="Top5 回避标的" text="展示竞价负反馈、掉队前排和需要回避的方向。" />
                <div className="auction-stock-list">
                  {selectedReport?.top5_avoid_stocks.length ? selectedReport.top5_avoid_stocks.map((stock) => (
                    <article className="auction-stock-card auction-stock-card--avoid" key={`${stock.rank}-${stock.code}`}>
                      <div className="auction-stock-rank">{stock.rank}</div>
                      <div>
                        <header>
                          <h2>{stock.name} <small>{stock.code}</small></h2>
                          <strong data-tone={changeTone(stock.today_open_change)}>{stock.today_open_change}%</strong>
                        </header>
                        <div className="auction-chip-row">
                          <span>{stock.theme}</span>
                          <span>{stock.label}</span>
                          <span>{stock.theme_level}</span>
                        </div>
                        <p>{stock.reason}</p>
                        <em>{stock.risk_after_930}</em>
                      </div>
                    </article>
                  )) : <EmptyState text="所选日期还没有回避标的数据。" />}
                </div>
              </section>
            </section>

            <section className="auction-grid auction-grid--v2">
              <section className="auction-panel auction-conclusion-panel">
                <PanelHead icon={<BarChart3 className="h-5 w-5" />} title="全局结论" text="把 9:25 最强、最超预期、容量确认和负反馈压缩成 9:30 观察重点。" />
                <div className="auction-metric-grid">
                  <MetricTile label="最强个股" value={selectedReport?.global_conclusion.strongest_stock_at_925 || "--"} />
                  <MetricTile label="最强题材" value={selectedReport?.global_conclusion.strongest_theme_cluster || "--"} />
                  <MetricTile label="最超预期" value={selectedReport?.global_conclusion.most_over_expected_stock || "--"} />
                  <MetricTile label="容量确认" value={selectedReport?.global_conclusion.best_capacity_confirmation || "--"} />
                  <MetricTile label="最大负反馈" value={selectedReport?.global_conclusion.biggest_negative_feedback || "--"} />
                </div>
                <p className="auction-conclusion-text">{conclusionText || "所选日期暂无全局结论。"}</p>
              </section>

              <section className="auction-panel">
                <PanelHead icon={<Sparkles className="h-5 w-5" />} title="情绪锚点" text="涨停开、一字、接近涨停或强度锚，只作为盘前参考。" />
                <div className="auction-anchor-list">
                  {selectedReport?.emotion_anchors?.length ? selectedReport.emotion_anchors.slice(0, 8).map((anchor, index) => (
                    <article className="auction-v2-item" key={`${anchor.code || index}-${anchor.name || "anchor"}`}>
                      <header>
                        <b>{anchorLabel(anchor)}</b>
                        <strong data-tone={changeTone(String(anchor.today_open_change ?? anchor.today_open_change_pct ?? ""))}>{anchor.today_open_change ?? anchor.today_open_change_pct ?? "--"}%</strong>
                      </header>
                      <span>{anchor.theme || "--"}</span>
                      <p>{anchor.reason || anchor.participation_note || "--"}</p>
                    </article>
                  )) : <EmptyState text="所选日期没有情绪锚点字段，旧数据会保持空态。" />}
                </div>
              </section>
            </section>

            <section className="auction-grid auction-grid--v2">
              <section className="auction-panel">
                <PanelHead icon={<ShieldAlert className="h-5 w-5" />} title="题材门禁" text="Theme Gate 决定哪些题材放行，哪些题材排除。" />
                <div className="auction-theme-gate">
                  <MetricTile label="门禁状态" value={selectedReport?.theme_gate_result?.compact_gate || selectedReport?.theme_gate_result?.type || "--"} />
                  <MetricTile label="最强题材" value={selectedReport?.theme_gate_result?.strongest_theme || selectedReport?.global_conclusion.strongest_theme_cluster || "--"} />
                </div>
                <div className="auction-theme-list">
                  {(selectedReport?.theme_gate_result?.admitted_themes || []).slice(0, 5).map((theme, index) => (
                    <article className="auction-v2-item" key={`${theme.theme || "admit"}-${index}`}>
                      <header>
                        <b>{theme.theme || "--"}</b>
                        <span>{theme.confidence || "放行"}</span>
                      </header>
                      <p>{theme.reason || theme.leader_candidates?.map((item) => [item.name, item.code].filter(Boolean).join(" ")).filter(Boolean).join(" / ") || "--"}</p>
                    </article>
                  ))}
                  {(selectedReport?.theme_gate_result?.excluded_themes || []).slice(0, 5).map((theme, index) => (
                    <article className="auction-v2-item auction-v2-item--avoid" key={`${theme.theme || "exclude"}-${index}`}>
                      <header>
                        <b>{theme.theme || "--"}</b>
                        <span>排除</span>
                      </header>
                      <p>{theme.reason || "--"}</p>
                    </article>
                  ))}
                  {selectedReport?.theme_gate_result?.admitted_themes?.length || selectedReport?.theme_gate_result?.excluded_themes?.length ? null : <EmptyState text="所选日期没有题材门禁字段，旧数据会保持空态。" />}
                </div>
              </section>

              <section className="auction-panel">
                <PanelHead icon={<Timer className="h-5 w-5" />} title="链路耗时" text="展示 webhook 中传来的 V2 阶段耗时。" />
                <div className="auction-metric-grid">
                  <MetricTile label="总耗时" value={formatTiming(selectedReport?.timings?.total_elapsed_seconds)} />
                  <MetricTile label="9:25后" value={formatTiming(selectedReport?.timings?.post_auction_elapsed_seconds)} />
                  <MetricTile label="行情获取" value={formatTiming(selectedReport?.timings?.quote_fetch_elapsed_seconds)} />
                  <MetricTile label="题材判断" value={formatTiming(selectedReport?.timings?.theme_judge_elapsed_seconds)} />
                  <MetricTile label="个股判断" value={formatTiming(selectedReport?.timings?.stock_judge_elapsed_seconds)} />
                </div>
                <div className="auction-data-box">
                  <Database className="h-4 w-4" />
                  <div>
                    <b>{selectedReport?.quote_provider || "行情源 --"}</b>
                    <span>{selectedReport?.source_csv || "CSV --"}</span>
                  </div>
                </div>
                {selectedReport?.data_limit?.length ? (
                  <ul className="auction-note-list">
                    {selectedReport.data_limit.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
                  </ul>
                ) : null}
                {selectedReport?.warnings?.length ? (
                  <ul className="auction-note-list auction-note-list--warning">
                    {selectedReport.warnings.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
                  </ul>
                ) : null}
              </section>
            </section>

            <section className="auction-grid auction-grid--lower auction-grid--single">
              <section className="auction-panel auction-day-list-panel">
                <PanelHead icon={<CalendarDays className="h-5 w-5" />} title="当日记录" text="同一日期有多次推送时，可切换查看。" />
                <div className="auction-history-list">
                  {reports.length ? reports.map((report) => (
                    <button className={selectedReport?.id === report.id ? "active" : ""} type="button" key={report.id} onClick={() => setSelectedId(report.id)}>
                      <b>{report.trade_date || report.received_at}</b>
                      <span>{report.received_at || report.analysis_time} · {report.analysis_time || report.summary.one_sentence || "--"}</span>
                    </button>
                  )) : <EmptyState text="所选日期还没有历史记录。" />}
                </div>
                {message ? <p className="auction-message">{message}</p> : null}
              </section>
            </section>
          </>
        )}
      </section>
    </main>
  );
}

function PanelHead({ icon, title, text }: { icon: ReactNode; title: string; text?: string }) {
  return (
    <div className="auction-panel-head">
      {icon}
      <div>
        <h2>{title}</h2>
        {text ? <p>{text}</p> : null}
      </div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="auction-empty">
      <b>暂无数据</b>
      <span>{text}</span>
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <article className="auction-metric-tile">
      <span>{label}</span>
      <b>{value}</b>
    </article>
  );
}
