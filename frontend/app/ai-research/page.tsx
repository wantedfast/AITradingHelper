"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CalendarDays, FileText, Loader2, LockKeyhole, RefreshCcw } from "lucide-react";
import { MainSidebar } from "@/components/main-sidebar";
import { FinancialDisclaimer } from "@/components/financial-disclaimer";
import { MobileActionDock } from "@/components/mobile-action-dock";
import { MobileTaskHeader } from "@/components/mobile-task-header";
import { getAuthToken, storeUser, usageBillingText, type UserProfile } from "@/lib/auth-client";
import { canReadDatedReport, shouldShowDatedReportPayment, type BillingStatus } from "@/lib/dated-report-access";
import { type AiResearchReport, type AiResearchSummary, ReportBody, ReportMeta } from "./report-components";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8600" : "");

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
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [summary, setSummary] = useState<AiResearchSummary | null>(null);
  const [report, setReport] = useState<AiResearchReport | null>(null);
  const [billingMessage, setBillingMessage] = useState("");
  const [billingStatus, setBillingStatus] = useState<BillingStatus>("no_data");
  const [billingCost, setBillingCost] = useState(0);
  const loadedRunIdRef = useRef("");
  const ackedRunIdsRef = useRef<Set<string>>(new Set());
  const requestRef = useRef(0);
  const isToday = selectedDate === todayIsoDate();

  function clearSelection(nextMessage = "") {
    requestRef.current += 1;
    loadedRunIdRef.current = "";
    setSummary(null);
    setReport(null);
    setBillingMessage("");
    setBillingStatus("no_data");
    setBillingCost(0);
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
    setMessage("");
    setBillingMessage("");
    if (!summary?.run_id) return;
    const requestId = ++requestRef.current;
    setLoading(true);
    void loadReport(summary.run_id, token, requestId, true)
      .catch((error) => setMessage(error instanceof Error ? error.message : "确认研报访问失败"))
      .finally(() => {
        if (requestId === requestRef.current) setLoading(false);
      });
  }

  const loadReport = useCallback(async (runId: string, token: string, requestId: number, shouldAcknowledge = false) => {
    if (shouldAcknowledge && !ackedRunIdsRef.current.has(runId)) {
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
      setBillingCost(0);
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
      const nextBillingStatus = payload.billing_status || "no_data";
      setBillingStatus(nextBillingStatus);
      setBillingCost(payload.billing_cost || 0);
      if (payload.user) storeUser(payload.user);
      const next = (payload.reports || [])[0] || null;
      if (!next?.run_id) {
        setSummary(null);
        setReport(null);
        loadedRunIdRef.current = "";
        setMessage("所选日期暂无 AI 研报，不会扣除使用次数。");
        return;
      }
      setSummary(next);
      if (canReadDatedReport(nextBillingStatus)) {
        if (loadedRunIdRef.current !== next.run_id) {
          await loadReport(next.run_id, token, requestId);
        } else if (!silent) {
          setMessage("研报已刷新至所选日期的最新版本。");
        }
      } else {
        const replaced = isToday && loadedRunIdRef.current && loadedRunIdRef.current !== next.run_id;
        setReport(null);
        loadedRunIdRef.current = "";
        if (replaced || !silent) {
          setMessage(replaced ? "发现新的当日研报，请重新确认后查看；本次刷新未扣费。" : "");
        }
      }
    } catch (error) {
      if (requestId !== requestRef.current) return;
      setMessage(error instanceof Error ? error.message : "读取 AI 研报失败");
    } finally {
      if (requestId === requestRef.current) setLoading(false);
    }
  }, [isToday, loadReport, router, selectedDate]);

  useEffect(() => {
    void loadReports();
  }, [loadReports]);

  useEffect(() => {
    if (!isToday) return;
    const timer = window.setInterval(() => void loadReports(true), 15000);
    return () => window.clearInterval(timer);
  }, [isToday, loadReports]);

  return (
    <main className="review-workbench-page auction-page dated-report-page ai-research-page">
      <MainSidebar activeKey="ai-research" note="每天 08:30（早上 8:30）汇总国内外重要消息，解释 CPI、黄金、原油和海外观点可能怎样影响 A 股。" />
      <section className="review-workbench-main auction-main">
        <header className="auction-topbar">
          <div><span>DAILY INSTITUTIONAL RESEARCH</span><b>AI 研报</b></div>
          <div className="auction-topbar-actions">
            <label className="auction-date-picker">
              <CalendarDays />
              <input type="date" value={selectedDate} max={todayIsoDate()} list="ai-research-available-dates" onChange={(event) => handleDateChange(event.target.value)} />
              <datalist id="ai-research-available-dates">{availableDates.map((date) => <option value={date} key={date} />)}</datalist>
            </label>
            <button type="button" onClick={() => void loadReports()} disabled={loading}>{loading ? <Loader2 className="spin-icon" /> : <RefreshCcw />}<span>刷新研报</span></button>
          </div>
        </header>

        <FinancialDisclaimer compact={canReadDatedReport(billingStatus)} />

        <MobileTaskHeader
          eyebrow={<><FileText />{selectedDate}</>}
          title="AI 研报"
          description={canReadDatedReport(billingStatus) ? summary?.summary || "国内外重要信息已经整理完成。" : billingStatus === "pending_view" ? `确认后扣除 ${billingCost} 次使用机会。` : "所选日期暂无研报，可稍后刷新。"}
          status={billingStatusText(billingStatus, isToday)}
        />

        <section className="auction-hero dated-report-hero">
          <div>
            <p className="auction-kicker"><FileText />{selectedDate} · {canReadDatedReport(billingStatus) ? "可以直接查看" : billingStatus === "pending_view" ? "确认后查看" : "等待研报"}</p>
            <h1>{canReadDatedReport(billingStatus) ? summary?.title || "等待所选日期的最新研报" : billingStatus === "pending_view" ? `查看今天研报将扣除 ${billingCost} 次使用机会` : "所选日期暂无 AI 研报"}</h1>
            <p>{canReadDatedReport(billingStatus) ? summary?.summary || "当天只展示最新一份研报，正文已在当前页面展开。" : billingStatus === "pending_view" ? "同一份研报重复刷新不重复扣费；若今天生成了新批次，会重新要求确认。" : "没有数据不会扣除使用次数，可以稍后刷新或选择其他日期。"}</p>
          </div>
          <div className="auction-status-strip">
            <article><span>所选日期</span><b>{selectedDate}</b></article>
            <article><span>研报状态</span><b>{summary ? "已生成" : "暂无数据"}</b></article>
            <article><span>计费状态</span><b>{billingStatusText(billingStatus, isToday)}</b></article>
          </div>
        </section>

        {shouldShowDatedReportPayment(billingStatus, Boolean(summary)) ? (
          <section className="auction-panel auction-confirm-panel">
            <div className="auction-panel-head"><LockKeyhole /><div><h2>确认查看 AI 研报</h2><p>今天这份研报尚未付费，确认后扣除 {billingCost} 次使用机会。</p></div></div>
            <MobileActionDock className="auction-confirm-actions">
              <button type="button" onClick={confirmView} disabled={loading}>确认查看并扣除 {billingCost} 次</button>
              <span>所选日期无数据或读取失败时不会调用确认扣费接口。</span>
            </MobileActionDock>
          </section>
        ) : (
          <>
            {loading && !report ? <section className="auction-panel dated-report-empty" role="status"><Loader2 className="spin-icon" /><b>正在读取所选日期的最新研报</b></section> : null}
            {message ? <p className="auction-message" role="status">{message}</p> : null}
            {billingMessage ? <p className="auction-message" role="status">{billingMessage}</p> : null}
            {!loading && billingStatus === "no_data" ? <section className="auction-panel auction-empty"><b>暂无数据</b><span>所选日期暂无 AI 研报，请稍后刷新或选择其他日期。</span></section> : null}
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
