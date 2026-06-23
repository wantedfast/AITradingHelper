"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ArrowLeft, BarChart3, CalendarDays, Flame, GitBranch, Loader2, RefreshCcw, ShieldAlert, Sparkles, Trophy } from "lucide-react";
import { FeatureSidebar } from "@/components/feature-sidebar";

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
  limit_open_emotion_anchors?: AnchorItem[];
  one_sentence_for_930: string;
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

type ThemeGateTheme = {
  theme?: string;
  priority?: number | string;
  confidence?: string;
  theme_level?: string;
  theme_status?: string;
  leader_candidates?: AnchorItem[];
  emotion_anchors?: AnchorItem[];
};

type ThemeGateExcluded = {
  theme?: string;
  reason?: string;
};

type ThemeGateResult = {
  strongest_theme?: string;
  excluded_theme_count?: number;
  admitted_themes?: ThemeGateTheme[];
  excluded_themes?: ThemeGateExcluded[];
};

type AnchorItem = {
  code?: string;
  name?: string;
  theme?: string;
  role?: string;
  label?: string;
  today_open_change?: number | string;
  reason?: string;
  participation_note?: string;
};

type AuctionTimings = {
  prearm_elapsed_seconds?: number;
  quote_fetch_elapsed_seconds?: number;
  theme_summary_elapsed_seconds?: number;
  theme_judge_elapsed_seconds?: number;
  stock_pool_elapsed_seconds?: number;
  stock_judge_elapsed_seconds?: number;
  push_elapsed_seconds?: number;
  total_elapsed_seconds?: number;
  post_auction_elapsed_seconds?: number;
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
  emotion_anchors?: unknown[];
  timings?: AuctionTimings;
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

function compactUnknown(value: unknown) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    const name = record.name || record.stock || record.code || record.theme || record.reason || record.label;
    if (name) return String(name);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function stockTitle(item: AnchorItem) {
  return [item.code, item.name].filter(Boolean).join(" ") || item.theme || item.label || "--";
}

function changeText(value?: number | string) {
  if (value === undefined || value === null || value === "") return "--";
  return `${value}%`;
}

export default function AuctionStrengthV2Page() {
  const [latest, setLatest] = useState<AuctionReport | null>(null);
  const [reports, setReports] = useState<AuctionReport[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selectedDate, setSelectedDate] = useState(todayIsoDate());
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  const selectedReport = useMemo(() => {
    if (!reports.length) return latest;
    return reports.find((report) => report.id === selectedId) || latest || reports[0];
  }, [latest, reports, selectedId]);

  const conclusionText = useMemo(() => globalConclusionText(selectedReport), [selectedReport]);
  const isToday = selectedDate === todayIsoDate();
  const themeGate = selectedReport?.theme_gate_result;
  const admittedThemes = themeGate?.admitted_themes || [];
  const excludedThemes = themeGate?.excluded_themes || [];
  const limitOpenAnchors = selectedReport?.global_conclusion.limit_open_emotion_anchors || [];
  const themeEmotionAnchors = admittedThemes.flatMap((theme) =>
    (theme.emotion_anchors || []).map((anchor) => ({ ...anchor, theme: anchor.theme || theme.theme })),
  );
  const emotionAnchors = (selectedReport?.emotion_anchors || []) as AnchorItem[];
  const displayAnchors = [...limitOpenAnchors, ...themeEmotionAnchors, ...emotionAnchors].filter((anchor, index, rows) => {
    const key = `${anchor.code || ""}-${anchor.name || ""}-${anchor.theme || ""}-${anchor.reason || ""}`;
    return rows.findIndex((row) => `${row.code || ""}-${row.name || ""}-${row.theme || ""}-${row.reason || ""}` === key) === index;
  });

  const loadReports = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "20" });
      if (selectedDate) params.set("date", selectedDate);
      const response = await fetch(`${API_BASE}/api/auction-strength-v2?${params.toString()}`, { cache: "no-store" });
      const text = await response.text();
      const payload = text ? (JSON.parse(text) as AuctionPayload & { error?: string }) : {};
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
        setMessage(nextLatest ? "已刷新竞价强者V2数据。" : "当前日期暂无竞价强者V2数据。");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取竞价强者V2数据失败");
    } finally {
      setLoading(false);
    }
  }, [selectedDate]);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  useEffect(() => {
    if (!isToday) return;
    const timer = window.setInterval(() => loadReports(true), 10000);
    return () => window.clearInterval(timer);
  }, [isToday, loadReports]);

  return (
    <main className="review-workbench-page auction-page">
      <FeatureSidebar active="auction-strength-v2" note="接收 V2 09:25 webhook，展示题材门禁、情绪锚点、主板池过滤后的 Top5 和 9:30 执行重点。" />

      <section className="auction-main">
        <header className="auction-topbar">
          <div className="auction-module-title">
            <span className="auction-title-icon"><Trophy className="h-5 w-5" /></span>
            <div>
              <b>竞价强者V2</b>
              <small>Theme Gate + 主板池</small>
            </div>
          </div>
          <div className="auction-topbar-actions">
            <Link className="auction-home-link" href="/">
              <ArrowLeft className="h-4 w-4" />
              <span>
                <b>返回首页</b>
                <small>回到盈航主界面</small>
              </span>
            </Link>
            <label className="auction-date-picker">
              <CalendarDays className="h-4 w-4" />
              <input type="date" value={selectedDate} onChange={(event) => setSelectedDate(event.target.value)} />
            </label>
            <button className="auction-refresh-button" type="button" onClick={() => loadReports()} disabled={loading}>
              {loading ? <Loader2 className="spin-icon" /> : <RefreshCcw className="h-4 w-4" />}
              <span>
                <b>刷新数据</b>
                <small>{isToday ? "当日自动刷新中" : "读取所选日期"}</small>
              </span>
            </button>
          </div>
        </header>

        <section className="auction-hero">
          <div>
            <p className="auction-kicker">
              <Flame className="h-4 w-4" />
              {selectedReport?.trade_date || selectedDate || "等待数据"} · {selectedReport?.analysis_time || "09:25 集合竞价后"}
            </p>
            <h1>{selectedReport?.summary.one_sentence || "当前日期暂无竞价强者V2数据。"}</h1>
            <p>{selectedReport?.global_conclusion.one_sentence_for_930 || "当日数据进入后，页面会自动刷新并展示 9:30 前执行重点。"}</p>
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

        <section className="auction-grid auction-grid--primary">
          <section className="auction-panel auction-strong-panel">
            <PanelHead icon={<Trophy className="h-5 w-5" />} title="Top5 强势标的" text="最终进入 9:30 前优先观察的主板个股。" />
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

          <section className="auction-panel auction-conclusion-panel">
            <PanelHead icon={<BarChart3 className="h-5 w-5" />} title="全局结论" text="把 9:25 最强、最超预期、容量确认和负反馈压缩成 9:30 观察重点。" />
            <div className="auction-conclusion-stack">
              <MetricTile label="最强个股" value={selectedReport?.global_conclusion.strongest_stock_at_925 || "--"} />
              <MetricTile label="最强题材" value={selectedReport?.global_conclusion.strongest_theme_cluster || "--"} />
              <MetricTile label="最超预期" value={selectedReport?.global_conclusion.most_over_expected_stock || "--"} />
              <MetricTile label="容量确认" value={selectedReport?.global_conclusion.best_capacity_confirmation || "--"} />
              <MetricTile label="最大负反馈" value={selectedReport?.global_conclusion.biggest_negative_feedback || "--"} />
            </div>
            <p className="auction-conclusion-text">{conclusionText || "所选日期暂无全局结论。"}</p>
          </section>
        </section>

        <section className="auction-panel auction-anchor-panel">
          <PanelHead icon={<Sparkles className="h-5 w-5" />} title="情绪锚点" text="涨停开、一字、接近涨停或强度锚，只给用户参考，不等于 Top5 可观察标的。" />
          {displayAnchors.length ? (
            <div className="auction-anchor-grid">
              {displayAnchors.slice(0, 18).map((anchor, index) => (
                <article className="auction-anchor-card" key={`${stockTitle(anchor)}-${index}`}>
                  <header>
                    <b>{stockTitle(anchor)}</b>
                    <strong data-tone={changeTone(String(anchor.today_open_change ?? ""))}>{changeText(anchor.today_open_change)}</strong>
                  </header>
                  <div className="auction-chip-row">
                    {anchor.theme ? <span>{anchor.theme}</span> : null}
                    {anchor.role ? <span>{anchor.role}</span> : null}
                    {anchor.label ? <span>{anchor.label}</span> : null}
                  </div>
                  <p>{anchor.reason || compactUnknown(anchor) || "--"}</p>
                  {anchor.participation_note ? <em>{anchor.participation_note}</em> : null}
                </article>
              ))}
            </div>
          ) : <EmptyState text="所选记录没有情绪锚点字段。" />}
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

          <section className="auction-panel auction-v2-panel">
            <PanelHead icon={<GitBranch className="h-5 w-5" />} title="题材门禁" text="Theme Gate 决定哪些题材放行，哪些题材排除。" />
            <div className="auction-v2-summary">
              <MetricTile label="最强题材" value={themeGate?.strongest_theme || "--"} />
              <MetricTile label="放行题材" value={`${admittedThemes.length || 0}`} />
              <MetricTile label="排除数量" value={`${themeGate?.excluded_theme_count ?? excludedThemes.length ?? 0}`} />
            </div>
            <div className="auction-theme-list">
              {admittedThemes.length ? admittedThemes.map((theme, index) => (
                <article key={`${theme.theme || "theme"}-${index}`}>
                  <b>{theme.priority ? `${theme.priority}. ` : ""}{theme.theme || "--"}</b>
                  <span>{[theme.theme_level, theme.theme_status, theme.confidence].filter(Boolean).join(" · ") || "--"}</span>
                  {theme.leader_candidates?.length ? (
                    <div className="auction-mini-stock-list">
                      {theme.leader_candidates.slice(0, 5).map((item, itemIndex) => (
                        <span key={`${theme.theme}-${stockTitle(item)}-${itemIndex}`}>{stockTitle(item)} · {item.role || "候选"} · {changeText(item.today_open_change)}</span>
                      ))}
                    </div>
                  ) : null}
                </article>
              )) : <EmptyState text="所选记录没有 V2 题材门禁字段。" />}
            </div>
            {excludedThemes.length ? (
              <div className="auction-note-list">
                {excludedThemes.map((theme, index) => (
                  <span key={`${theme.theme || "excluded"}-${index}`}>{theme.theme || "--"}：{theme.reason || "--"}</span>
                ))}
              </div>
            ) : null}
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
