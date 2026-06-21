"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { BarChart3, CalendarDays, FileUp, Flame, Info, Loader2, RefreshCcw, ShieldAlert, TrendingUp, Trophy } from "lucide-react";

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

export default function AuctionStrengthPage() {
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

  const loadReports = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "20" });
      if (selectedDate) params.set("date", selectedDate);
      const response = await fetch(`${API_BASE}/api/auction-strength?${params.toString()}`, { cache: "no-store" });
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
        setMessage(nextLatest ? "已刷新竞价强者数据。" : "当前日期暂无竞价强者数据。");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取竞价强者数据失败");
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
      <aside className="review-workbench-rail">
        <Link className="review-workbench-brand" href="/">
          <span className="brand-mark">盈</span>
          <span>
            <b>盈航</b>
            <small>MARKET DAY</small>
          </span>
        </Link>
        <nav className="review-workbench-nav" aria-label="核心功能">
          <Link href="/review">
            <FileUp />
            <span><b>AI复盘</b></span>
          </Link>
          <Link href="/watch">
            <BarChart3 />
            <span><b>AI盯盘</b></span>
          </Link>
          <Link href="/market-day">
            <TrendingUp />
            <span><b>AI当日行情</b></span>
          </Link>
          <Link className="active" href="/auction-strength">
            <Trophy />
            <span><b>竞价强者</b></span>
          </Link>
        </nav>
        <div className="review-rail-note">
          <Info />
          <span>接收 09:25 集合竞价后的强弱 JSON，映射 Top5 强势标的、回避标的和 9:30 执行重点。</span>
        </div>
      </aside>

      <section className="auction-main">
        <header className="auction-topbar">
          <div>
            <span>AUCTION STRENGTH</span>
            <b>竞价强者数据看板</b>
          </div>
          <div className="auction-topbar-actions">
            <label className="auction-date-picker">
              <CalendarDays className="h-4 w-4" />
              <input type="date" value={selectedDate} onChange={(event) => setSelectedDate(event.target.value)} />
            </label>
            <button className="auction-refresh-button" type="button" onClick={() => loadReports()} disabled={loading}>
              {loading ? <Loader2 className="spin-icon" /> : <RefreshCcw className="h-4 w-4" />}
              <span>{isToday ? "当日刷新" : "刷新所选日期"}</span>
            </button>
          </div>
        </header>

        <section className="auction-hero">
          <div>
            <p className="auction-kicker">
              <Flame className="h-4 w-4" />
              {selectedReport?.trade_date || selectedDate || "等待数据"} · {selectedReport?.analysis_time || "09:25 集合竞价后"}
            </p>
            <h1>{selectedReport?.summary.one_sentence || "当前日期暂无竞价强者数据。"}</h1>
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

        <section className="auction-grid auction-grid--lower">
          <section className="auction-panel auction-conclusion-panel">
            <PanelHead icon={<BarChart3 className="h-5 w-5" />} title="全局结论" />
            <p className="auction-conclusion-text">{conclusionText || "所选日期暂无全局结论。"}</p>
          </section>

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
