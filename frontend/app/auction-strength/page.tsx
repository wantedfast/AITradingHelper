"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { BarChart3, CalendarDays, Flame, GitBranch, Loader2, LockKeyhole, RefreshCcw, ShieldAlert, Sparkles, Trophy } from "lucide-react";
import { getAuthToken, storeUser, usageBillingText, type UserProfile } from "@/lib/auth-client";
import { MainSidebar } from "@/components/main-sidebar";
import { FinancialDisclaimer } from "@/components/financial-disclaimer";
import { MobileActionDock } from "@/components/mobile-action-dock";
import { MobileTaskHeader } from "@/components/mobile-task-header";
import { canReadDatedReport, shouldShowDatedReportPayment, type BillingStatus } from "@/lib/dated-report-access";

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
  today_open_change_pct?: string | number;
  label: string;
  role?: string;
  expectation_status?: string;
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
  today_open_change_pct?: string | number;
  label: string;
  role?: string;
  expectation_status?: string;
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
  billing_status?: "no_data" | "pending_view" | "charged" | "free_history";
  billing_cost?: number;
  billing_trade_date?: string;
  user?: UserProfile;
  error?: string;
};

type AuctionAckPayload = {
  ok?: boolean;
  error?: string;
  billing_status?: "charged" | "free_history";
  billing_trade_date?: string;
  user?: UserProfile;
};

type ThemeCandidate = {
  theme?: string;
  confidence?: string;
  priority?: number | string;
  reason?: string;
  theme_level?: string;
  theme_status?: string;
  leader_candidates?: Array<{
    code?: string;
    name?: string;
    role?: string;
    today_open_change?: string | number;
    today_open_change_pct?: string | number;
    reason?: string;
  }>;
  emotion_anchors?: AuctionAnchor[];
};

type ThemeGateResult = {
  type?: string;
  compact_gate?: string;
  admitted_themes?: ThemeCandidate[];
  excluded_themes?: Array<{
    theme?: string;
    reason?: string;
  }>;
  excluded_theme_count?: number;
  strongest_theme?: string;
  summary?: string;
};

type AuctionAnchor = {
  code?: string;
  name?: string;
  theme?: string;
  role?: string;
  label?: string;
  today_open_change?: string | number;
  today_open_change_pct?: string | number;
  reason?: string;
  participation_note?: string;
};

function todayIsoDate() {
  const today = new Date();
  return `${today.getFullYear()}-${`${today.getMonth() + 1}`.padStart(2, "0")}-${`${today.getDate()}`.padStart(2, "0")}`;
}

function isValidIsoDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const candidate = new Date(Date.UTC(year, month - 1, day));
  return candidate.getUTCFullYear() === year
    && candidate.getUTCMonth() === month - 1
    && candidate.getUTCDate() === day;
}

function normalizeChangeNumber(value: string | number | undefined) {
  if (typeof value === "number") return value;
  if (!value) return Number.NaN;
  return Number(String(value).replace("%", "").trim());
}

function changeTone(value: string | number | undefined) {
  const number = normalizeChangeNumber(value);
  if (Number.isNaN(number)) return "flat";
  if (number > 0) return "up";
  if (number < 0) return "down";
  return "flat";
}

function changeText(value: string | number | undefined) {
  if (value === undefined || value === null || value === "") return "--";
  const text = String(value);
  return text.includes("%") ? text : `${text}%`;
}

function stockTitle(item: { name?: string; code?: string }) {
  return [item.name, item.code].filter(Boolean).join(" ") || "--";
}

function globalConclusionText(report: AuctionReport | null) {
  if (!report) return "";
  const conclusion = report.global_conclusion || ({} as AuctionConclusion);
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

export default function AuctionStrengthPage() {
  const router = useRouter();
  const [latest, setLatest] = useState<AuctionReport | null>(null);
  const [reports, setReports] = useState<AuctionReport[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selectedDate, setSelectedDate] = useState(todayIsoDate());
  const [dateQueryReady, setDateQueryReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [billingStatus, setBillingStatus] = useState<BillingStatus>("no_data");
  const [billingCost, setBillingCost] = useState(0);
  const [billingMessage, setBillingMessage] = useState("");

  const selectedReport = useMemo(() => {
    if (!reports.length) return latest;
    return reports.find((report) => report.id === selectedId) || latest || reports[0];
  }, [latest, reports, selectedId]);

  const conclusionText = useMemo(() => globalConclusionText(selectedReport), [selectedReport]);
  const displayAnchors = useMemo(() => {
    const themeAnchors = selectedReport?.theme_gate_result?.admitted_themes?.flatMap((theme) =>
      (theme.emotion_anchors || []).map((anchor) => ({ ...anchor, theme: anchor.theme || theme.theme })),
    ) || [];
    const allAnchors = [
      ...(selectedReport?.global_conclusion?.limit_open_emotion_anchors || []),
      ...themeAnchors,
      ...(selectedReport?.emotion_anchors || []),
    ];
    const seen = new Set<string>();
    return allAnchors.filter((anchor) => {
      const key = [anchor.code, anchor.name, anchor.theme, anchor.reason].filter(Boolean).join("|");
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [selectedReport]);
  const isToday = selectedDate === todayIsoDate();
  const hasAccess = canReadDatedReport(billingStatus);
  const themeGate = selectedReport?.theme_gate_result;
  const admittedThemes = themeGate?.admitted_themes || [];
  const excludedThemes = themeGate?.excluded_themes || [];
  const excludedCount = themeGate?.excluded_theme_count ?? excludedThemes.length;

  function handleDateChange(value: string) {
    const nextDate = isValidIsoDate(value) ? value : todayIsoDate();
    setSelectedDate(nextDate);
    router.replace(`/auction-strength?date=${nextDate}`, { scroll: false });
    setLatest(null);
    setReports([]);
    setSelectedId("");
    setMessage("");
    setBillingMessage("");
    setBillingStatus("no_data");
    setBillingCost(0);
  }

  async function confirmView() {
    const token = getAuthToken();
    if (!token) {
      router.push(`/auth?redirect=/auction-strength`);
      return;
    }
    setMessage("");
    setBillingMessage("");
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/auction-strength/ack`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ trade_date: selectedDate }),
        cache: "no-store",
      });
      const payload = (await response.json()) as AuctionAckPayload;
      if (!response.ok) throw new Error(payload.error || "确认每日 TOP5 访问失败");
      if (payload.user) {
        storeUser(payload.user);
        setBillingMessage(`每日 TOP5 已确认展示。${usageBillingText(payload.user)}`);
      }
      await loadReports(true);
    } catch (error) {
      setBillingMessage(error instanceof Error ? error.message : "确认每日 TOP5 访问失败");
    } finally {
      setLoading(false);
    }
  }

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
      setBillingStatus(payload.billing_status || "no_data");
      setBillingCost(payload.billing_cost || 0);
      if (payload.user) storeUser(payload.user);
      setReports(nextReports);
      setLatest(nextLatest);
      setSelectedId((current) => {
        if (current && nextReports.some((report) => report.id === current)) return current;
        return nextLatest?.id || nextReports[0]?.id || "";
      });
      if (!silent) {
        setMessage(nextLatest ? "已刷新每日 TOP5 数据。" : "当前日期暂无每日 TOP5 数据。");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取每日 TOP5 数据失败");
    } finally {
      setLoading(false);
    }
  }, [router, selectedDate]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const queryDate = params.get("date");
    const nextDate = queryDate && isValidIsoDate(queryDate) ? queryDate : todayIsoDate();
    setSelectedDate(nextDate);
    setDateQueryReady(true);
    if (queryDate && queryDate !== nextDate) {
      router.replace(`/auction-strength?date=${nextDate}`, { scroll: false });
    }
  }, [router]);

  useEffect(() => {
    if (!dateQueryReady) return;
    loadReports();
  }, [dateQueryReady, loadReports]);

  useEffect(() => {
    if (!dateQueryReady || !isToday) return;
    const timer = window.setInterval(() => loadReports(true), 10000);
    return () => window.clearInterval(timer);
  }, [dateQueryReady, isToday, loadReports]);

  return (
    <main className="review-workbench-page auction-page">
      <MainSidebar
        activeKey="auction-strength"
        note="每天 9:25 集合竞价结束后，选出 5 只强势股，并提示需要回避的方向。"
      />

      <section className="review-workbench-main auction-main">
        <header className="auction-topbar">
          <div>
            <span>DAILY TOP 5</span>
            <b>每日 TOP5</b>
          </div>
          <div className="auction-topbar-actions">
            <label className="auction-date-picker">
              <CalendarDays className="h-4 w-4" />
              <input type="date" value={selectedDate} onChange={(event) => handleDateChange(event.target.value)} />
            </label>
            <button type="button" onClick={() => loadReports()} disabled={loading}>
                {loading ? <Loader2 className="spin-icon" /> : <RefreshCcw className="h-4 w-4" />}
                <span>刷新数据</span>
            </button>
          </div>
        </header>

        <FinancialDisclaimer compact={hasAccess} />

        <MobileTaskHeader
          eyebrow={<><Flame className="h-4 w-4" />{selectedDate || "等待数据"}</>}
          title="每日 TOP5"
          description={hasAccess ? selectedReport?.summary.one_sentence || "查看当天最值得关注的 5 只强势股。" : billingStatus === "pending_view" ? `今天的数据需确认并扣除 ${billingCost} 次使用机会。` : "所选日期暂无数据，可稍后刷新。"}
          status={hasAccess ? "已可直接查看" : billingStatus === "pending_view" ? "待确认查看" : "暂无数据"}
        />

        <section className="auction-hero">
          <div>
            <p className="auction-kicker">
              <Flame className="h-4 w-4" />
              {selectedDate || "等待数据"} · {hasAccess ? selectedReport?.analysis_time || "09:25 集合竞价后" : billingStatus === "pending_view" ? "确认后查看" : "等待数据"}
            </p>
            <h1>{hasAccess ? selectedReport?.summary.one_sentence || "当前日期暂无每日 TOP5 数据。" : billingStatus === "pending_view" ? `查看今天的每日 TOP5 将扣除 ${billingCost} 次使用机会` : "当前日期暂无每日 TOP5 数据"}</h1>
            <span className="auction-buy-note">建议选择观察开盘方向，优先选择开盘向上，买限买入。</span>
            <p>{hasAccess ? selectedReport?.global_conclusion.one_sentence_for_930 || "当日数据进入后，页面会自动刷新并展示 9:30 前执行重点。" : billingStatus === "pending_view" ? "同一交易日只扣一次；今天已经付费后再切回来会直接显示。" : "没有数据不会扣除使用次数，可以稍后刷新或选择其他日期。"}</p>
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
              <b>{isToday ? "当日自动刷新" : "历史手动刷新"}</b>
            </article>
          </div>
        </section>

        {shouldShowDatedReportPayment(billingStatus, Boolean(selectedReport)) ? (
          <section className="auction-panel auction-confirm-panel">
            <PanelHead icon={<LockKeyhole className="h-5 w-5" />} title="确认查看每日 TOP5" text={`今天的数据尚未付费，确认后扣除 ${billingCost} 次使用机会。`} />
            <MobileActionDock className="auction-confirm-actions">
              <button type="button" onClick={confirmView} disabled={loading}>
                确认查看并扣除 {billingCost} 次
              </button>
              <span>所选日期无数据或读取失败时不会扣除使用次数。</span>
            </MobileActionDock>
          </section>
        ) : hasAccess ? (
          <>
            {billingMessage ? <p className="auction-message">{billingMessage}</p> : null}
            <section className="auction-grid auction-grid--primary">
              <section className="auction-panel auction-conclusion-panel">
                <PanelHead icon={<BarChart3 className="h-5 w-5" />} title="全局结论" text="把 9:25 最强、最超预期、容量确认和负反馈压缩成 9:30 观察重点。" />
                <div className="auction-conclusion-stack">
                  <MetricTile label="最强个股" value={selectedReport?.global_conclusion.strongest_stock_at_925 || "--"} tone="hot" />
                  <MetricTile label="最强题材" value={selectedReport?.global_conclusion.strongest_theme_cluster || "--"} />
                  <MetricTile label="最超预期" value={selectedReport?.global_conclusion.most_over_expected_stock || "--"} tone="hot" />
                  <MetricTile label="容量确认" value={selectedReport?.global_conclusion.best_capacity_confirmation || "--"} />
                  <MetricTile label="最大负反馈" value={selectedReport?.global_conclusion.biggest_negative_feedback || "--"} />
                </div>
                <p className="auction-conclusion-text">{conclusionText || "所选日期暂无全局结论。"}</p>
              </section>

              <section className="auction-panel auction-strong-panel">
                <PanelHead icon={<Trophy className="h-5 w-5" />} title="Top5 强势标的" text="最终进入 9:30 前优先观察的主板个股。" />
                <div className="auction-stock-list">
                  {selectedReport?.top5_strong_stocks.length ? selectedReport.top5_strong_stocks.map((stock) => (
                    <article className="auction-stock-card" key={`${stock.rank}-${stock.code}`}>
                      <div className="auction-stock-rank">{stock.rank}</div>
                      <div>
                        <header>
                          <h2>{stock.name} <small>{stock.code}</small></h2>
                          <strong data-tone={changeTone(stock.today_open_change ?? stock.today_open_change_pct)}>{changeText(stock.today_open_change ?? stock.today_open_change_pct)}</strong>
                        </header>
                        <div className="auction-chip-row">
                          <span>{stock.theme}</span>
                          <span>{stock.label || stock.role || "--"}</span>
                          <span>{stock.expectation_status || stock.theme_level}</span>
                        </div>
                        <p>{stock.reason}</p>
                        <em>{stock.observe_after_930}</em>
                      </div>
                    </article>
                  )) : <EmptyState text="所选日期还没有强势标的数据。" />}
                </div>
              </section>
            </section>

            <section className="auction-panel auction-anchor-panel">
              <PanelHead icon={<Sparkles className="h-5 w-5" />} title="情绪锚点" text="涨停开、一字、接近涨停或强度锚，只给用户参考，不等于 Top5 可观察标的。" />
              <div className="auction-anchor-grid">
                {displayAnchors.length ? displayAnchors.map((anchor, index) => (
                  <article className="auction-anchor-card" key={`${anchor.code || index}-${anchor.name || "anchor"}`}>
                    <header>
                      <b>{stockTitle(anchor)}</b>
                      <strong data-tone={changeTone(anchor.today_open_change ?? anchor.today_open_change_pct)}>{changeText(anchor.today_open_change ?? anchor.today_open_change_pct)}</strong>
                    </header>
                    <div className="auction-chip-row">
                      <span>{anchor.theme || "--"}</span>
                      {anchor.role || anchor.label ? <span>{anchor.role || anchor.label}</span> : null}
                    </div>
                    <p>{anchor.reason || "--"}</p>
                    {anchor.participation_note ? <em>{anchor.participation_note}</em> : null}
                  </article>
                )) : <EmptyState text="所选日期没有情绪锚点字段，旧数据会保持空态。" />}
              </div>
            </section>

            <section className="auction-grid">
              <section className="auction-panel auction-avoid-panel">
                <PanelHead icon={<ShieldAlert className="h-5 w-5" />} title="Top5 回避标的" text="竞价负反馈、掉队前排和高开低质方向。" />
                <div className="auction-stock-list">
                  {selectedReport?.top5_avoid_stocks.length ? selectedReport.top5_avoid_stocks.map((stock) => (
                    <article className="auction-stock-card auction-stock-card--avoid" key={`${stock.rank}-${stock.code}`}>
                      <div className="auction-stock-rank">{stock.rank}</div>
                      <div>
                        <header>
                          <h2>{stock.name} <small>{stock.code}</small></h2>
                          <strong data-tone={changeTone(stock.today_open_change ?? stock.today_open_change_pct)}>{changeText(stock.today_open_change ?? stock.today_open_change_pct)}</strong>
                        </header>
                        <div className="auction-chip-row">
                          <span>{stock.theme}</span>
                          <span>{stock.label || stock.role || "--"}</span>
                          <span>{stock.expectation_status || stock.theme_level}</span>
                        </div>
                        <p>{stock.reason}</p>
                        <em>{stock.risk_after_930}</em>
                      </div>
                    </article>
                  )) : <EmptyState text="所选日期还没有回避标的数据。" />}
                </div>
              </section>

              <section className="auction-panel auction-v2-panel">
                <PanelHead icon={<GitBranch className="h-5 w-5" />} title="题材门禁" text="Theme Gate 决定哪些题材放行，哪些题材排除。" />
                <div className="auction-v2-summary">
                  <MetricTile label="最强题材" value={themeGate?.strongest_theme || selectedReport?.global_conclusion.strongest_theme_cluster || "--"} />
                  <MetricTile label="放行题材" value={String(admittedThemes.length)} />
                  <MetricTile label="排除数量" value={String(excludedCount)} />
                </div>
                <div className="auction-theme-list">
                  {admittedThemes.length ? admittedThemes.map((theme, index) => (
                    <article key={`${theme.theme || "admit"}-${index}`}>
                      <b>{theme.theme || "--"}</b>
                      <span>{theme.confidence || theme.theme_status || "放行"}</span>
                      {theme.reason ? <p>{theme.reason}</p> : null}
                      {theme.leader_candidates?.length ? (
                        <div className="auction-mini-stock-list">
                          {theme.leader_candidates.map((candidate, candidateIndex) => (
                            <span key={`${candidate.code || candidate.name || candidateIndex}`}>
                              {candidate.code || "--"} {candidate.name || "--"} · {candidate.role || "--"} · {changeText(candidate.today_open_change ?? candidate.today_open_change_pct)}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </article>
                  )) : null}
                  {excludedThemes.length ? (
                    <div className="auction-note-list">
                      {excludedThemes.map((theme, index) => (
                        <span key={`${theme.theme || "exclude"}-${index}`}>
                          {theme.theme || "未命名题材"}：{theme.reason || "--"}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  {admittedThemes.length || excludedThemes.length ? null : <EmptyState text="所选日期没有题材门禁字段，旧数据会保持空态。" />}
                </div>
              </section>
            </section>

            <section className="auction-grid auction-grid--history">
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
        ) : !loading && billingStatus === "no_data" ? isToday ? (
          <section className="auction-panel auction-confirm-panel auction-waiting-panel">
            <PanelHead icon={<LockKeyhole className="h-5 w-5" />} title="等待今日数据" text="数据到达后，查看按钮会自动变为可用状态。" />
            <MobileActionDock className="auction-confirm-actions">
              <button type="button" disabled>等待今日数据</button>
              <span>页面每 10 秒自动检查一次；无数据时不会扣除使用次数。</span>
            </MobileActionDock>
          </section>
        ) : <section className="auction-panel auction-empty"><b>暂无数据</b><span>所选日期暂无每日 TOP5，请选择其他日期。</span></section> : null}
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

function MetricTile({ label, value, tone }: { label: string; value: string; tone?: "hot" }) {
  return (
    <article className="auction-metric-tile" data-tone={tone}>
      <span>{label}</span>
      <b>{value}</b>
    </article>
  );
}
