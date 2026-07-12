"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Activity, ArrowRight, Clock3, Loader2, Network, RefreshCcw, Target, TrendingUp } from "lucide-react";
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
      if (!silent) showToast("列表已更新");
    } catch (error) {
      const message = error instanceof Error ? error.message : "读取报告列表失败";
      setErrorText(message);
      if (!silent) showToast("刷新失败，请稍后重试");
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
      <MainSidebar activeKey="market-day" />

      <section className="review-workbench-main">
        <header className="review-workbench-topbar">
          <div className="review-topbar-title">
            <span className="topbar-icon">
              <TrendingUp />
            </span>
            <b>AI当日行情</b>
            <i>DAILY MARKET REVIEW</i>
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

        <section className="market-day-overview">
          <div className="market-day-overview-copy">
            <span>A股收盘复盘</span>
            <h1>每日收盘后，快速看懂市场主线、情绪与强势方向</h1>
            <p>结合指数表现、市场情绪、题材强度与核心个股反馈，为你提炼当日最重要的市场结构和次日观察方向。</p>
          </div>
          <div className="market-day-capabilities" aria-label="复盘能力">
            <article>
              <Network />
              <span>市场结构</span>
              <b>识别主线</b>
            </article>
            <article>
              <Activity />
              <span>情绪周期</span>
              <b>判断强弱</b>
            </article>
            <article>
              <Target />
              <span>决策输出</span>
              <b>验证方向</b>
            </article>
          </div>
        </section>

        <section className="research-panel recent-report-panel">
          <div className="recent-report-head">
            <div>
              <span className="card-label">最新复盘</span>
              <h2>查看最近生成的市场复盘</h2>
              <p>每日收盘后自动生成；首次查看扣除 1 次，同一交易日重复查看不重复扣次。</p>
            </div>
            <button type="button" onClick={() => void refreshRecentReports()} disabled={recentLoading}>
              {recentLoading ? <Loader2 className="spin-icon" /> : <RefreshCcw />}
              <span>{recentLoading ? "刷新中" : "刷新列表"}</span>
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
                const marketMood = inferMarketMood(report.one_line_conclusion || "");
                return (
                  <article className="market-day-report-card" key={report.run_id}>
                    <div className="market-day-report-content">
                      <div className="market-day-report-card-head">
                        <h3>A股当日行情复盘 · {reportDate}</h3>
                        <div className="market-day-report-tags">
                          <span>{reportDate}</span>
                          <em>{report.mainline || "主线待补充"}</em>
                        </div>
                      </div>

                      <p className="market-day-report-summary">
                        {report.one_line_conclusion || "系统已完成当日行情判断，点击查看完整主线与个股证据。"}
                      </p>

                      <div className="market-day-report-meta">
                        <span>
                          <Network />
                          <span><b>市场主线</b><strong>{report.mainline || "待补充"}</strong></span>
                        </span>
                        <span>
                          <Activity />
                          <span><b>情绪状态</b><strong>{marketMood}</strong></span>
                        </span>
                        <span>
                          <Clock3 />
                          <span><b>生成时间</b><strong>{formatGeneratedAt(report.created_at || "")}</strong></span>
                        </span>
                      </div>
                    </div>

                    <button
                      className="primary-gold-action market-day-open-button"
                      type="button"
                      onClick={() => void openReport(report)}
                      disabled={isOpening}
                    >
                      {isOpening ? <Loader2 className="spin-icon" /> : <ArrowRight />}
                      <span>{isOpening ? "正在打开" : "查看完整复盘"}</span>
                    </button>
                  </article>
                );
              })}
            </div>
          ) : null}

          {!recentLoading && !errorText && !recentReports.length ? (
            <div className="recent-report-empty market-day-empty-state">
              <b>{authMissing ? "登录后查看市场复盘" : "今日复盘尚未生成"}</b>
              <span>{authMissing ? "登录后即可查看最近生成的完整市场复盘。" : "报告将在 A 股交易日收盘后生成，请稍后刷新查看。"}</span>
              <button type="button" onClick={() => void refreshRecentReports()} disabled={recentLoading}>
                {recentLoading ? <Loader2 className="spin-icon" /> : <RefreshCcw />}
                <span>{recentLoading ? "刷新中" : "刷新列表"}</span>
              </button>
            </div>
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

function formatGeneratedAt(value: string) {
  if (!value) return "--";
  return value.slice(0, 16);
}

function inferMarketMood(summary: string) {
  const moods = ["高位分歧", "退潮", "冰点修复", "强修复", "弱修复", "主升", "加速", "轮动", "混沌"];
  return moods.find((mood) => summary.includes(mood)) || "详见报告";
}
