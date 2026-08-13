import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowClockwise,
  Article,
  CalendarBlank,
  CaretDown,
  ChartBar,
  CheckCircle,
  Clock,
  FileText,
  Info,
  Pill,
  ShieldCheck,
  Target,
  TrendUp,
  Trophy,
  XCircle,
} from "@phosphor-icons/react";

const navItems = [
  [Trophy, "每日 TOP5"],
  [Article, "AI 复盘"],
  [ChartBar, "AI 盯盘"],
  [TrendUp, "AI 当日行情"],
  [FileText, "AI 研报"],
];

const reportUrl = "/data/2026-08-13-v2.json";

const stanceLabels = {
  observe: "可以观察",
  cautious: "谨慎观察",
  stand_aside: "暂不参与",
};

export function App() {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [refreshed, setRefreshed] = useState(false);
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");

  async function loadReport() {
    setRefreshed(true);
    setError("");
    try {
      const response = await fetch(`${reportUrl}?t=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setReport(await response.json());
    } catch (loadError) {
      setError(`读取 8 月 13 日实际研报失败：${loadError.message}`);
    } finally {
      window.setTimeout(() => setRefreshed(false), 500);
    }
  }

  useEffect(() => { void loadReport(); }, []);

  if (!report) {
    return <main className="loading-screen"><b>{error || "正在读取 2026-08-13 实际研报…"}</b></main>;
  }

  const decision = report.beginner_decision;

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="产品导航">
        <div className="brand" aria-label="盈航 AI Trading">
          <span className="brand-mark">盈</span>
          <span><b>盈航</b><small>AI TRADING</small></span>
        </div>

        <nav>
          {navItems.map(([Icon, label]) => (
            <button className={`nav-item ${label === "AI 研报" ? "active" : ""}`} key={label}>
              <Icon size={22} weight="duotone" aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <div className="daily-tip">
          <Info size={22} weight="duotone" aria-hidden="true" />
          <div><b>每日提示</b><p>每天 08:30 汇总重要消息，帮助你先看懂市场，再决定是否参与。</p></div>
        </div>
      </aside>

      <main className="content">
        <header className="page-header">
          <div>
            <p className="eyebrow">DAILY RESEARCH · BEGINNER VIEW</p>
            <h1>AI 研报 <span>· 30秒判断</span></h1>
          </div>
          <div className="header-actions">
            <div className="date"><CalendarBlank size={20} />{report.research_date}</div>
            <button className="refresh" onClick={loadReport} disabled={refreshed}>
              <ArrowClockwise size={20} className={refreshed ? "spin" : ""} />
              {refreshed ? "已刷新" : "刷新研报"}
            </button>
          </div>
        </header>

        <section className="hero" aria-labelledby="today-title">
          <div className="hero-icon"><Target size={38} weight="duotone" /></div>
          <div className="hero-copy">
            <p className="status">今日态度 · {stanceLabels[decision.stance]}</p>
            <h2 id="today-title">{decision.headline}</h2>
            <p className="focus">今天只看：<strong>{decision.primary_focus?.name || "没有明确方向"}</strong></p>
            <p className="focus-reason">{decision.primary_focus?.reason || "证据不足，今天先不参与。"}</p>
          </div>
          <p className="hero-guidance"><Clock size={20} weight="duotone" />{decision.timeline[1].action} {decision.timeline[1].if_unmet}</p>
        </section>

        <section className="decision-grid" aria-label="今日判断条件">
          <article className="decision-panel positive">
            <div className="panel-title"><CheckCircle size={34} weight="duotone" /><div><span>满足全部条件</span><h3>继续观察</h3></div></div>
            <div className="condition-list">
              {decision.continue_conditions.map((item) => <div className="condition" key={`${item.time}-${item.observation}`}><span>{item.time}</span><div><p>{item.observation}</p><small>{item.action}</small></div></div>)}
            </div>
            <p className="panel-outcome"><CheckCircle size={19} weight="fill" />可以继续看，但仍不是买入提示</p>
          </article>

          <article className="decision-panel negative">
            <div className="panel-title"><XCircle size={34} weight="duotone" /><div><span>出现任意一种</span><h3>立即放弃</h3></div></div>
            <div className="condition-list">
              {decision.stop_conditions.map((item) => <div className="condition" key={`${item.time}-${item.observation}`}><span>{item.time}</span><div><p>{item.observation}</p><small>{item.action}</small></div></div>)}
            </div>
            <p className="panel-outcome"><XCircle size={19} weight="fill" />今天不操作</p>
          </article>
        </section>

        <section className="action-flow">
          <div className="section-heading"><Clock size={23} weight="duotone" /><h3>我该怎么做</h3></div>
          <ol>{decision.timeline.map((item) => <li key={item.time}><span>{item.time}</span><strong>{item.action}</strong><small>看：{item.observation}</small><em>不满足：{item.if_unmet}</em></li>)}</ol>
        </section>

        <section className="backup">
          <div><Pill size={25} weight="duotone" /><span>备选方向</span><strong>{decision.backup_focus?.name || "今天不设备选方向"}</strong></div>
          <p>{decision.backup_focus?.condition || "不临时找题材凑数。"}</p>
        </section>

        <section className="avoid-actions">
          <div className="section-heading"><ShieldCheck size={23} weight="duotone" /><h3>今天最需要避免</h3></div>
          <ul>{decision.avoid_actions.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>

        <section className={`research-details ${detailsOpen ? "open" : ""}`}>
          <button aria-expanded={detailsOpen} onClick={() => setDetailsOpen(value => !value)}>
            <span><Article size={22} weight="duotone" />研究依据与术语解释</span>
            <span className="details-hint">给想深入了解的人<CaretDown size={20} /></span>
          </button>
          {detailsOpen && <div className="details-body">
            <div className="research-stats"><span><b>{report.sources.length}</b> 个公开来源</span><span><b>{report.evidence_table.length}</b> 条证据</span><span><b>{report.institutional_research.length}</b> 条机构研究</span></div>
            <div className="evidence"><h4>当天专业摘要</h4><p>{report.summary}</p></div>
            <div className="glossary">
              {decision.term_explanations.map((item) => <div key={item.term}><h4>{item.term}</h4><p>{item.plain}</p></div>)}
            </div>
            <details className="professional-report">
              <summary>展开完整专业研报</summary>
              <article className="markdown-report">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    a: ({ children, ...props }) => <a {...props} target="_blank" rel="noreferrer">{children}</a>,
                    table: ({ children, ...props }) => <div className="markdown-table-scroll"><table {...props}>{children}</table></div>,
                  }}
                >
                  {report.markdown}
                </ReactMarkdown>
              </article>
            </details>
          </div>}
        </section>

        <footer><ShieldCheck size={20} weight="duotone" /><strong>不是买点提示，不推荐具体股票。</strong><span>条件不满足时，今天不操作就是正确决定。</span></footer>
      </main>
    </div>
  );
}
