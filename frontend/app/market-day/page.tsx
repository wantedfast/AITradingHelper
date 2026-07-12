"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Info, Loader2, RefreshCcw, TrendingUp } from "lucide-react";
import { getAuthToken, storeUser } from "@/lib/auth-client";
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

type MarketDayResponse = {
  ok?: boolean;
  billing_status?: "pending_generation" | "ready_to_charge" | "charged";
  error?: string;
  detail?: string;
  user?: MarketDayUser;
};

type RecentMarketDayReport = {
  run_id: string;
  created_at?: string;
  market_date?: string;
  mainline?: string;
  one_line_conclusion?: string;
  report_route?: string;
};

export default function MarketDayPage() {
  const router = useRouter();
  const toastTimer = useRef<number | null>(null);
  const [toast, setToast] = useState("");
  const [errorText, setErrorText] = useState("");
  const [recentReports, setRecentReports] = useState<RecentMarketDayReport[]>([]);
  const [recentLoading, setRecentLoading] = useState(false);
  const [openingRunId, setOpeningRunId] = useState("");
  const [authMissing, setAuthMissing] = useState(false);

  function showToast(text: string) {
    setToast(text);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(""), 2600);
  }

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

  async function refreshRecentReports(silent = false) {
    const token = getAuthToken();
    if (!token) {
      setAuthMissing(true);
      setRecentLoading(false);
      setErrorText("");
      setRecentReports([]);
      return;
    }

    setAuthMissing(false);
    setRecentLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/market-day/reports?limit=12`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      const payload = (await parseJsonResponse<{ reports?: RecentMarketDayReport[]; error?: string }>(response)) || {};
      if (!response.ok) throw new Error(payload.error || "读取报告列表失败");
      setErrorText("");
      setRecentReports((payload.reports || []).filter((item) => Boolean(item.run_id)));
    } catch (error) {
      const message = error instanceof Error ? error.message : "读取报告列表失败";
      setErrorText(message);
      if (!silent) showToast(message);
    } finally {
      setRecentLoading(false);
    }
  }

  async function openReport(report: RecentMarketDayReport) {
    if (openingRunId) return;

    const token = getAuthToken();
    if (!token) {
      router.push("/auth?redirect=/market-day");
      return;
    }

    setErrorText("");
    setOpeningRunId(report.run_id);

    try {
      const response = await fetch(`${API_BASE}/api/market-day/reports/${encodeURIComponent(report.run_id)}/ack`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      const payload = await parseJsonResponse<MarketDayResponse>(response);
      if (!response.ok) throw new Error(formatError(payload, "打开报告失败"));
      syncUser(payload.user);
      showToast("正在打开报告详情");
      router.push(report.report_route || `/market-day/report/${encodeURIComponent(report.run_id)}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "打开报告失败";
      setErrorText(message);
      showToast(message);
      setOpeningRunId("");
    }
  }

  useEffect(() => {
    void refreshRecentReports(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimer.current) window.clearTimeout(toastTimer.current);
    };
  }, []);

  return (
    <main className="review-workbench-page market-day-page">
      <MainSidebar
        activeKey="market-day"
        note="系统会按交易日自动生成当日行情报告，先判断市场主线，再定位主线中的最强个股。"
      />

      <section className="review-workbench-main">
        <header className="review-workbench-topbar">
          <div className="review-topbar-title">
            <span className="topbar-icon">
              <TrendingUp />
            </span>
            <b>AI当日行情</b>
            <i>DAILY</i>
          </div>
          <div className="review-workbench-actions">
            <button type="button" onClick={() => router.push("/")}>
              首页
            </button>
            <button type="button" onClick={() => void refreshRecentReports()} disabled={recentLoading}>
              {recentLoading ? <Loader2 className="spin-icon" /> : <RefreshCcw />}
              <span>刷新</span>
            </button>
          </div>
        </header>

        <section className="review-workbench-hero market-day-hero">
          <div className="review-hero-copy">
            <p className="review-kicker">MARKET MAINLINE AGENT</p>
            <h1>Codex 每日整理当日行情主线与最强个股</h1>
            <p>报告由 Codex 完成公开信息研究和结构化整理，系统接收成品后统一发布到报告列表。</p>
          </div>

          <section className="research-panel market-day-intro-panel">
            <div className="market-day-intro-grid">
              <article>
                <span>生成方式</span>
                <b>Codex 推送</b>
                <p>当前页面不调用其他模型，也不在浏览器中发起生成，只展示已经接收完成的报告。</p>
              </article>
              <article>
                <span>报告内容</span>
                <b>结论更紧凑</b>
                <p>列表直接给出报告日期、一句话结论和当日主线，进入详情再看完整证据。</p>
              </article>
              <article>
                <span>计费确认</span>
                <b>后端幂等</b>
                <p>点击“查看”会先确认展示，再按 run_id 执行同报告幂等扣次。</p>
              </article>
            </div>

            <div className="market-day-time-note">
              <Info />
              <span>报告打开前会先向后端发送确认请求；同一份报告重复进入仍由后端保证不会重复计费。</span>
            </div>
          </section>
        </section>

        <section className="research-panel recent-report-panel">
          <div className="recent-report-head">
            <div>
              <span className="card-label">系统生成报告</span>
              <h2>最近生成的 AI 当日行情</h2>
            </div>
            <button type="button" onClick={() => void refreshRecentReports()} disabled={recentLoading}>
              {recentLoading ? <Loader2 className="spin-icon" /> : <RefreshCcw />}
              刷新
            </button>
          </div>

          {errorText && recentReports.length ? (
            <div className="upload-error" role="alert">
              <b>操作失败</b>
              <span>{errorText}</span>
            </div>
          ) : null}

          {recentLoading && !recentReports.length ? (
            <section className="market-day-loading-panel" role="status" aria-live="polite">
              <Loader2 className="spin-icon" />
              <b>正在读取当日行情报告</b>
              <span>系统正在同步最近生成的结果</span>
            </section>
          ) : null}

          {!recentLoading && errorText && !recentReports.length ? (
            <section className="market-day-loading-panel is-error" role="alert">
              <b>读取失败</b>
              <span>{errorText}</span>
            </section>
          ) : null}

          {!recentLoading && !errorText && recentReports.length ? (
            <div className="market-day-report-list">
              {recentReports.map((report) => {
                const isOpening = openingRunId === report.run_id;
                const reportDate = formatReportDate(report.market_date || report.created_at || report.run_id);
                return (
                  <article className="market-day-report-card" key={report.run_id}>
                    <div className="market-day-report-card-head">
                      <div>
                        <span>报告日期</span>
                        <h3>{reportDate}</h3>
                      </div>
                      <em>{report.mainline || "主线待补充"}</em>
                    </div>

                    <p className="market-day-report-summary">
                      {report.one_line_conclusion || "系统已完成当日行情判断，点击查看完整主线与个股证据。"}
                    </p>

                    <div className="market-day-report-meta">
                      <span>
                        <b>主线</b>
                        <strong>{report.mainline || "待补充"}</strong>
                      </span>
                      <span>
                        <b>生成时间</b>
                        <strong>{report.created_at || "--"}</strong>
                      </span>
                    </div>

                    <button
                      className="primary-gold-action market-day-open-button"
                      type="button"
                      onClick={() => void openReport(report)}
                      disabled={isOpening}
                    >
                      {isOpening ? <Loader2 className="spin-icon" /> : <ArrowRight />}
                      <span>查看</span>
                    </button>
                  </article>
                );
              })}
            </div>
          ) : null}

          {!recentLoading && !errorText && !recentReports.length ? (
            <div className="recent-report-empty">{authMissing ? "登录后可查看系统生成的当日行情报告。" : "暂无可查看的当日行情报告。"}</div>
          ) : null}
        </section>
      </section>

      <div className={`studio-toast ${toast ? "show" : ""}`}>{toast}</div>
    </main>
  );
}

function formatReportDate(value: string) {
  if (!value) return "--";
  return value.slice(0, 10);
}
