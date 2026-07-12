"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Loader2, RefreshCcw, ShieldCheck, TrendingUp } from "lucide-react";
import { getAuthToken, storeUser, usageBillingText } from "@/lib/auth-client";
import { MainSidebar } from "@/components/main-sidebar";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8600" : "");

type MarketDayUser = {
  id?: number;
  phone?: string;
  role?: string;
  invite_code?: string;
  credits?: number;
  membership_plan?: string | null;
  membership_status?: string | null;
  membership_expires_at?: string | null;
  membership_active?: boolean;
  referral_count?: number;
  created_at?: string;
};

type MarketDayEnvelope = {
  run_id?: string;
  market_date?: string;
  report?: MarketDayReport;
  doubao_search_pack?: string;
  research_metrics?: {
    model?: string;
    seconds?: number;
    estimated_cost_cny?: number;
  };
  doubao_search_metrics?: {
    model?: string;
    seconds?: number;
    cost_cny?: number;
  };
};

type MarketDayReport = {
  marketDate?: string;
  oneLineConclusion?: string;
  marketMood?: {
    summary?: string;
    limitUpCount?: string;
    limitDownCount?: string;
    heightBoard?: string;
    turnover?: string;
    score?: number;
  };
  mainline?: {
    name?: string;
    reason?: string;
    branches?: string[];
    evidence?: EvidenceItem[];
    score?: number;
  };
  strongestStocks?: Array<{
    rank?: number;
    name?: string;
    code?: string;
    leaderType?: string;
    theme?: string;
    strengthReason?: string;
    evidence?: EvidenceItem[];
    riskOrDivergence?: string;
    score?: number;
  }>;
  secondaryLines?: Array<{ name?: string; reason?: string; representativeStocks?: unknown[]; evidence?: EvidenceItem[] }>;
  fakeOrWeakLines?: Array<{ name?: string; reason?: string; evidence?: EvidenceItem[] }>;
  watchPoints?: Array<string | WatchPoint>;
  audit?: { missingEvidence?: string[]; sourceWarnings?: string[] };
};

type EvidenceItem = string | { content?: string; type?: string; sourceIds?: string[] };

type WatchPoint = {
  object?: string;
  condition?: string;
  positiveSignal?: string;
  negativeSignal?: string;
  meaning?: string;
};

type StatusPayload = {
  status?: "queued" | "running" | "done" | "error";
  stage?: string;
  billing_status?: "pending_generation" | "ready_to_charge" | "charged";
  report?: MarketDayEnvelope;
  user?: MarketDayUser;
  error?: string;
  detail?: string;
};

type AccessPayload = {
  ok?: boolean;
  billing_status?: "pending_generation" | "ready_to_charge" | "charged";
  user?: MarketDayUser;
  error?: string;
  detail?: string;
};

export default function MarketDayReportPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const runId = decodeURIComponent(params.id);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("authorizing");
  const [errorText, setErrorText] = useState("");
  const [billingMessage, setBillingMessage] = useState("");
  const [reportEnvelope, setReportEnvelope] = useState<MarketDayEnvelope | null>(null);

  function syncUser(user?: MarketDayUser) {
    if (!user?.id || !user.phone || !user.role || !user.invite_code) return;
    storeUser({
      id: user.id,
      phone: user.phone,
      role: user.role as "user" | "admin",
      invite_code: user.invite_code,
      credits: user.credits || 0,
      membership_plan: user.membership_plan || "",
      membership_status: user.membership_status || "",
      membership_expires_at: user.membership_expires_at || "",
      membership_active: Boolean(user.membership_active),
      referral_count: user.referral_count || 0,
      created_at: user.created_at || "",
    });
  }

  async function parseJsonResponse<T>(response: Response): Promise<T> {
    const text = await response.text();
    if (!text) return {} as T;
    try {
      return JSON.parse(text) as T;
    } catch {
      return { error: text } as T;
    }
  }

  function formatError(payload: { error?: string; detail?: string }, fallback: string) {
    return [payload.error || fallback, payload.detail && payload.detail !== payload.error ? payload.detail : ""]
      .filter(Boolean)
      .join("\n");
  }

  function buildBillingMessage(user?: MarketDayUser) {
    const usageText = usageBillingText(user);
    return usageText ? `报告已确认展示。${usageText}` : "报告已确认展示。";
  }

  async function acknowledgeReportAccess(token: string) {
    setStatus("authorizing");
    const response = await fetch(`${API_BASE}/api/market-day/reports/${encodeURIComponent(runId)}/ack`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    const payload = await parseJsonResponse<AccessPayload>(response);
    if (!response.ok) throw new Error(formatError(payload, "确认报告访问失败"));
    syncUser(payload.user);
    setBillingMessage(buildBillingMessage(payload.user));
  }

  async function fetchProtectedReport(token: string) {
    setStatus("loading");
    const response = await fetch(`${API_BASE}/api/market-day/reports/${encodeURIComponent(runId)}/status`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    const payload = await parseJsonResponse<StatusPayload>(response);
    if (!response.ok) throw new Error(formatError(payload, "读取当日行情报告失败"));
    return payload;
  }

  async function loadReport() {
    const token = getAuthToken();
    if (!token) {
      router.push(`/auth?redirect=/market-day/report/${encodeURIComponent(runId)}`);
      return;
    }

    setLoading(true);
    setErrorText("");

    try {
      await acknowledgeReportAccess(token);
      const payload = await fetchProtectedReport(token);
      setStatus(payload.stage || payload.status || "unknown");

      if (payload.status === "done" && payload.report) {
        setReportEnvelope(payload.report);
        return;
      }

      if (payload.status === "error") {
        throw new Error(formatError(payload, "报告生成失败"));
      }
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : "读取当日行情报告失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadReport();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  useEffect(() => {
    if (!loading && !reportEnvelope && !errorText) {
      const timer = window.setTimeout(() => void loadReport(), 1800);
      return () => window.clearTimeout(timer);
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, reportEnvelope, errorText, status]);

  const report = reportEnvelope?.report;
  const strongestStocks = report?.strongestStocks || [];

  return (
    <main className="review-workbench-page market-day-page market-day-report-surface">
      <MainSidebar activeKey="market-day" />

      <section className="review-workbench-main">
        <header className="review-workbench-topbar">
          <div className="review-topbar-title">
            <span className="topbar-icon">
              <TrendingUp />
            </span>
            <b>AI当日行情报告</b>
            <i>{report?.marketDate || reportEnvelope?.market_date || "REPORT"}</i>
          </div>
          <div className="review-workbench-actions">
            <button type="button" onClick={() => router.push("/market-day")}>
              <ArrowLeft />
              <span>返回</span>
            </button>
            <button type="button" onClick={() => void loadReport()} disabled={loading}>
              {loading ? <Loader2 className="spin-icon" /> : <RefreshCcw />}
              <span>刷新</span>
            </button>
          </div>
        </header>

        {loading && !report ? (
          <section className="research-panel market-day-loading-panel" role="status" aria-live="polite">
            <Loader2 className="spin-icon" />
            <b>{status === "authorizing" ? "正在确认报告访问权限" : "正在读取当日行情报告"}</b>
            <span>{status === "authorizing" ? "先确认展示，再读取受保护报告内容" : status}</span>
          </section>
        ) : null}

        {errorText ? (
          <section className="research-panel market-day-loading-panel is-error" role="alert">
            <b>读取失败</b>
            <span>{errorText}</span>
          </section>
        ) : null}

        {report ? (
          <>
            <section className="review-workbench-hero market-day-report-hero">
              <div className="review-hero-copy">
                <p className="review-kicker">MARKET JUDGE RESULT</p>
                <h1>{report.oneLineConclusion || "AI当日行情复盘"}</h1>
                <p>{report.mainline?.reason || "Judge 已完成当天行情主线判断。"}</p>
                {billingMessage ? <div className="market-day-billing-note">{billingMessage}</div> : null}
              </div>
              <div className="market-day-score-board">
                <div>
                  <span>最强主线</span>
                  <b>{report.mainline?.name || "-"}</b>
                </div>
                <div>
                  <span>主线强度</span>
                  <b>{formatScore(report.mainline?.score)}</b>
                </div>
                <div>
                  <span>市场情绪</span>
                  <b>{formatScore(report.marketMood?.score)}</b>
                </div>
              </div>
            </section>

            <section className="research-panel market-day-mood-panel">
              <span className="card-label">市场情绪</span>
              <h2>{report.marketMood?.summary || "市场情绪证据不足"}</h2>
              <div className="market-day-fact-grid">
                <Metric label="涨停家数" value={report.marketMood?.limitUpCount} />
                <Metric label="跌停家数" value={report.marketMood?.limitDownCount} />
                <Metric label="连板高度" value={report.marketMood?.heightBoard} />
                <Metric label="成交额" value={report.marketMood?.turnover} />
              </div>
            </section>

            <section className="research-panel market-day-mainline-panel">
              <span className="card-label">当日最强主线</span>
              <h2>{report.mainline?.name || "主线证据不足"}</h2>
              <p>{report.mainline?.reason || "暂无主线判断。"}</p>
              <div className="market-day-chip-row">
                {(report.mainline?.branches || []).map((branch) => (
                  <span key={branch}>{branch}</span>
                ))}
              </div>
              <EvidenceList items={report.mainline?.evidence} />
            </section>

            <section className="research-panel market-day-strong-panel">
              <div className="recent-report-head">
                <div>
                  <span className="card-label">主线内最强势个股</span>
                  <h2>强弱排名</h2>
                </div>
              </div>
              <div className="market-day-strong-list">
                {strongestStocks.map((stock) => (
                  <article key={`${stock.rank}-${stock.name}`}>
                    <div className="market-day-stock-rank">#{stock.rank || "-"}</div>
                    <div>
                      <h3>
                        {stock.name || "未命名个股"} <small>{stock.code || ""}</small>
                      </h3>
                      <p>{stock.strengthReason || "强势原因证据不足。"}</p>
                      <div className="market-day-chip-row">
                        <span>{stock.leaderType || "证据不足"}</span>
                        <span>{stock.theme || "主线待确认"}</span>
                        <span>{formatScore(stock.score)}</span>
                      </div>
                      <EvidenceList items={stock.evidence} />
                      {stock.riskOrDivergence ? <em>{stock.riskOrDivergence}</em> : null}
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="review-workbench-grid">
              <section className="research-panel">
                <span className="card-label">次主线</span>
                <LineList
                  items={report.secondaryLines?.map(
                    (item) => `${item.name || "未命名"}：${item.reason || "证据不足"}`,
                  )}
                />
              </section>
              <section className="research-panel">
                <span className="card-label">伪主线 / 弱方向</span>
                <LineList
                  items={report.fakeOrWeakLines?.map(
                    (item) => `${item.name || "未命名"}：${item.reason || "证据不足"}`,
                  )}
                />
              </section>
            </section>

            <section className="research-panel market-day-audit-panel">
              <span className="card-label">复盘观察</span>
              <LineList items={report.watchPoints} icon />
              <div className="market-day-audit-grid">
                <article>
                  <b>证据不足</b>
                  <LineList items={report.audit?.missingEvidence} />
                </article>
                <article>
                  <b>来源提醒</b>
                  <LineList items={report.audit?.sourceWarnings} />
                </article>
              </div>
            </section>
          </>
        ) : null}
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value?: string }) {
  return (
    <div>
      <span>{label}</span>
      <b>{value || "-"}</b>
    </div>
  );
}

function EvidenceList({ items }: { items?: EvidenceItem[] }) {
  const lines = (items || []).map(formatEvidenceItem).filter(Boolean).slice(0, 6);
  if (!lines.length) return null;
  return (
    <ul className="market-day-evidence-list">
      {lines.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function LineList({ items, icon = false }: { items?: unknown[]; icon?: boolean }) {
  const lines = (items || []).map(formatLineItem).filter(Boolean);
  if (!lines.length) return <p className="market-day-empty-text">暂无明确证据。</p>;
  return (
    <ul className="market-day-line-list">
      {lines.map((item) => (
        <li key={item}>
          {icon ? <ShieldCheck /> : null}
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function formatEvidenceItem(item: EvidenceItem) {
  if (typeof item === "string") return item.trim();
  const content = item?.content?.trim() || "";
  const type = item?.type?.trim() || "";
  return [type, content].filter(Boolean).join("：");
}

function formatLineItem(item: unknown) {
  if (typeof item === "string") return item.trim();
  if (!item || typeof item !== "object") return "";
  const point = item as WatchPoint;
  return [
    point.object,
    point.condition ? `条件：${point.condition}` : "",
    point.positiveSignal ? `正向：${point.positiveSignal}` : "",
    point.negativeSignal ? `负向：${point.negativeSignal}` : "",
    point.meaning ? `含义：${point.meaning}` : "",
  ]
    .filter(Boolean)
    .join("；");
}

function formatScore(value?: number) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return `${Math.round(value * 10) / 10}/10`;
}
