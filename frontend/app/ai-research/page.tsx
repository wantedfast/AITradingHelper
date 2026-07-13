"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { FileText, Loader2, RefreshCcw } from "lucide-react";
import { MainSidebar } from "@/components/main-sidebar";
import { FinancialDisclaimer } from "@/components/financial-disclaimer";
import { getAuthToken, storeUser, usageBillingText, type UserProfile } from "@/lib/auth-client";
import { AiResearchReport, AiResearchSummary, ReportBody, ReportMeta } from "./report-components";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8600" : "");

type StatusPayload = {
  status?: string;
  report?: AiResearchReport;
  error?: string;
};

type AckPayload = StatusPayload & {
  billing_status?: "charged";
  user?: UserProfile;
};

type LoadReportOptions = {
  shouldScroll?: boolean;
  updateQuery?: boolean;
  charge?: boolean;
};

export default function AiResearchPage() {
  return (
    <Suspense fallback={null}>
      <AiResearchPageContent />
    </Suspense>
  );
}

function AiResearchPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedRunId = searchParams.get("report")?.trim() || "";

  const [reports, setReports] = useState<AiResearchSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [selectedRunId, setSelectedRunId] = useState("");
  const [selectedReport, setSelectedReport] = useState<AiResearchReport | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailMessage, setDetailMessage] = useState("");
  const [failedRunId, setFailedRunId] = useState("");
  const [billingMessage, setBillingMessage] = useState("");
  const listRequestRef = useRef(0);
  const detailRequestRef = useRef(0);
  const previousRequestedRunIdRef = useRef(requestedRunId);

  function replaceReportQuery(runId: string) {
    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.set("report", runId);
    router.replace(`/ai-research?${nextParams.toString()}`, { scroll: false });
  }

  async function refreshReports() {
    const token = getAuthToken();
    if (!token) {
      const target = `${window.location.pathname}${window.location.search}`;
      router.push(`/auth?redirect=${encodeURIComponent(target)}`);
      return;
    }

    const requestId = ++listRequestRef.current;
    setLoading(true);
    setMessage("");

    try {
      const response = await fetch(`${API_BASE}/api/ai-research/reports?limit=30`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.error || "读取研报失败");
      if (requestId !== listRequestRef.current) return;

      const nextReports: AiResearchSummary[] = Array.isArray(payload?.reports) ? payload.reports : [];
      setReports(nextReports);

      if (!requestedRunId && selectedRunId && !nextReports.some((item) => item.run_id === selectedRunId)) {
        setSelectedRunId("");
        setSelectedReport(null);
        setDetailMessage("");
      }
    } catch (error) {
      if (requestId !== listRequestRef.current) return;
      setMessage(error instanceof Error ? error.message : "读取研报失败");
    } finally {
      if (requestId === listRequestRef.current) {
        setLoading(false);
      }
    }
  }

  async function loadReport(runId: string, options: LoadReportOptions = {}) {
    const { shouldScroll = true, updateQuery = true, charge = false } = options;
    const token = getAuthToken();
    if (!token) {
      router.push(`/auth?redirect=${encodeURIComponent(`/ai-research?report=${runId}`)}`);
      return;
    }

    const requestId = ++detailRequestRef.current;
    setSelectedRunId(runId);
    setDetailLoading(true);
    setDetailMessage("");
    setBillingMessage("");
    setFailedRunId("");
    setSelectedReport((current) => (current?.run_id === runId ? current : null));

    try {
      const endpoint = charge
        ? `${API_BASE}/api/ai-research/reports/${encodeURIComponent(runId)}/ack`
        : `${API_BASE}/api/ai-research/reports/${encodeURIComponent(runId)}/status`;
      const response = await fetch(endpoint, {
        method: charge ? "POST" : "GET",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      const payload = (await response.json()) as AckPayload;
      if (!response.ok) throw new Error(payload.error || "读取研报详情失败");
      if (!payload.report) throw new Error("研报暂不可用，请稍后刷新");
      if (requestId !== detailRequestRef.current) return;

      setSelectedReport(payload.report);
      if (updateQuery) {
        replaceReportQuery(runId);
      }
      if (payload.user) {
        storeUser(payload.user);
        setBillingMessage(`研报已展示。${usageBillingText(payload.user)}`);
      }

      if (shouldScroll) {
        window.setTimeout(() => {
          document.getElementById("ai-research-inline-report")?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 60);
      }
    } catch (error) {
      if (requestId !== detailRequestRef.current) return;
      setSelectedReport(null);
      setFailedRunId(runId);
      setDetailMessage(error instanceof Error ? error.message : "读取研报详情失败");
    } finally {
      if (requestId === detailRequestRef.current) {
        setDetailLoading(false);
      }
    }
  }

  useEffect(() => {
    void refreshReports();
    const timer = window.setInterval(() => void refreshReports(), 15000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const previousRequestedRunId = previousRequestedRunIdRef.current;
    previousRequestedRunIdRef.current = requestedRunId;
    if (!requestedRunId) {
      if (!previousRequestedRunId) return;
      detailRequestRef.current += 1;
      setSelectedRunId("");
      setSelectedReport(null);
      setDetailLoading(false);
      setDetailMessage("");
      setFailedRunId("");
      return;
    }

    if (failedRunId === requestedRunId) return;

    if (selectedReport?.run_id === requestedRunId || (detailLoading && selectedRunId === requestedRunId)) {
      if (selectedRunId !== requestedRunId) {
        setSelectedRunId(requestedRunId);
      }
      return;
    }

    void loadReport(requestedRunId, { shouldScroll: false, updateQuery: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedRunId, selectedReport?.run_id, detailLoading, selectedRunId, failedRunId]);

  return (
    <main className="review-workbench-page market-day-page ai-research-page">
      <MainSidebar
        activeKey="ai-research"
        note="每天盘前把重要消息转成可验证的观察清单。"
      />

      <section className="review-workbench-main">
        <header className="review-workbench-topbar">
          <div className="review-topbar-title">
            <span className="topbar-icon"><FileText /></span>
            <b>AI研报</b>
            <i>盘前决策工作台</i>
          </div>
          <div className="review-workbench-actions">
            <button type="button" onClick={() => router.push("/")}>首页</button>
            <button type="button" onClick={() => void refreshReports()} disabled={loading}>
              {loading ? <Loader2 className="spin-icon" /> : <RefreshCcw />}
              <span>刷新</span>
            </button>
          </div>
        </header>

        <FinancialDisclaimer compact={Boolean(selectedRunId)} />

        <section className="research-panel ai-research-shell-head">
          <div className="ai-research-shell-copy">
            <p className="review-kicker">海外机构产业研究</p>
            <h1>精选每日海外机构最新公开研究，提炼产业趋势、祝你把握今日方向</h1>
            <p>追踪海外投行、资管机构和行业研究机构最新公开观点，提炼产业变化、A股映射、验证条件和风险。</p>
          </div>
          <div className="ai-research-status-grid" aria-label="功能能力">
            <article>
              <span>机构研究</span>
              <b>来源可核验</b>
            </article>
            <article>
              <span>产业映射</span>
              <b>落到A股方向</b>
            </article>
            <article><span>决策输出</span><b>验证与失效条件</b></article>
          </div>
        </section>

        <section className="research-panel recent-report-panel" aria-labelledby="ai-research-list-heading">
          <div className="recent-report-head">
            <div>
              <span className="card-label">最新研报</span>
              <h2 id="ai-research-list-heading">点击查看完整研究结论</h2>
              <p className="ai-research-charge-note">首次查看每篇研报扣除 2 次使用机会，同一篇重复查看不重复扣次。</p>
            </div>
            <button type="button" onClick={() => void refreshReports()} disabled={loading}>
              {loading ? <Loader2 className="spin-icon" /> : <RefreshCcw />}
              刷新列表
            </button>
          </div>

          {message ? (
            <div className="upload-error" role="alert">
              <b>列表读取失败</b>
              <span>{message}</span>
            </div>
          ) : null}

          {reports.length ? (
            <div className="recent-report-list" role="list">
              {reports.map((item) => {
                const active = selectedRunId === item.run_id;
                return (
                  <article className={`recent-report-item${active ? " active" : ""}`} key={item.run_id} role="listitem">
                    <div className="recent-report-item-copy">
                      <div className="recent-report-item-title">
                        <b>{item.title || "AI研报"}</b>
                        <em>{item.research_date || "待补充日期"}</em>
                      </div>
                      <small>{item.summary || item.created_at || item.run_id}</small>
                      <span className="recent-report-item-meta">{item.created_at || item.run_id}</span>
                    </div>
                    <button
                      className="recent-report-view"
                      type="button"
                      aria-pressed={active}
                      onClick={() => void loadReport(item.run_id, { charge: true })}
                    >
                      {detailLoading && active ? <Loader2 className="spin-icon" /> : <span>查看研报</span>}
                    </button>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="recent-report-empty">
              {loading ? "正在读取研报列表..." : "暂无可查看的研报。"}
            </div>
          )}
        </section>

        {billingMessage ? <p className="auction-message" role="status">{billingMessage}</p> : null}
        <InlineReport
          report={selectedReport}
          loading={detailLoading}
          message={detailMessage}
          hasSelection={Boolean(selectedRunId)}
        />
      </section>
    </main>
  );
}

function InlineReport({
  report,
  loading,
  message,
  hasSelection,
}: {
  report: AiResearchReport | null;
  loading: boolean;
  message: string;
  hasSelection: boolean;
}) {
  if (loading && !report) {
    return (
      <section id="ai-research-inline-report" className="research-panel market-day-loading-panel">
        <Loader2 className="spin-icon" />
        <b>正在展开研报</b>
      </section>
    );
  }

  if (message) {
    return (
      <section id="ai-research-inline-report" className="research-panel market-day-loading-panel is-error">
        <b>研报读取失败</b>
        <p>{message}</p>
      </section>
    );
  }

  if (!report) {
    return (
      <section id="ai-research-inline-report" className="research-panel ai-research-inline-empty">
        <b>{hasSelection ? "正在准备研报内容" : "选择一篇研报后在这里展开正文"}</b>
        <p>{hasSelection ? "如果长时间没有内容，请刷新列表后重试。" : "点击上方“查看”，完整研报将在这里展开。"}</p>
      </section>
    );
  }

  return (
    <section id="ai-research-inline-report" className="ai-research-inline-stack ai-research-inline-report">
      <section className="review-workbench-hero market-day-report-hero">
        <div className="review-hero-copy">
          <p className="review-kicker">盘前研报</p>
          <h1>{report.title || "AI研报"}</h1>
          <p>{report.summary || "本篇研报已生成。"}</p>
        </div>
        <ReportMeta report={report} />
      </section>

      {report.tags?.length ? (
        <section className="research-panel ai-tag-panel">
          {report.tags.map((tag) => <span key={tag}>{tag}</span>)}
        </section>
      ) : null}

      <ReportBody report={report} />
    </section>
  );
}
