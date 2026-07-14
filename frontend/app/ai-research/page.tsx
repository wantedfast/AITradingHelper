"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CalendarDays, FileText, Loader2, LockKeyhole, RefreshCcw } from "lucide-react";
import { MainSidebar } from "@/components/main-sidebar";
import { FinancialDisclaimer } from "@/components/financial-disclaimer";
import { getAuthToken, storeUser, usageBillingText, type UserProfile } from "@/lib/auth-client";
import { type AiResearchReport, type AiResearchSummary, ReportBody, ReportMeta } from "./report-components";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8600" : "");

type BillingStatus = "no_data" | "pending_view" | "charged" | "free_history";

type DatedListPayload = {
  selected_date?: string;
  available_dates?: string[];
  reports?: AiResearchSummary[];
  billing_status?: BillingStatus;
  billing_cost?: number;
  user?: UserProfile;
  error?: string;
  detail?: string;
};

type ReportPayload = {
  status?: "queued" | "running" | "done" | "error";
  stage?: string;
  billing_status?: "charged" | "free_history";
  report?: AiResearchReport;
  user?: UserProfile;
  error?: string;
  detail?: string;
};

export default function AiResearchPage() {
  return <Suspense fallback={null}><AiResearchPageContent /></Suspense>;
}

function AiResearchPageContent() {
  const router = useRouter();
  const [selectedDate, setSelectedDate] = useState(todayIsoDate());
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [summary, setSummary] = useState<AiResearchSummary | null>(null);
  const [report, setReport] = useState<AiResearchReport | null>(null);
  const [billingMessage, setBillingMessage] = useState("");
  const [billingStatus, setBillingStatus] = useState<BillingStatus>("no_data");
  const activeRunIdRef = useRef("");
  const loadedRunIdRef = useRef("");
  const ackedRunIdsRef = useRef<Set<string>>(new Set());
  const requestRef = useRef(0);
  const isToday = selectedDate === todayIsoDate();

  function clearSelection(nextMessage = "") {
    requestRef.current += 1;
    activeRunIdRef.current = "";
    loadedRunIdRef.current = "";
    setConfirmed(false);
    setSummary(null);
    setReport(null);
    setBillingMessage("");
    setBillingStatus("no_data");
    setMessage(nextMessage);
    setLoading(false);
  }

  function handleDateChange(value: string) {
    setSelectedDate(value || todayIsoDate());
    clearSelection();
  }

  function confirmView() {
    const token = getAuthToken();
    if (!token) {
      router.push(`/auth?redirect=${encodeURIComponent("/ai-research")}`);
      return;
    }
    setConfirmed(true);
    setMessage("");
    setBillingMessage("");
  }

  const loadReport = useCallback(async (runId: string, token: string, requestId: number) => {
    if (!ackedRunIdsRef.current.has(runId)) {
      ackedRunIdsRef.current.add(runId);
      const ackResponse = await fetch(`${API_BASE}/api/ai-research/reports/${encodeURIComponent(runId)}/ack`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      const ackPayload = await readJson<ReportPayload>(ackResponse);
      if (!ackResponse.ok) {
        ackedRunIdsRef.current.delete(runId);
        throw new Error(formatError(ackPayload, "确认研报访问失败"));
      }
      if (requestId !== requestRef.current) return;
      if (ackPayload.user) {
        storeUser(ackPayload.user);
        setBillingMessage(`AI 研报已确认展示。${usageBillingText(ackPayload.user)}`);
      }
      setBillingStatus(ackPayload.billing_status || "charged");
    }

    const response = await fetch(`${API_BASE}/api/ai-research/reports/${encodeURIComponent(runId)}/status`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    const payload = await readJson<ReportPayload>(response);
    if (!response.ok) throw new Error(formatError(payload, "读取 AI 研报失败"));
    if (requestId !== requestRef.current) return;
    if (payload.status === "error") throw new Error(formatError(payload, "AI 研报生成失败"));
    if (payload.status !== "done" || !payload.report) {
      setMessage(`研报正在生成（${payload.stage || payload.status || "处理中"}），稍后将自动刷新。`);
      return;
    }
    activeRunIdRef.current = runId;
    loadedRunIdRef.current = runId;
    setReport(payload.report);
    setMessage("");
  }, []);

  const loadReports = useCallback(async (silent = false) => {
    const token = getAuthToken();
    if (!token) {
      router.push(`/auth?redirect=${encodeURIComponent("/ai-research")}`);
      return;
    }
    const requestId = ++requestRef.current;
    if (!silent) setLoading(true);
    try {
      const params = new URLSearchParams({ date: selectedDate });
      const response = await fetch(`${API_BASE}/api/ai-research/reports?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      const payload = await readJson<DatedListPayload>(response);
      if (!response.ok) throw new Error(formatError(payload, "读取 AI 研报失败"));
      if (requestId !== requestRef.current) return;
      setAvailableDates(payload.available_dates || []);
      setBillingStatus(payload.billing_status || "no_data");
      if (payload.user) storeUser(payload.user);
      const next = (payload.reports || [])[0] || null;
      if (!next?.run_id) {
        setSummary(null);
        setReport(null);
        activeRunIdRef.current = isToday ? "__no_report__" : "";
        loadedRunIdRef.current = "";
        setMessage("所选日期暂无 AI 研报，不会扣除使用次数。");
        return;
      }
      if (isToday && activeRunIdRef.current && activeRunIdRef.current !== next.run_id) {
        clearSelection("发现新的当日研报，请重新确认后查看；本次刷新未扣费。");
        return;
      }
      setSummary(next);
      activeRunIdRef.current = next.run_id;
      if (loadedRunIdRef.current !== next.run_id) {
        await loadReport(next.run_id, token, requestId);
      } else if (!silent) {
        setMessage("研报已刷新至所选日期的最新版本。");
      }
    } catch (error) {
      if (requestId !== requestRef.current) return;
      setMessage(error instanceof Error ? error.message : "读取 AI 研报失败");
    } finally {
      if (requestId === requestRef.current) setLoading(false);
    }
  }, [isToday, loadReport, router, selectedDate]);

  useEffect(() => {
    if (!confirmed) return;
    void loadReports();
  }, [confirmed, loadReports]);

  useEffect(() => {
    if (!confirmed || !isToday) return;
    const timer = window.setInterval(() => void loadReports(true), 15000);
    return () => window.clearInterval(timer);
  }, [confirmed, isToday, loadReports]);

  return (
    <main className="review-workbench-page auction-page dated-report-page ai-research-page">
      <MainSidebar activeKey="ai-research" note="按日期查看当天最新一份 AI 研报；确认后在当前页面展开正文。" />
      <section className="review-workbench-main auction-main">
        <header className="auction-topbar">
          <div><span>DAILY INSTITUTIONAL RESEARCH</span><b>AI 研报</b></div>
          <div className="auction-topbar-actions">
            <label className="auction-date-picker">
              <CalendarDays />
              <input type="date" value={selectedDate} max={todayIsoDate()} list="ai-research-available-dates" onChange={(event) => handleDateChange(event.target.value)} />
              <datalist id="ai-research-available-dates">{availableDates.map((date) => <option value={date} key={date} />)}</datalist>
            </label>
            {confirmed ? <button type="button" onClick={() => void loadReports()} disabled={loading}>{loading ? <Loader2 className="spin-icon" /> : <RefreshCcw />}<span>刷新研报</span></button> : null}
          </div>
        </header>

        <FinancialDisclaimer compact={confirmed} />

        <section className="auction-hero dated-report-hero">
          <div>
            <p className="auction-kicker"><FileText />{selectedDate} · {confirmed ? "已确认查看" : "确认后查看"}</p>
            <h1>{confirmed ? summary?.title || "等待所选日期的最新研报" : isToday ? "查看今天研报将扣除 2 次使用机会" : "历史 AI 研报免费查看"}</h1>
            <p>{confirmed ? summary?.summary || "当天只展示最新一份研报，正文将在当前页面展开。" : isToday ? "同一份研报重复刷新不重复扣费；若今天生成了新批次，会先退出正文并要求重新确认。" : "历史日期只展示该日最新一份已生成研报，不扣除使用次数。"}</p>
          </div>
          <div className="auction-status-strip">
            <article><span>所选日期</span><b>{selectedDate}</b></article>
            <article><span>研报状态</span><b>{summary ? "已生成" : confirmed ? "暂无数据" : "待确认"}</b></article>
            <article><span>计费状态</span><b>{billingStatusText(billingStatus, isToday)}</b></article>
          </div>
        </section>

        {!confirmed ? (
          <section className="auction-panel auction-confirm-panel">
            <div className="auction-panel-head"><LockKeyhole /><div><h2>确认查看 AI 研报</h2><p>{isToday ? "确认后读取今天最新一份研报并扣除 2 次使用机会。" : "确认后免费读取所选历史日期的最新一份研报。"}</p></div></div>
            <div className="auction-confirm-actions">
              <button type="button" onClick={confirmView}>{isToday ? "确认查看并扣除 2 次" : "确认免费查看历史研报"}</button>
              <span>所选日期无数据或读取失败时不会调用确认扣费接口。</span>
            </div>
          </section>
        ) : (
          <>
            {loading && !report ? <section className="auction-panel dated-report-empty" role="status"><Loader2 className="spin-icon" /><b>正在读取所选日期的最新研报</b></section> : null}
            {message ? <p className="auction-message" role="status">{message}</p> : null}
            {billingMessage ? <p className="auction-message" role="status">{billingMessage}</p> : null}
            {!loading && !summary ? <section className="auction-panel auction-empty"><b>暂无数据</b><span>所选日期暂无 AI 研报，请稍后刷新或选择其他日期。</span></section> : null}
            {report ? <InlineReport report={report} /> : null}
          </>
        )}
      </section>
    </main>
  );
}

function InlineReport({ report }: { report: AiResearchReport }) {
  return (
    <section id="ai-research-inline-report" className="ai-research-inline-stack ai-research-inline-report dated-report-content">
      <section className="review-workbench-hero market-day-report-hero">
        <div className="review-hero-copy"><p className="review-kicker">盘前研报</p><h1>{report.title || "AI 研报"}</h1><p>{report.summary || "本篇研报已生成。"}</p></div>
        <ReportMeta report={report} />
      </section>
      {report.tags?.length ? <section className="research-panel ai-tag-panel">{report.tags.map((tag) => <span key={tag}>{tag}</span>)}</section> : null}
      <ReportBody report={report} />
    </section>
  );
}

function todayIsoDate() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}`;
}

function billingStatusText(status: BillingStatus, isToday: boolean) {
  if (status === "charged") return "已确认";
  if (status === "free_history") return "历史免费";
  if (status === "pending_view") return "待确认扣费";
  return isToday ? "无数据不扣费" : "历史免费";
}

async function readJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  if (!text) return {} as T;
  try { return JSON.parse(text) as T; } catch { return { error: text } as T; }
}

function formatError(payload: { error?: string; detail?: string }, fallback: string) {
  return [payload.error || fallback, payload.detail && payload.detail !== payload.error ? payload.detail : ""].filter(Boolean).join("\n");
}
