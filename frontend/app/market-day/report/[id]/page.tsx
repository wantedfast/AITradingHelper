"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, BarChart3, FileUp, Loader2, RefreshCcw, ShieldCheck, TrendingUp, Trophy } from "lucide-react";
import { getAuthToken, storeUser, usageBillingText } from "@/lib/auth-client";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8600" : "");

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
    evidence?: string[];
    score?: number;
  };
  strongestStocks?: Array<{
    rank?: number;
    name?: string;
    code?: string;
    leaderType?: string;
    theme?: string;
    strengthReason?: string;
    evidence?: string[];
    riskOrDivergence?: string;
    score?: number;
  }>;
  secondaryLines?: Array<{ name?: string; reason?: string; representativeStocks?: string[]; evidence?: string[] }>;
  fakeOrWeakLines?: Array<{ name?: string; reason?: string; evidence?: string[] }>;
  watchPoints?: string[];
  audit?: { missingEvidence?: string[]; sourceWarnings?: string[] };
};

type StatusPayload = {
  status?: "queued" | "running" | "done" | "error";
  stage?: string;
  billing_status?: "pending_generation" | "ready_to_charge" | "charged";
  report?: MarketDayEnvelope;
  user?: {
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
  error?: string;
  detail?: string;
};

export default function MarketDayReportPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const runId = decodeURIComponent(params.id);
  const ackStartedRef = useRef(false);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("loading");
  const [errorText, setErrorText] = useState("");
  const [billingMessage, setBillingMessage] = useState("");
  const [reportEnvelope, setReportEnvelope] = useState<MarketDayEnvelope | null>(null);

  function syncUser(payload: StatusPayload) {
    if (payload.user?.id && payload.user.phone && payload.user.role && payload.user.invite_code) {
      storeUser({
        id: payload.user.id,
        phone: payload.user.phone,
        role: payload.user.role as "user" | "admin",
        invite_code: payload.user.invite_code,
        credits: payload.user.credits || 0,
        membership_plan: payload.user.membership_plan || "",
        membership_status: payload.user.membership_status || "",
        membership_expires_at: payload.user.membership_expires_at || "",
        membership_active: Boolean(payload.user.membership_active),
        referral_count: payload.user.referral_count || 0,
        created_at: payload.user.created_at || "",
      });
    }
  }

  async function acknowledgeVisibleReport() {
    if (ackStartedRef.current) return;
    ackStartedRef.current = true;
    const token = getAuthToken();
    if (!token) return;
    try {
      const response = await fetch(`${API_BASE}/api/market-day/reports/${encodeURIComponent(runId)}/ack`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      const payload = (await response.json()) as StatusPayload & { ok?: boolean };
      if (!response.ok) throw new Error(payload.error || "报告已展示，但扣除使用次数失败");
      syncUser(payload);
      setBillingMessage(`报告已成功展示。${usageBillingText(payload.user)}`);
    } catch (error) {
      ackStartedRef.current = false;
      setBillingMessage(error instanceof Error ? error.message : "报告已展示，但扣除使用次数失败");
    }
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
      const response = await fetch(`${API_BASE}/api/market-day/reports/${encodeURIComponent(runId)}/status`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      const payload = (await response.json()) as StatusPayload;
      if (!response.ok) throw new Error(payload.error || "读取当日行情报告失败");
      setStatus(payload.stage || payload.status || "unknown");
      if (payload.status === "done" && payload.report) {
        setReportEnvelope(payload.report);
        if (payload.billing_status === "charged") {
          syncUser(payload);
          setBillingMessage(`报告已成功展示。${usageBillingText(payload.user)}`);
        } else {
          void acknowledgeVisibleReport();
        }
      } else if (payload.status === "error") {
        throw new Error([payload.error || "报告生成失败", payload.detail || ""].filter(Boolean).join("\n"));
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
      <aside className="review-workbench-rail">
        <Link className="review-workbench-brand" href="/">
          <span className="brand-mark">盈</span>
          <span>
            <b>盈航</b>
            <small>MARKET REPORT</small>
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
          <Link className="active" href="/market-day">
            <TrendingUp />
            <span><b>AI当日行情</b></span>
          </Link>
          <Link href="/auction-strength">
            <Trophy />
            <span><b>竞价强者</b></span>
          </Link>
        </nav>
      </aside>

      <section className="review-workbench-main">
        <header className="review-workbench-topbar">
          <div className="review-topbar-title">
            <span className="topbar-icon"><TrendingUp /></span>
            <b>AI当日行情报告</b>
            <i>{report?.marketDate || reportEnvelope?.market_date || "REPORT"}</i>
          </div>
          <div className="review-workbench-actions">
            <button type="button" onClick={() => router.push("/market-day")}>
              <ArrowLeft />
              <span>返回</span>
            </button>
            <button type="button" onClick={() => void loadReport()}>
              {loading ? <Loader2 className="spin-icon" /> : <RefreshCcw />}
              <span>刷新</span>
            </button>
          </div>
        </header>

        {loading && !report ? (
          <section className="research-panel market-day-loading-panel">
            <Loader2 className="spin-icon" />
            <b>正在读取当日行情报告</b>
            <span>{status}</span>
          </section>
        ) : null}

        {errorText ? (
          <section className="research-panel market-day-loading-panel is-error">
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
                {(report.mainline?.branches || []).map((branch) => <span key={branch}>{branch}</span>)}
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
                      <h3>{stock.name || "未命名个股"} <small>{stock.code || ""}</small></h3>
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
                <LineList items={report.secondaryLines?.map((item) => `${item.name || "未命名"}：${item.reason || "证据不足"}`)} />
              </section>
              <section className="research-panel">
                <span className="card-label">伪主线 / 弱方向</span>
                <LineList items={report.fakeOrWeakLines?.map((item) => `${item.name || "未命名"}：${item.reason || "证据不足"}`)} />
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

function EvidenceList({ items }: { items?: string[] }) {
  const lines = (items || []).filter(Boolean).slice(0, 6);
  if (!lines.length) return null;
  return (
    <ul className="market-day-evidence-list">
      {lines.map((item) => <li key={item}>{item}</li>)}
    </ul>
  );
}

function LineList({ items, icon = false }: { items?: string[]; icon?: boolean }) {
  const lines = (items || []).filter(Boolean);
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

function formatScore(value?: number) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return `${Math.round(value * 10) / 10}/10`;
}
