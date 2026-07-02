"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, CalendarDays, Info, Loader2, RefreshCcw, TrendingUp } from "lucide-react";
import { getAuthToken, storeUser } from "@/lib/auth-client";
import { MainSidebar } from "@/components/main-sidebar";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8600" : "");

type MarketDayPayload = {
  run_id?: string;
  status?: "queued" | "running" | "done" | "error";
  stage?: string;
  status_url?: string;
  report_url?: string;
  market_date?: string;
  billing_status?: "pending_generation" | "ready_to_charge" | "charged";
  estimated_seconds?: number;
  error?: string;
  detail?: string;
  report?: MarketDayReportEnvelope;
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
};

type MarketDayReportEnvelope = {
  market_date?: string;
  report?: {
    oneLineConclusion?: string;
    mainline?: { name?: string; reason?: string; score?: number; branches?: string[]; evidence?: string[] };
    marketMood?: { summary?: string; score?: number };
    strongestStocks?: Array<{ rank?: number; name?: string; leaderType?: string; theme?: string; strengthReason?: string; score?: number }>;
  };
};

type RecentMarketDayReport = {
  run_id: string;
  title?: string;
  created_at?: string;
  mainline?: string;
  one_line_conclusion?: string;
  report_route?: string;
};

export default function MarketDayPage() {
  const router = useRouter();
  const toastTimer = useRef<number | null>(null);
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const [marketDate, setMarketDate] = useState(today);
  const [generating, setGenerating] = useState(false);
  const [stage, setStage] = useState("idle");
  const [toast, setToast] = useState("");
  const [errorText, setErrorText] = useState("");
  const [preview, setPreview] = useState<MarketDayReportEnvelope | null>(null);
  const [recentReports, setRecentReports] = useState<RecentMarketDayReport[]>([]);
  const [recentLoading, setRecentLoading] = useState(false);

  function showToast(text: string) {
    setToast(text);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(""), 2600);
  }

  async function parseJsonResponse(response: Response): Promise<MarketDayPayload> {
    const text = await response.text();
    if (!text) return {};
    try {
      return JSON.parse(text) as MarketDayPayload;
    } catch {
      return { error: text };
    }
  }

  function formatError(payload: MarketDayPayload, fallback: string) {
    return [payload.error || fallback, payload.detail && payload.detail !== payload.error ? payload.detail : ""].filter(Boolean).join("\n");
  }

  async function apiFetch(path: string, init?: RequestInit) {
    const token = getAuthToken();
    if (!token) {
      router.push("/auth?redirect=/market-day");
      throw new Error("请先登录后生成当日行情复盘。");
    }
    return fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...(init?.headers || {}),
      },
      cache: "no-store",
    });
  }

  async function pollStatus(statusUrl: string): Promise<MarketDayPayload> {
    const target = statusUrl.startsWith("http") ? statusUrl : `${API_BASE}${statusUrl}`;
    for (let attempt = 0; attempt < 240; attempt += 1) {
      const response = await fetch(target, { cache: "no-store" });
      const payload = await parseJsonResponse(response);
      setStage(payload.stage || payload.status || "running");
      if (!response.ok) throw new Error(formatError(payload, "读取当日行情复盘状态失败"));
      if (payload.status === "done") return payload;
      if (payload.status === "error") throw new Error(formatError(payload, "当日行情复盘生成失败"));
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
    }
    throw new Error("当日行情复盘生成超时，请稍后刷新报告列表。");
  }

  async function refreshRecentReports(silent = false) {
    const token = getAuthToken();
    if (!token) {
      setRecentReports([]);
      return;
    }
    setRecentLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/market-day/reports?limit=12`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.error || "读取报告列表失败");
      const reports = Array.isArray(payload?.reports) ? payload.reports : [];
      setRecentReports(reports.filter((item: RecentMarketDayReport) => Boolean(item.run_id)));
    } catch (error) {
      if (!silent) showToast(error instanceof Error ? error.message : "读取报告列表失败");
    } finally {
      setRecentLoading(false);
    }
  }

  useEffect(() => {
    void refreshRecentReports(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function generateReport() {
    if (generating) return;
    setGenerating(true);
    setErrorText("");
    setPreview(null);
    setStage("queued");
    showToast("正在调用 Doubao 搜索当天行情主线。");

    try {
      const response = await apiFetch("/api/market-day/reports", {
        method: "POST",
        body: JSON.stringify({ market_date: marketDate }),
      });
      let payload = await parseJsonResponse(response);
      setStage(payload.stage || payload.status || "queued");
      if (!response.ok) throw new Error(formatError(payload, "当日行情复盘生成失败"));
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
      if (payload.status !== "done" && payload.status_url) {
        payload = await pollStatus(payload.status_url);
      }
      if (payload.report) setPreview(payload.report);
      await refreshRecentReports(true);
      const runId = payload.run_id || payload.report?.market_date || "";
      if (runId) router.push(`/market-day/report/${encodeURIComponent(runId)}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "当日行情复盘生成失败";
      setErrorText(message);
      showToast(message);
    } finally {
      setGenerating(false);
    }
  }

  const progress = progressForStage(stage);
  const mainline = preview?.report?.mainline;
  const strongestStocks = preview?.report?.strongestStocks || [];

  return (
    <main className="review-workbench-page market-day-page">
      <MainSidebar
        activeKey="market-day"
        note="默认复盘今天 A股全市场，先找主线，再判断主线内最强个股。"
      />

      <section className="review-workbench-main">
        <header className="review-workbench-topbar">
          <div className="review-topbar-title">
            <span className="topbar-icon"><TrendingUp /></span>
            <b>AI当日行情</b>
            <i>DAILY</i>
          </div>
          <div className="review-workbench-actions">
            <button type="button" onClick={() => router.push("/")}>首页</button>
            <button type="button" onClick={() => void refreshRecentReports()}>
              {recentLoading ? <Loader2 className="spin-icon" /> : <RefreshCcw />}
              <span>刷新</span>
            </button>
          </div>
        </header>

        <section className="review-workbench-hero market-day-hero">
          <div className="review-hero-copy">
            <p className="review-kicker">MARKET MAINLINE AGENT</p>
            <h1>用 AI 找出今天 A股最强主线和最强个股</h1>
            <p>Doubao 先搜索当天市场复盘、涨停潮、连板梯队和资金方向，Judge 再只基于证据包判断主线强弱和核心个股位置。</p>
          </div>
          <section className="research-panel market-day-generate-panel">
            <div className="market-day-date-card">
              <CalendarDays />
              <div>
                <span>复盘日期</span>
                <input
                  aria-label="选择复盘日期"
                  type="date"
                  value={marketDate}
                  onChange={(event) => setMarketDate(event.target.value || today)}
                  disabled={generating}
                />
              </div>
            </div>
            <button className="primary-gold-action" type="button" onClick={generateReport} disabled={generating}>
              {generating ? <Loader2 className="spin-icon" /> : <TrendingUp />}
              {generating ? "正在生成行情复盘" : marketDate === today ? "生成今天行情复盘" : "生成所选日期行情复盘"}
            </button>
            <div className="market-day-time-note">
              <Info />
              <span>预计 1-3 分钟。离开页面后可从历史报告继续查看；只有报告成功展示到前端后，才会扣除 1 次使用机会。</span>
            </div>
            {generating ? (
              <div className="generation-progress" role="status" aria-live="polite">
                <div className="generation-progress-head">
                  <b>{progress.label}</b>
                  <span>{progress.percent}%</span>
                </div>
                <div className="generation-progress-track" aria-hidden="true">
                  <i style={{ width: `${progress.percent}%` }} />
                </div>
                <p>{progress.detail}</p>
              </div>
            ) : null}
            {errorText ? <div className="upload-error"><b>生成失败</b><span>{errorText}</span></div> : null}
          </section>
        </section>

        {preview ? (
          <section className="research-panel market-day-preview-panel">
            <span className="card-label">最新判断</span>
            <h2>{preview.report?.oneLineConclusion || "当日行情复盘已生成"}</h2>
            <div className="market-day-summary-grid">
              <article>
                <span>最强主线</span>
                <b>{mainline?.name || "-"}</b>
                <p>{mainline?.reason || "等待 Judge 返回主线判断。"}</p>
              </article>
              <article>
                <span>市场情绪</span>
                <b>{preview.report?.marketMood?.score ?? "-"}</b>
                <p>{preview.report?.marketMood?.summary || "等待市场情绪判断。"}</p>
              </article>
            </div>
            <div className="market-day-stock-list">
              {strongestStocks.slice(0, 5).map((stock) => (
                <div key={`${stock.rank}-${stock.name}`}>
                  <em>#{stock.rank || "-"}</em>
                  <span>
                    <b>{stock.name || "未命名个股"}</b>
                    <small>{stock.leaderType || "证据不足"} · {stock.theme || "主线待确认"}</small>
                  </span>
                  <strong>{stock.score ?? "-"}</strong>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        <section className="research-panel recent-report-panel">
          <div className="recent-report-head">
            <div>
              <span className="card-label">历史行情复盘</span>
              <h2>最近生成的 AI当日行情报告</h2>
            </div>
            <button type="button" onClick={() => void refreshRecentReports()} disabled={recentLoading}>
              {recentLoading ? <Loader2 className="spin-icon" /> : <RefreshCcw />}
              刷新
            </button>
          </div>
          {recentReports.length ? (
            <div className="recent-report-list">
              {recentReports.map((item) => (
                <button
                  className="recent-report-item"
                  key={item.run_id}
                  type="button"
                  onClick={() => router.push(item.report_route || `/market-day/report/${encodeURIComponent(item.run_id)}`)}
                >
                  <span>
                    <b>{item.title || "AI当日行情"}</b>
                    <small>{item.one_line_conclusion || item.created_at || item.run_id}</small>
                  </span>
                  <em>{item.mainline || "主线"}</em>
                  <ArrowRight />
                </button>
              ))}
            </div>
          ) : (
            <div className="recent-report-empty">
              {recentLoading ? "正在读取报告列表..." : "暂无可查看的当日行情报告。"}
            </div>
          )}
        </section>
      </section>
      <div className={`studio-toast ${toast ? "show" : ""}`}>{toast}</div>
    </main>
  );
}

function progressForStage(stage: string) {
  if (stage === "market_day_agent") return { label: "正在搜索当天行情主线", detail: "Doubao 正在整理市场复盘、涨停潮、连板梯队和资金方向。", percent: 42 };
  if (stage === "write_market_day_report") return { label: "正在写入结构化报告", detail: "Judge 已完成判断，正在生成前端可读报告。", percent: 86 };
  if (stage === "done") return { label: "报告已生成", detail: "正在打开当日行情报告。", percent: 100 };
  return { label: "任务已提交", detail: "系统正在准备调用行情复盘 Agent。", percent: 12 };
}
