"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { getAuthToken, storeUser, usageBillingText, type UserProfile } from "@/lib/auth-client";

type ViewKey = "review" | "choice" | "theme" | "logic";

type ReviewItem = {
  key?: string;
  label?: string;
  text?: string;
};

type NextAction = {
  text?: string;
};

type ReviewScore = {
  key?: string;
  label?: string;
  value?: number;
};

type ReviewJudgment = {
  key?: string;
  label?: string;
  text?: string;
  summary?: string | null;
};

type ChainNode = {
  label?: string;
  role?: string | null;
  level?: string;
  name?: string;
  current?: boolean;
};

type RankingItem = {
  rank?: number | string;
  name?: string;
  reason?: string | null;
};

type Presenter = {
  presenter_contract?: string;
  review?: {
    verdict?: {
      text?: string | null;
    } | null;
    scores?: {
      items?: ReviewScore[];
    };
    judgments?: {
      items?: ReviewJudgment[];
    };
    items?: ReviewItem[];
    nextActions?: {
      text?: string | null;
      items?: NextAction[];
    };
  };
  bestChoice?: {
    available?: boolean;
    name?: string | null;
    summary?: string | null;
    ranking?: RankingItem[];
  };
  companyComparison?: {
    shortTermCapitalRanking?: RankingItem[];
    industryValueRanking?: RankingItem[];
    summary?: string | null;
  };
  tradeLogic?: {
    text?: string | null;
    summary?: string | null;
  };
  themeAnalysis?: {
    industryChain?: {
      nodes?: ChainNode[];
    };
    profitFlow?: {
      text?: string | null;
    };
  };
};

type AckPayload = {
  ok?: boolean;
  error?: string;
  billing_status?: "pending_generation" | "charged";
  user?: UserProfile;
};

type ReviewReportPageProps = {
  params: { id: string };
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

const views: Array<{ key: ViewKey; number: string; label: string }> = [
  { key: "review", number: "1", label: "复盘评价" },
  { key: "logic", number: "2", label: "交易逻辑" },
  { key: "choice", number: "3", label: "同行对比" },
  { key: "theme", number: "4", label: "题材分析" },
];

function copy(value: unknown, fallback = "原始报告未提供") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function scoreCopy(value: unknown, forceHundredScale = false) {
  const score = normalizedScore(value, forceHundredScale);
  if (score === null) return "--";
  return Number.isInteger(score) ? `${score}` : `${Number(score.toFixed(1))}`;
}

function normalizedScore(value: unknown, forceHundredScale = false) {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  if (forceHundredScale || value > 10) return Math.max(0, Math.min(10, value / 10));
  return Math.max(0, Math.min(10, value));
}

function scorePercent(value: unknown, forceHundredScale = false) {
  const score = normalizedScore(value, forceHundredScale);
  return score === null ? 0 : score * 10;
}

export default function ReviewReportPage({ params }: ReviewReportPageProps) {
  const reportId = decodeURIComponent(params.id);
  const presenterUrl = `${API_BASE}/api/reports/${encodeURIComponent(reportId)}/research_presenter_data.json`;
  const [activeView, setActiveView] = useState<ViewKey>("review");
  const [presenter, setPresenter] = useState<Presenter | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [billingMessage, setBillingMessage] = useState("");
  const ackStartedRef = useRef(false);

  const acknowledgeVisibleReport = useCallback(async () => {
    if (ackStartedRef.current) return;
    ackStartedRef.current = true;
    const token = getAuthToken();
    if (!token) {
      ackStartedRef.current = false;
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/api/reports/${encodeURIComponent(reportId)}/ack`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      const payload = (await response.json()) as AckPayload;
      if (!response.ok) throw new Error(payload.error || "报告已展示，但扣除使用次数失败");
      if (payload.user) {
        storeUser(payload.user);
        setBillingMessage(`报告已成功展示。${usageBillingText(payload.user)}`);
      }
    } catch (ackError) {
      ackStartedRef.current = false;
      setBillingMessage(ackError instanceof Error ? ackError.message : "报告已展示，但扣除使用次数失败");
    }
  }, [reportId]);

  const loadPresenter = useCallback(async () => {
    setLoading(true);
    setError("");
    setPresenter(null);

    try {
      const response = await fetch(presenterUrl, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Presenter 请求失败：${response.status}`);
      }
      setPresenter((await response.json()) as Presenter);
      void acknowledgeVisibleReport();
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Presenter 加载失败");
    } finally {
      setLoading(false);
    }
  }, [acknowledgeVisibleReport, presenterUrl]);

  useEffect(() => {
    void loadPresenter();
  }, [loadPresenter]);

  const reviewItems = presenter?.review?.items?.slice(0, 4) || [];
  const reviewScores = presenter?.review?.scores?.items || [];
  const reviewScoresUseHundredScale = reviewScores.some(
    (item) => typeof item.value === "number" && Number.isFinite(item.value) && item.value > 10,
  );
  const reviewJudgments = presenter?.review?.judgments?.items || [];
  const nextActions = presenter?.review?.nextActions?.items || [];
  const nextActionsText = presenter?.review?.nextActions?.text
    || nextActions.map((item) => copy(item.text, "")).filter(Boolean).join("\n");
  const shortTermRanking = presenter?.companyComparison?.shortTermCapitalRanking || presenter?.bestChoice?.ranking || [];
  const chainNodes = presenter?.themeAnalysis?.industryChain?.nodes || [];

  return (
    <main className="review-page">
      <style dangerouslySetInnerHTML={{ __html: styles }} />

      <header className="topbar glass">
        <Link className="icon-button" href="/review" aria-label="返回复盘列表" title="返回复盘列表">
          <span>返回复盘</span>
        </Link>
        <div className="report-brand">
          <strong>AI复盘报告</strong>
          <span>{reportId}</span>
        </div>
        <button className="icon-button refresh-button" type="button" onClick={() => void loadPresenter()} aria-label="刷新报告" title="刷新报告">
          <span>刷新</span>
        </button>
      </header>

      <div className="workspace">
        <aside className="side-nav glass" aria-label="报告视图">
          <p>报告导航</p>
          <div className="view-tabs" role="tablist" aria-label="报告章节">
            {views.map((view) => (
              <button
                key={view.key}
                className={activeView === view.key ? "active" : ""}
                type="button"
                role="tab"
                aria-selected={activeView === view.key}
                aria-controls={`${view.key}-panel`}
                onClick={() => setActiveView(view.key)}
              >
                <b>{view.number}</b>
                <span>{view.label}</span>
              </button>
            ))}
          </div>
        </aside>

        <div className="content">
          {billingMessage && (
            <div className="billing-note glass" role="status">
              {billingMessage}
            </div>
          )}

          {loading && (
            <section className="state glass" aria-live="polite">
              <span className="state-mark" aria-hidden="true">...</span>
              <p>正在读取报告</p>
            </section>
          )}

          {!loading && error && (
            <section className="state error glass" role="alert">
              <span className="state-mark" aria-hidden="true">!</span>
              <strong>报告加载失败</strong>
              <p>{error}</p>
              <button type="button" onClick={() => void loadPresenter()}>重试</button>
            </section>
          )}

          {!loading && presenter && activeView === "review" && (
            <section id="review-panel" className="report-view glass" role="tabpanel" aria-label="复盘评价">
              <div className="view-heading">
                <span>REVIEW VERDICT</span>
                <h1>复盘评价</h1>
              </div>

              <div className="verdict">
                <span>总评</span>
                <p>{copy(presenter.review?.verdict?.text)}</p>
              </div>

              <div className="review-decision-layout">
                <aside className="score-panel" aria-label="评分维度">
                  <div className="total-score">
                    <span>综合评分</span>
                    <strong>{scoreCopy(reviewScores.find((item) => item.key === "total")?.value, reviewScoresUseHundredScale)}</strong>
                    <small>满分 10 分</small>
                  </div>

                  <div className="score-list">
                    {reviewScores.filter((item) => item.key !== "total").length > 0 ? (
                      reviewScores.filter((item) => item.key !== "total").map((item) => (
                        <article key={item.key || item.label}>
                          <div>
                            <span>{copy(item.label)}</span>
                            <strong>{scoreCopy(item.value, reviewScoresUseHundredScale)}<small>/10</small></strong>
                          </div>
                          <i><b style={{ width: `${scorePercent(item.value, reviewScoresUseHundredScale)}%` }} /></i>
                        </article>
                      ))
                    ) : null}
                  </div>
                </aside>

                <section className="judgment-panel" aria-label="判断结论">
                  {reviewJudgments.length > 0 ? reviewJudgments.map((item, index) => (
                    <article key={item.key || `${item.label}-${index}`}>
                      <span>{String(index + 1).padStart(2, "0")}</span>
                      <div>
                        <h2>{copy(item.label, `判断 ${index + 1}`)}</h2>
                        <p>{copy(item.summary || item.text)}</p>
                      </div>
                    </article>
                  )) : reviewItems.length > 0 ? reviewItems.map((item, index) => (
                    <article key={item.key || `${item.label}-${index}`}>
                      <span>{String(index + 1).padStart(2, "0")}</span>
                      <div>
                        <h2>{copy(item.label, `判断 ${index + 1}`)}</h2>
                        <p>{copy(item.text)}</p>
                      </div>
                    </article>
                  )) : (
                    <p className="empty-copy">原始报告未提供判断</p>
                  )}
                </section>
              </div>

              <div className="next-actions">
                <div className="subheading">
                  <span>NEXT ACTION</span>
                  <h2>如果交易重来一次选谁</h2>
                </div>
                {nextActionsText ? (
                  <article className="action-full-text">
                    <p>{nextActionsText}</p>
                  </article>
                ) : (
                  <p className="empty-copy">原始报告未提供下次行动</p>
                )}
              </div>
            </section>
          )}

          {!loading && presenter && activeView === "choice" && (
            <section id="choice-panel" className="report-view glass" role="tabpanel" aria-label="同行对比">
              <div className="view-heading">
                <span>PEER COMPARISON</span>
                <h1>同行对比</h1>
              </div>

              {shortTermRanking.length === 0 ? (
                <div className="unavailable">
                  <span aria-hidden="true">—</span>
                  <p>原始报告未提供同行对比</p>
                </div>
              ) : (
                <div className="comparison-grid single">
                  <RankingPanel title="同行标的对比" kicker="PEER TARGETS" items={shortTermRanking} />
                </div>
              )}
            </section>
          )}

          {!loading && presenter && activeView === "theme" && (
            <section id="theme-panel" className="report-view glass" role="tabpanel" aria-label="题材分析">
              <div className="view-heading">
                <span>THEME ANALYSIS</span>
                <h1>题材分析</h1>
              </div>

              <div className="theme-section">
                <div className="subheading">
                  <span>INDUSTRY CHAIN</span>
                  <h2>产业链</h2>
                </div>

                {chainNodes.length > 0 ? (
                  <div className="chain-flow">
                    {chainNodes.map((node, index) => (
                      <div className="chain-step" key={`${node.role || node.level}-${node.label || node.name}-${index}`}>
                        <article className={node.current ? "current" : ""}>
                          {(node.role || node.level) && <span>{node.role || node.level}</span>}
                          <strong>{copy(node.label || node.name)}</strong>
                          {node.current && <small>当前标的</small>}
                        </article>
                        {index < chainNodes.length - 1 && (
                          <>
                            <span className="flow-arrow horizontal" aria-hidden="true">→</span>
                            <span className="flow-arrow vertical" aria-hidden="true">↓</span>
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="empty-copy">原始报告未提供产业链</p>
                )}
              </div>

              <div className="theme-section profit-flow">
                <div className="subheading">
                  <span>PROFIT FLOW</span>
                  <h2>利润流向</h2>
                </div>
                <p>{copy(presenter.themeAnalysis?.profitFlow?.text)}</p>
              </div>
            </section>
          )}

          {!loading && presenter && activeView === "logic" && (
            <section id="logic-panel" className="report-view glass" role="tabpanel" aria-label="交易逻辑">
              <div className="view-heading">
                <span>TRADE LOGIC</span>
                <h1>交易逻辑</h1>
              </div>

              {presenter.tradeLogic?.text ? (
                <div className="trade-logic-content">
                  {presenter.tradeLogic.summary && <strong>{presenter.tradeLogic.summary}</strong>}
                  <p>{presenter.tradeLogic.text}</p>
                </div>
              ) : (
                <p className="empty-copy">原始报告未提供交易逻辑</p>
              )}
            </section>
          )}
        </div>
      </div>
    </main>
  );
}

function RankingPanel({ title, kicker, items }: { title: string; kicker: string; items: RankingItem[] }) {
  return (
    <section className="ranking-panel">
      <div className="subheading">
        <span>{kicker}</span>
        <h2>{title}</h2>
      </div>

      {items.length > 0 ? (
        <ol className="ranking-list">
          {items.map((item, index) => (
            <li key={`${title}-${item.rank}-${item.name}-${index}`}>
              <span className="rank">{copy(item.rank, String(index + 1))}</span>
              <div>
                <h3>{copy(item.name)}</h3>
                <p>{copy(item.reason)}</p>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="empty-copy">原始报告未提供这一榜单</p>
      )}
    </section>
  );
}

const styles = `
:root {
  --page: #f6f8fb;
  --surface: #ffffff;
  --surface-strong: #ffffff;
  --surface-soft: #f9fbff;
  --text: #1d1d1f;
  --muted: #6e6e73;
  --blue: #007aff;
  --blue-soft: rgba(0, 122, 255, 0.12);
  --line: rgba(60, 60, 67, 0.13);
  --glass-line: rgba(60, 60, 67, 0.13);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  color: var(--text);
  background: var(--page);
}

button,
a {
  font: inherit;
}

.review-page {
  width: 100%;
  min-height: 100vh;
  margin: 0 auto;
  padding: 0 0 52px;
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", "Microsoft YaHei", sans-serif;
  letter-spacing: 0;
}

.glass {
  border: 1px solid var(--glass-line);
  background: var(--surface);
  box-shadow: 0 14px 36px rgba(15, 23, 42, 0.06);
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr) 180px;
  align-items: center;
  min-height: 76px;
  padding: 12px 24px;
  border-width: 0 0 1px;
  border-radius: 0;
}

.icon-button {
  width: fit-content;
  min-width: 54px;
  height: 44px;
  display: grid;
  place-items: center;
  padding: 0 22px;
  border: 0;
  border-radius: 10px;
  color: #3a3a3c;
  background: #f3f7ff;
  text-decoration: none;
  cursor: pointer;
  box-shadow: none;
}

.icon-button span {
  font-size: 15px;
  font-weight: 760;
  line-height: 1;
}

.icon-button:hover,
.icon-button:focus-visible {
  color: var(--blue);
  background: #eaf3ff;
  outline: none;
}

.report-brand {
  min-width: 0;
  text-align: center;
}

.report-brand strong {
  display: block;
  color: var(--text);
  font-size: 20px;
  font-weight: 820;
}

.report-brand span {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  color: var(--muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
  width: min(1440px, calc(100vw - 32px));
  margin: 18px auto 0;
}

.side-nav {
  position: sticky;
  top: 94px;
  padding: 18px;
  border-radius: 12px;
}

.side-nav > p {
  margin: 0 0 14px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: .08em;
}

.view-tabs {
  display: grid;
  gap: 8px;
}

.view-tabs button {
  width: 100%;
  min-height: 58px;
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid transparent;
  border-radius: 12px;
  color: var(--muted);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.view-tabs button:hover,
.view-tabs button:focus-visible {
  color: var(--text);
  background: #f3f7ff;
  outline: none;
}

.view-tabs button.active {
  border-color: rgba(0, 122, 255, 0.22);
  color: var(--blue);
  background: #eaf3ff;
  box-shadow: none;
}

.view-tabs b {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 12px;
  color: var(--blue);
  background: #f3f7ff;
  font-size: 14px;
}

.view-tabs span {
  min-width: 0;
  font-size: 16px;
  font-weight: 700;
}

.content {
  min-width: 0;
}

.billing-note {
  margin-bottom: 12px;
  padding: 10px 14px;
  border-radius: 10px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.5;
}

.report-view {
  min-height: calc(100vh - 116px);
  padding: clamp(28px, 3vw, 44px);
  border-radius: 12px;
}

.view-heading {
  padding-bottom: 20px;
  border-bottom: 0;
}

.view-heading > span,
.subheading > span {
  color: var(--blue);
  font-size: 13px;
  font-weight: 800;
  letter-spacing: .08em;
}

.view-heading h1 {
  margin: 10px 0 0;
  font-size: clamp(32px, 3.6vw, 52px);
  font-weight: 820;
  line-height: 1.08;
}

.verdict {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
  max-width: 980px;
  margin-top: 10px;
  padding: 0 0 28px;
  border-bottom: 1px solid var(--line);
}

.verdict > span {
  display: none;
  color: var(--blue);
  font-size: 13px;
  font-weight: 800;
}

.verdict > p {
  max-width: 920px;
  margin: 0;
  color: var(--muted);
  font-size: clamp(17px, 1.25vw, 21px);
  font-weight: 520;
  line-height: 1.55;
  white-space: pre-wrap;
}

.review-reasons {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 32px;
  overflow: visible;
  border: 0;
  background: transparent;
}

.review-reasons article {
  min-height: 190px;
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 16px;
  padding: 24px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #f9fbff;
  box-shadow: none;
}

.review-reasons article > span,
.action-list article > span {
  color: var(--blue);
  font-size: 12px;
  font-weight: 800;
}

.review-reasons h2 {
  margin: 0;
  font-size: 18px;
}

.review-reasons p,
.action-list p,
.ranking-list p {
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.75;
  white-space: pre-wrap;
}

.next-actions {
  margin-top: 30px;
  padding-top: 26px;
  border-top: 1px solid var(--line);
}

.subheading h2 {
  margin: 6px 0 0;
  font-size: 22px;
}

.action-full-text {
  margin-top: 20px;
  padding: 26px 28px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #f9fbff;
}

.action-full-text p {
  margin: 0;
  color: var(--muted);
  font-size: 16px;
  line-height: 1.9;
  white-space: pre-wrap;
}

.choice-content,
.comparison-grid {
  padding-top: 24px;
}

.comparison-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.comparison-grid.single {
  grid-template-columns: minmax(0, 1fr);
}

.ranking-panel {
  min-width: 0;
  padding: 26px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #f9fbff;
  box-shadow: none;
}

.choice-name {
  padding: 28px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #eaf3ff;
  color: var(--text);
}

.choice-name > span {
  color: var(--blue);
  font-size: 12px;
  font-weight: 800;
}

.choice-name h2 {
  margin: 12px 0 0;
  overflow-wrap: anywhere;
  font-size: clamp(30px, 5vw, 54px);
  line-height: 1.08;
}

.choice-name p {
  max-width: 780px;
  margin: 16px 0 0;
  color: var(--muted);
  line-height: 1.75;
}

.ranking-list {
  margin: 24px 0 0;
  padding: 0;
  list-style: none;
  border-top: 1px solid var(--line);
}

.ranking-list li {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 24px;
  padding: 24px 0;
  border-bottom: 1px solid var(--line);
}

.rank {
  width: 54px;
  height: 54px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 18px;
  color: var(--blue);
  background: var(--blue-soft);
  font-size: 18px;
  font-weight: 800;
}

.ranking-list h3 {
  margin: 2px 0 0;
  font-size: 21px;
}

.unavailable {
  min-height: 260px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 12px;
  color: var(--muted);
  text-align: center;
}

.unavailable span {
  color: var(--blue);
  font-size: 46px;
  line-height: 1;
}

.unavailable p {
  margin: 0;
  font-size: 18px;
}

.theme-section {
  padding-top: 24px;
}

.chain-flow {
  display: flex;
  align-items: stretch;
  margin-top: 24px;
  overflow-x: auto;
  padding-bottom: 8px;
}

.chain-step {
  display: flex;
  flex: 1 0 auto;
  align-items: center;
}

.chain-step article {
  width: clamp(160px, 18vw, 220px);
  min-height: 132px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #f9fbff;
}

.chain-step article.current {
  border-color: rgba(0, 122, 255, .32);
  background: rgba(218, 236, 255, 0.82);
}

.chain-step article > span {
  color: var(--muted);
  font-size: 12px;
}

.chain-step article > strong {
  margin-top: 8px;
  font-size: 18px;
}

.chain-step article > small {
  margin-top: 14px;
  color: var(--blue);
  font-size: 11px;
  font-weight: 800;
}

.flow-arrow {
  width: 44px;
  flex: 0 0 44px;
  color: var(--blue);
  font-size: 23px;
  text-align: center;
}

.flow-arrow.vertical {
  display: none;
}

.profit-flow {
  margin-top: 30px;
  padding-top: 26px;
  border-top: 1px solid var(--line);
}

.profit-flow > p {
  margin: 22px 0 0;
  padding: 24px;
  border-left: 3px solid var(--blue);
  color: #3a3a3c;
  background: #f9fbff;
  font-size: 16px;
  line-height: 1.9;
  white-space: pre-wrap;
  border-radius: 0 12px 12px 0;
}

.trade-logic-content {
  margin-top: 24px;
  padding: clamp(22px, 3vw, 34px);
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #f9fbff;
  box-shadow: none;
}

.trade-logic-content strong {
  display: block;
  margin-bottom: 18px;
  color: var(--blue);
  font-size: 20px;
}

.trade-logic-content p {
  margin: 0;
  color: #3a3a3c;
  font-size: clamp(16px, 1.35vw, 20px);
  line-height: 1.9;
  white-space: pre-wrap;
}

.empty-copy {
  margin: 24px 0 0;
  color: var(--muted);
  line-height: 1.7;
}

.review-reasons > .empty-copy {
  margin: 0;
  padding: 24px;
  background: var(--surface-strong);
}

.review-decision-layout {
  display: grid;
  grid-template-columns: minmax(240px, 0.34fr) minmax(0, 0.66fr);
  gap: 16px;
  margin-top: 24px;
}

.score-panel {
  display: grid;
  gap: 14px;
  align-content: start;
}

.total-score {
  min-height: 170px;
  display: grid;
  align-content: center;
  gap: 10px;
  padding: 24px;
  border: 1px solid rgba(0, 122, 255, 0.16);
  border-radius: 16px;
  color: var(--text);
  background: linear-gradient(180deg, #f7fbff 0%, #eaf3ff 100%);
  box-shadow: none;
}

.total-score span,
.total-score small {
  color: var(--muted);
  font-size: 13px;
  font-weight: 780;
}

.total-score strong {
  font-size: clamp(54px, 5vw, 78px);
  line-height: .9;
}

.score-list {
  display: grid;
  gap: 10px;
}

.score-list article {
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #f9fbff;
  box-shadow: none;
}

.score-list article > div {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: baseline;
}

.score-list span {
  color: var(--muted);
  font-size: 14px;
  font-weight: 760;
}

.score-list strong {
  color: var(--blue);
  font-size: 28px;
  line-height: 1;
}

.score-list strong small {
  margin-left: 2px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 800;
}

.score-list i {
  display: block;
  height: 8px;
  margin-top: 14px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(60, 60, 67, .12);
}

.score-list b {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #007aff, #63d2ff);
}

.judgment-panel {
  display: grid;
  gap: 14px;
}

.judgment-panel article {
  min-height: 132px;
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 16px;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #f9fbff;
  box-shadow: none;
}

.judgment-panel article > span {
  color: var(--blue);
  font-size: 12px;
  font-weight: 800;
}

.judgment-panel h2 {
  margin: 0;
  font-size: 18px;
}

.judgment-panel p {
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.75;
  white-space: pre-wrap;
}

.state {
  min-height: calc(100vh - 112px);
  display: grid;
  place-items: center;
  align-content: center;
  gap: 10px;
  padding: 32px;
  border-radius: 12px;
  color: var(--muted);
  text-align: center;
}

.state-mark {
  color: var(--blue);
  font-size: 32px;
  font-weight: 800;
}

.state p {
  margin: 0;
}

.state.error strong {
  color: var(--text);
}

.state.error button {
  margin-top: 10px;
  padding: 9px 18px;
  border: 1px solid var(--gold-line);
  border-radius: 10px;
  color: #fff;
  background: var(--blue);
  font-weight: 800;
  cursor: pointer;
}

@media (max-width: 980px) {
  .workspace {
    grid-template-columns: 1fr;
  }

  .side-nav {
    position: sticky;
    top: 88px;
    z-index: 15;
  }

  .side-nav > p {
    display: none;
  }

  .view-tabs {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .view-tabs button {
    grid-template-columns: 28px minmax(0, 1fr);
  }

  .view-tabs b {
    width: 28px;
    height: 28px;
  }

  .report-view,
  .state {
    min-height: calc(100vh - 190px);
  }
}

@media (max-width: 720px) {
  .review-page {
    width: 100%;
    padding: 0 0 28px;
  }

  .topbar {
    top: 0;
    border-width: 0 0 1px;
    grid-template-columns: 110px minmax(0, 1fr) 62px;
    min-height: 74px;
    border-radius: 0;
    padding: 10px;
  }

  .icon-button {
    min-width: 52px;
    height: 44px;
    padding: 0 14px;
  }

  .icon-button span {
    font-size: 14px;
  }

  .report-brand strong {
    font-size: 18px;
  }

  .workspace {
    gap: 10px;
    margin: 10px;
  }

  .side-nav {
    top: 70px;
    padding: 8px;
  }

  .view-tabs button {
    min-height: 44px;
    grid-template-columns: 1fr;
    justify-items: center;
    gap: 0;
    padding: 8px 4px;
    text-align: center;
  }

  .view-tabs b {
    display: none;
  }

  .view-tabs span {
    font-size: 12px;
  }

  .report-view {
    min-height: calc(100vh - 142px);
    padding: 24px 18px 30px;
    border-radius: 12px;
  }

  .view-heading h1 {
    font-size: 36px;
  }

  .verdict {
    grid-template-columns: 1fr;
    gap: 10px;
    padding: 24px 0;
  }

  .verdict > p {
    font-size: 17px;
  }

  .review-reasons,
  .action-list,
  .review-decision-layout,
  .comparison-grid {
    grid-template-columns: 1fr;
  }

  .review-reasons article {
    min-height: 0;
    padding: 20px;
  }

  .action-list article {
    min-height: 0;
  }

  .ranking-list li {
    grid-template-columns: 52px minmax(0, 1fr);
    gap: 16px;
  }

  .rank {
    width: 46px;
    height: 46px;
  }

  .chain-flow {
    display: grid;
    overflow: visible;
  }

  .chain-step {
    display: grid;
    justify-items: stretch;
  }

  .chain-step article {
    width: 100%;
    min-height: 116px;
  }

  .flow-arrow.horizontal {
    display: none;
  }

  .flow-arrow.vertical {
    width: 100%;
    height: 38px;
    display: grid;
    place-items: center;
  }

  .profit-flow > p {
    padding: 18px;
    font-size: 15px;
  }
}
`;
