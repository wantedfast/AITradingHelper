"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CalendarDays, Loader2, LockKeyhole, RefreshCcw, TrendingUp } from "lucide-react";
import { MainSidebar } from "@/components/main-sidebar";
import { FinancialDisclaimer } from "@/components/financial-disclaimer";
import { MarketDayReportView, type MarketDayEnvelope } from "@/components/market-day-report-view";
import { getAuthToken, storeUser, usageBillingText, type UserProfile } from "@/lib/auth-client";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8600" : "");

type BillingStatus = "no_data" | "pending_view" | "charged" | "free_history";

type MarketDaySummary = {
  run_id: string;
  created_at?: string;
  market_date?: string;
  mainline?: string;
  one_line_conclusion?: string;
};

type DatedListPayload = {
  selected_date?: string;
  available_dates?: string[];
  reports?: MarketDaySummary[];
  billing_status?: BillingStatus;
  billing_cost?: number;
  user?: UserProfile;
  error?: string;
  detail?: string;
};

type AckPayload = {
  billing_status?: "charged" | "free_history";
  user?: UserProfile;
  error?: string;
  detail?: string;
};

type StatusPayload = {
  status?: "queued" | "running" | "done" | "error";
  stage?: string;
  report?: MarketDayEnvelope;
  error?: string;
  detail?: string;
};

export default function MarketDayPage() {
  const router = useRouter();
  const [selectedDate, setSelectedDate] = useState(todayIsoDate());
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [summary, setSummary] = useState<MarketDaySummary | null>(null);
  const [reportEnvelope, setReportEnvelope] = useState<MarketDayEnvelope | null>(null);
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
    setReportEnvelope(null);
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
      router.push(`/auth?redirect=/market-day`);
      return;
    }
    setConfirmed(true);
    setMessage("");
    setBillingMessage("");
  }

  const loadReport = useCallback(async (runId: string, token: string, requestId: number) => {
    if (!ackedRunIdsRef.current.has(runId)) {
      ackedRunIdsRef.current.add(runId);
      const ackResponse = await fetch(`${API_BASE}/api/market-day/reports/${encodeURIComponent(runId)}/ack`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      const ackPayload = await readJson<AckPayload>(ackResponse);
      if (!ackResponse.ok) {
        ackedRunIdsRef.current.delete(runId);
        throw new Error(formatError(ackPayload, "确认报告访问失败"));
      }
      if (requestId !== requestRef.current) return;
      if (ackPayload.user) {
        storeUser(ackPayload.user);
        setBillingMessage(`行情报告已确认展示。${usageBillingText(ackPayload.user)}`);
      }
      setBillingStatus(ackPayload.billing_status || "charged");
    }

    const response = await fetch(`${API_BASE}/api/market-day/reports/${encodeURIComponent(runId)}/status`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    const payload = await readJson<StatusPayload>(response);
    if (!response.ok) throw new Error(formatError(payload, "读取当日行情报告失败"));
    if (requestId !== requestRef.current) return;
    if (payload.status === "error") throw new Error(formatError(payload, "报告生成失败"));
    if (payload.status !== "done" || !payload.report?.report) {
      setMessage(`报告正在生成（${payload.stage || payload.status || "处理中"}），稍后将自动刷新。`);
      return;
    }
    activeRunIdRef.current = runId;
    loadedRunIdRef.current = runId;
    setReportEnvelope(payload.report);
    setMessage("");
  }, []);

  const loadReports = useCallback(async (silent = false) => {
    const token = getAuthToken();
    if (!token) {
      router.push(`/auth?redirect=/market-day`);
      return;
    }
    const requestId = ++requestRef.current;
    if (!silent) setLoading(true);
    try {
      const params = new URLSearchParams({ date: selectedDate });
      const response = await fetch(`${API_BASE}/api/market-day/reports?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      const payload = await readJson<DatedListPayload>(response);
      if (!response.ok) throw new Error(formatError(payload, "读取行情报告失败"));
      if (requestId !== requestRef.current) return;

      setAvailableDates(payload.available_dates || []);
      setBillingStatus(payload.billing_status || "no_data");
      if (payload.user) storeUser(payload.user);
      const next = (payload.reports || [])[0] || null;
      if (!next?.run_id) {
        setSummary(null);
        setReportEnvelope(null);
        activeRunIdRef.current = isToday ? "__no_report__" : "";
        loadedRunIdRef.current = "";
        setMessage("所选日期暂无当日行情报告，不会扣除使用次数。");
        return;
      }

      if (isToday && activeRunIdRef.current && activeRunIdRef.current !== next.run_id) {
        clearSelection("发现新的当日行情报告，请重新确认后查看；本次刷新未扣费。");
        return;
      }

      setSummary(next);
      activeRunIdRef.current = next.run_id;
      if (loadedRunIdRef.current !== next.run_id) {
        await loadReport(next.run_id, token, requestId);
      } else if (!silent) {
        setMessage("报告已刷新至最新版本。");
      }
    } catch (error) {
      if (requestId !== requestRef.current) return;
      setMessage(error instanceof Error ? error.message : "读取行情报告失败");
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
    <main className="review-workbench-page auction-page dated-report-page market-day-page">
      <MainSidebar activeKey="market-day" note="按日期查看 AI 当日行情；确认后在当前页面展开完整复盘。" />
      <section className="review-workbench-main auction-main">
        <header className="auction-topbar">
          <div><span>DAILY MARKET REVIEW</span><b>AI 当日行情</b></div>
          <div className="auction-topbar-actions">
            <label className="auction-date-picker">
              <CalendarDays />
              <input type="date" value={selectedDate} max={todayIsoDate()} list="market-day-available-dates" onChange={(event) => handleDateChange(event.target.value)} />
              <datalist id="market-day-available-dates">{availableDates.map((date) => <option value={date} key={date} />)}</datalist>
            </label>
            {confirmed ? (
              <button type="button" onClick={() => void loadReports()} disabled={loading}>
                {loading ? <Loader2 className="spin-icon" /> : <RefreshCcw />}<span>刷新报告</span>
              </button>
            ) : null}
          </div>
        </header>

        <FinancialDisclaimer compact={confirmed} />

        <section className="auction-hero dated-report-hero">
          <div>
            <p className="auction-kicker"><TrendingUp />{selectedDate} · {confirmed ? "已确认查看" : "确认后查看"}</p>
            <h1>{confirmed ? summary?.one_line_conclusion || "等待所选日期的行情报告" : isToday ? "查看今天行情将扣除 1 次使用机会" : "历史行情报告免费查看"}</h1>
            <p>{confirmed ? summary?.mainline ? `当前主线：${summary.mainline}` : "报告正文将在完成确认后于当前页面展开。" : isToday ? "同一份报告重复刷新不重复扣费；若今天生成了新批次，会先退出正文并要求重新确认。" : "历史日期只读取已生成报告，不扣除使用次数，也不会触发新的报告生成。"}</p>
          </div>
          <div className="auction-status-strip">
            <article><span>所选日期</span><b>{selectedDate}</b></article>
            <article><span>报告状态</span><b>{summary ? "已生成" : confirmed ? "暂无数据" : "待确认"}</b></article>
            <article><span>计费状态</span><b>{billingStatusText(billingStatus, isToday)}</b></article>
          </div>
        </section>

        {!confirmed ? (
          <section className="auction-panel auction-confirm-panel">
            <div className="auction-panel-head"><LockKeyhole /><div><h2>确认查看 AI 当日行情</h2><p>{isToday ? "确认后读取今天最新一份行情报告并扣除 1 次使用机会。" : "确认后免费读取所选历史日期的最新一份行情报告。"}</p></div></div>
            <div className="auction-confirm-actions">
              <button type="button" onClick={confirmView}>{isToday ? "确认查看并扣除 1 次" : "确认免费查看历史报告"}</button>
              <span>所选日期无数据或读取失败时不会调用确认扣费接口。</span>
            </div>
          </section>
        ) : (
          <>
            {loading && !reportEnvelope ? <LoadingPanel text="正在读取所选日期的行情报告" /> : null}
            {message ? <p className="auction-message" role="status">{message}</p> : null}
            {billingMessage ? <p className="auction-message" role="status">{billingMessage}</p> : null}
            {!loading && !summary ? <EmptyPanel text="所选日期暂无行情报告，请稍后刷新或选择其他日期。" /> : null}
            {reportEnvelope ? <MarketDayReportView envelope={reportEnvelope} /> : null}
          </>
        )}
      </section>
    </main>
  );
}

function LoadingPanel({ text }: { text: string }) {
  return <section className="auction-panel dated-report-empty" role="status"><Loader2 className="spin-icon" /><b>{text}</b></section>;
}

function EmptyPanel({ text }: { text: string }) {
  return <section className="auction-panel auction-empty"><b>暂无数据</b><span>{text}</span></section>;
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
