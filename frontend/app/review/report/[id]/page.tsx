"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

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

type ReviewReportPageProps = {
  params: { id: string };
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8600";

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

function scoreCopy(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? `${value}` : "--";
}

export default function ReviewReportPage({ params }: ReviewReportPageProps) {
  const reportId = decodeURIComponent(params.id);
  const presenterUrl = `${API_BASE}/api/reports/${encodeURIComponent(reportId)}/research_presenter_data.json`;
  const [activeView, setActiveView] = useState<ViewKey>("review");
  const [presenter, setPresenter] = useState<Presenter | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

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
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Presenter 加载失败");
    } finally {
      setLoading(false);
    }
  }, [presenterUrl]);

  useEffect(() => {
    void loadPresenter();
  }, [loadPresenter]);

  const reviewItems = presenter?.review?.items?.slice(0, 4) || [];
  const reviewScores = presenter?.review?.scores?.items || [];
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
          <strong>Final WANG Agent</strong>
          <span>{reportId}</span>
        </div>
        <button className="icon-button" type="button" onClick={() => void loadPresenter()} aria-label="刷新报告" title="刷新报告">
          <span aria-hidden="true">↻</span>
        </button>
      </header>

      <div className="workspace">
        <aside className="side-nav glass" aria-label="报告视图">
          <p>REPORT MAP</p>
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
                    <strong>{scoreCopy(reviewScores.find((item) => item.key === "total")?.value)}</strong>
                    <small>来自原始报告</small>
                  </div>

                  <div className="score-list">
                    {reviewScores.filter((item) => item.key !== "total").length > 0 ? (
                      reviewScores.filter((item) => item.key !== "total").map((item) => (
                        <article key={item.key || item.label}>
                          <div>
                            <span>{copy(item.label)}</span>
                            <strong>{scoreCopy(item.value)}</strong>
                          </div>
                          <i><b style={{ width: `${Math.max(0, Math.min(100, Number(item.value) || 0))}%` }} /></i>
                        </article>
                      ))
                    ) : (
                      <p className="empty-copy">原始报告未提供评分</p>
                    )}
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
  --page: #f5f9ff;
  --surface: rgba(255, 255, 255, 0.72);
  --surface-strong: rgba(255, 255, 255, 0.64);
  --surface-soft: rgba(255, 255, 255, 0.46);
  --text: #1d1d1f;
  --muted: #6e6e73;
  --blue: #007aff;
  --blue-soft: rgba(0, 122, 255, 0.12);
  --line: rgba(60, 60, 67, 0.13);
  --glass-line: rgba(255, 255, 255, 0.82);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  color: var(--text);
  background:
    radial-gradient(circle at 11% 18%, rgba(0, 122, 255, 0.2), transparent 34%),
    radial-gradient(circle at 88% 10%, rgba(255, 149, 0, 0.13), transparent 28%),
    linear-gradient(135deg, #edf6ff 0%, #f7fbff 42%, #fffaf3 100%);
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
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.98),
    0 28px 80px rgba(33, 87, 150, 0.14);
  backdrop-filter: blur(30px) saturate(1.45);
  -webkit-backdrop-filter: blur(30px) saturate(1.45);
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr) 180px;
  align-items: center;
  min-height: 90px;
  padding: 14px 20px;
  border-width: 0 0 1px;
  border-radius: 0 0 28px 28px;
}

.icon-button {
  width: fit-content;
  min-width: 54px;
  height: 56px;
  display: grid;
  place-items: center;
  padding: 0 22px;
  border: 0;
  border-radius: 28px;
  color: #3a3a3c;
  background: rgba(255, 255, 255, 0.58);
  text-decoration: none;
  cursor: pointer;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.95), 0 10px 32px rgba(80, 130, 190, .1);
}

.icon-button span {
  font-size: 18px;
  font-weight: 760;
  line-height: 1;
}

.icon-button:hover,
.icon-button:focus-visible {
  background: rgba(255, 255, 255, 0.86);
  outline: none;
}

.report-brand {
  min-width: 0;
  text-align: center;
}

.report-brand strong {
  display: block;
  color: var(--text);
  font-size: 22px;
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
  grid-template-columns: 310px minmax(0, 1fr);
  gap: 24px;
  align-items: start;
  width: min(1840px, calc(100vw - 32px));
  margin: 28px auto 0;
}

.side-nav {
  position: sticky;
  top: 118px;
  padding: 26px 24px;
  border-radius: 40px;
}

.side-nav > p {
  margin: 0 0 20px;
  color: var(--muted);
  font-size: 16px;
  font-weight: 700;
  letter-spacing: .08em;
}

.view-tabs {
  display: grid;
  gap: 6px;
}

.view-tabs button {
  width: 100%;
  min-height: 78px;
  display: grid;
  grid-template-columns: 54px minmax(0, 1fr);
  gap: 14px;
  align-items: center;
  padding: 14px;
  border: 1px solid transparent;
  border-radius: 28px;
  color: var(--muted);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.view-tabs button:hover,
.view-tabs button:focus-visible {
  color: var(--text);
  background: rgba(255, 255, 255, 0.48);
  outline: none;
}

.view-tabs button.active {
  border-color: rgba(255, 255, 255, 0.9);
  color: var(--blue);
  background: rgba(218, 236, 255, 0.82);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.95);
}

.view-tabs b {
  width: 50px;
  height: 50px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 24px;
  color: var(--blue);
  background: rgba(255, 255, 255, 0.76);
  font-size: 22px;
}

.view-tabs span {
  min-width: 0;
  font-size: 21px;
  font-weight: 700;
}

.content {
  min-width: 0;
}

.report-view {
  min-height: calc(100vh - 146px);
  padding: clamp(40px, 4vw, 64px);
  border-radius: 40px;
}

.view-heading {
  padding-bottom: 24px;
  border-bottom: 0;
}

.view-heading > span,
.subheading > span {
  color: var(--blue);
  font-size: 17px;
  font-weight: 800;
  letter-spacing: .08em;
}

.view-heading h1 {
  margin: 10px 0 0;
  font-size: clamp(72px, 7vw, 124px);
  font-weight: 850;
  line-height: .96;
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
  font-size: clamp(20px, 1.5vw, 26px);
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
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.62);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.9);
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
  margin-top: 42px;
  padding-top: 32px;
  border-top: 1px solid var(--line);
}

.subheading h2 {
  margin: 6px 0 0;
  font-size: 26px;
}

.action-full-text {
  margin-top: 20px;
  padding: 26px 28px;
  border: 1px solid var(--line);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.62);
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
  padding-top: 34px;
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
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.58);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.9);
}

.choice-name {
  padding: 28px;
  border: 1px solid var(--line);
  border-radius: 28px;
  background: linear-gradient(135deg, #1d1d1f, #303036 48%, #007aff);
  color: #fff;
}

.choice-name > span {
  color: rgba(255,255,255,.72);
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
  color: rgba(255,255,255,.76);
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
  min-height: 380px;
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
  padding-top: 34px;
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
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.62);
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
  margin-top: 38px;
  padding-top: 34px;
  border-top: 1px solid var(--line);
}

.profit-flow > p {
  margin: 22px 0 0;
  padding: 24px;
  border-left: 3px solid var(--blue);
  color: #3a3a3c;
  background: rgba(255, 255, 255, 0.62);
  font-size: 16px;
  line-height: 1.9;
  white-space: pre-wrap;
  border-radius: 0 24px 24px 0;
}

.trade-logic-content {
  margin-top: 34px;
  padding: clamp(26px, 4vw, 48px);
  border: 1px solid var(--line);
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.62);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.9);
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
  font-size: clamp(18px, 2vw, 26px);
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
  grid-template-columns: minmax(280px, 0.42fr) minmax(0, 0.58fr);
  gap: 16px;
  margin-top: 32px;
}

.score-panel {
  display: grid;
  gap: 14px;
  align-content: start;
}

.total-score {
  min-height: 230px;
  display: grid;
  align-content: center;
  gap: 10px;
  padding: 30px;
  border-radius: 32px;
  color: #fff;
  background: linear-gradient(145deg, #1d1d1f, #303036 48%, #007aff);
  box-shadow: 0 20px 54px rgba(0, 72, 160, .16);
}

.total-score span,
.total-score small {
  color: rgba(255, 255, 255, .72);
  font-size: 13px;
  font-weight: 780;
}

.total-score strong {
  font-size: clamp(72px, 7vw, 116px);
  line-height: .9;
}

.score-list {
  display: grid;
  gap: 10px;
}

.score-list article {
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.62);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.9);
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
  font-size: 34px;
  line-height: 1;
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
  min-height: 150px;
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 16px;
  padding: 24px;
  border: 1px solid var(--line);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.62);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.9);
}

.judgment-panel article > span {
  color: var(--blue);
  font-size: 12px;
  font-weight: 800;
}

.judgment-panel h2 {
  margin: 0;
  font-size: 20px;
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
  border-radius: 8px;
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
  border-radius: 18px;
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
    border-radius: 0 0 22px 22px;
    padding: 10px;
  }

  .icon-button {
    min-width: 52px;
    height: 52px;
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
    border-radius: 28px;
  }

  .view-heading h1 {
    font-size: 48px;
  }

  .verdict {
    grid-template-columns: 1fr;
    gap: 10px;
    padding: 24px 0;
  }

  .verdict > p {
    font-size: 20px;
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
