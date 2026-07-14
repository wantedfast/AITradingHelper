"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Loader2, RefreshCcw, TrendingUp } from "lucide-react";
import { MainSidebar } from "@/components/main-sidebar";
import { FinancialDisclaimer } from "@/components/financial-disclaimer";
import { MarketDayReportView, type MarketDayEnvelope } from "@/components/market-day-report-view";
import { getAuthToken, storeUser, usageBillingText, type UserProfile } from "@/lib/auth-client";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8600" : "");

type ApiPayload = {
  status?: "queued" | "running" | "done" | "error";
  stage?: string;
  report?: MarketDayEnvelope;
  user?: UserProfile;
  error?: string;
  detail?: string;
};

export default function MarketDayReportPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const runId = decodeURIComponent(params.id);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [billingMessage, setBillingMessage] = useState("");
  const [envelope, setEnvelope] = useState<MarketDayEnvelope | null>(null);

  const loadReport = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      router.push(`/auth?redirect=${encodeURIComponent(`/market-day/report/${runId}`)}`);
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const ackResponse = await fetch(`${API_BASE}/api/market-day/reports/${encodeURIComponent(runId)}/ack`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      const ackPayload = await readJson<ApiPayload>(ackResponse);
      if (!ackResponse.ok) throw new Error(formatError(ackPayload, "确认报告访问失败"));
      if (ackPayload.user) {
        storeUser(ackPayload.user);
        setBillingMessage(`行情报告已确认展示。${usageBillingText(ackPayload.user)}`);
      }

      const response = await fetch(`${API_BASE}/api/market-day/reports/${encodeURIComponent(runId)}/status`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      const payload = await readJson<ApiPayload>(response);
      if (!response.ok) throw new Error(formatError(payload, "读取行情报告失败"));
      if (payload.status === "error") throw new Error(formatError(payload, "报告生成失败"));
      if (payload.status === "done" && payload.report?.report) {
        setEnvelope(payload.report);
      } else {
        setMessage(`报告正在生成（${payload.stage || payload.status || "处理中"}），请稍后刷新。`);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取行情报告失败");
    } finally {
      setLoading(false);
    }
  }, [router, runId]);

  useEffect(() => { void loadReport(); }, [loadReport]);

  return (
    <main className="review-workbench-page market-day-page">
      <MainSidebar activeKey="market-day" />
      <section className="review-workbench-main">
        <header className="review-workbench-topbar">
          <div className="review-topbar-title"><span className="topbar-icon"><TrendingUp /></span><b>AI 当日行情报告</b><i>{envelope?.market_date || "REPORT"}</i></div>
          <div className="review-workbench-actions">
            <button type="button" onClick={() => router.push("/market-day")}><ArrowLeft /><span>返回日期选择</span></button>
            <button type="button" onClick={() => void loadReport()} disabled={loading}>{loading ? <Loader2 className="spin-icon" /> : <RefreshCcw />}<span>刷新</span></button>
          </div>
        </header>
        <FinancialDisclaimer compact />
        {loading && !envelope ? <section className="research-panel market-day-loading-panel" role="status"><Loader2 className="spin-icon" /><b>正在读取行情报告</b></section> : null}
        {message ? <section className="research-panel market-day-loading-panel is-error" role="alert"><b>报告状态</b><span>{message}</span></section> : null}
        {envelope ? <MarketDayReportView envelope={envelope} billingMessage={billingMessage} /> : null}
      </section>
    </main>
  );
}

async function readJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  if (!text) return {} as T;
  try { return JSON.parse(text) as T; } catch { return { error: text } as T; }
}

function formatError(payload: { error?: string; detail?: string }, fallback: string) {
  return [payload.error || fallback, payload.detail && payload.detail !== payload.error ? payload.detail : ""].filter(Boolean).join("\n");
}
