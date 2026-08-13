"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, FileText, Loader2, RefreshCcw } from "lucide-react";
import { MainSidebar } from "@/components/main-sidebar";
import { FinancialDisclaimer } from "@/components/financial-disclaimer";
import { getAuthToken, storeUser, usageBillingText, type UserProfile } from "@/lib/auth-client";
import { type AiResearchReport, isBeginnerResearchReport, ReportBody, ReportMeta } from "../../report-components";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8600" : "");

type AckPayload = {
  billing_status?: "charged" | "free_history";
  report?: AiResearchReport;
  user?: UserProfile;
  error?: string;
  detail?: string;
};

export default function AiResearchReportPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const runId = decodeURIComponent(params.id);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [billingMessage, setBillingMessage] = useState("");
  const [report, setReport] = useState<AiResearchReport | null>(null);
  const beginnerReport = Boolean(report && isBeginnerResearchReport(report));

  const loadReport = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      router.push(`/auth?redirect=${encodeURIComponent(`/ai-research/report/${runId}`)}`);
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const response = await fetch(`${API_BASE}/api/ai-research/reports/${encodeURIComponent(runId)}/ack`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      const payload = await readJson<AckPayload>(response);
      if (!response.ok) throw new Error(formatError(payload, "读取 AI 研报失败"));
      if (!payload.report) throw new Error("AI 研报内容不可用，请返回日期选择后重试。");
      if (payload.user) {
        storeUser(payload.user);
        const prefix = payload.billing_status === "free_history" ? "历史研报免费展示。" : "AI 研报已确认展示。";
        setBillingMessage(`${prefix}${usageBillingText(payload.user)}`);
      }
      setReport(payload.report);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取 AI 研报失败");
    } finally {
      setLoading(false);
    }
  }, [router, runId]);

  useEffect(() => { void loadReport(); }, [loadReport]);

  return (
    <main className={`review-workbench-page market-day-page ai-research-page ${beginnerReport ? "ai-beginner-report-page" : ""}`}>
      <MainSidebar
        activeKey="ai-research"
        note={beginnerReport ? "每天 08:30 汇总重要消息，帮助你先看懂市场，再决定是否参与。" : undefined}
        prototypeIcons={beginnerReport}
      />
      <section className="review-workbench-main">
        <header className="review-workbench-topbar">
          <div className="review-topbar-title"><span className="topbar-icon"><FileText /></span><b>AI 研报{report && isBeginnerResearchReport(report) ? " · 30秒判断" : ""}</b><i>{report?.research_date || "REPORT"}</i></div>
          <div className="review-workbench-actions">
            <button type="button" onClick={() => router.push("/ai-research")}><ArrowLeft /><span>返回日期选择</span></button>
            <button type="button" onClick={() => void loadReport()} disabled={loading}>{loading ? <Loader2 className="spin-icon" /> : <RefreshCcw />}<span>刷新</span></button>
          </div>
        </header>
        <FinancialDisclaimer compact />
        {loading && !report ? <section className="research-panel market-day-loading-panel" role="status"><Loader2 className="spin-icon" /><b>正在读取 AI 研报</b></section> : null}
        {message ? <section className="research-panel market-day-loading-panel is-error" role="alert"><b>研报状态</b><span>{message}</span></section> : null}
        {billingMessage ? <p className="auction-message" role="status">{billingMessage}</p> : null}
        {report ? (
          <section className="ai-research-inline-stack ai-research-inline-report dated-report-content">
            {!isBeginnerResearchReport(report) ? <section className="review-workbench-hero market-day-report-hero">
              <div className="review-hero-copy"><p className="review-kicker">盘前研报</p><h1>{report.title || "AI 研报"}</h1><p>{report.summary || "本篇研报已生成。"}</p></div>
              <ReportMeta report={report} />
            </section> : null}
            {!isBeginnerResearchReport(report) && report.tags?.length ? <section className="research-panel ai-tag-panel">{report.tags.map((tag) => <span key={tag}>{tag}</span>)}</section> : null}
            <ReportBody report={report} />
          </section>
        ) : null}
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
