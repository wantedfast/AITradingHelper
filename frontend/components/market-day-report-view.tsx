"use client";

import { useState, type ReactNode } from "react";
import { ShieldCheck } from "lucide-react";
import {
  Article as PhArticle,
  CaretDown,
  CheckCircle as PhCheckCircle,
  Clock as PhClock,
  Pill,
  ShieldCheck as PhShieldCheck,
  Target as PhTarget,
  XCircle as PhXCircle,
} from "@phosphor-icons/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ReportPipeContent } from "@/components/report-pipe-table";
import { MobileReportDisclosure } from "@/components/mobile-report-disclosure";
import { containsMarkdownPipeTable } from "@/lib/markdown-pipe-table";
import { evidenceReportText, namedReportText, watchPointReportText, type LabeledReportText } from "@/lib/market-day-report-content";

export type MarketDayEnvelope = {
  run_id?: string;
  market_date?: string;
  report?: MarketDayReport;
};

export type MarketDayReport = {
  schema_version?: number;
  beginner_decision?: BeginnerDecision | null;
  marketDate?: string;
  oneLineConclusion?: string;
  summary?: string;
  markdown?: string;
  sources?: Array<string | Record<string, unknown>>;
  evidence_table?: Array<Record<string, unknown>>;
  institutional_research?: Array<Record<string, unknown>>;
  informationCutoff?: string;
  indices?: Array<Record<string, unknown>>;
  marketStage?: {
    label?: string;
    reason?: string;
    confidence?: number;
  };
  marketBreadth?: {
    summary?: string;
    largeVsSmall?: string;
    weightVsTheme?: string;
    upCount?: string;
    downCount?: string;
    flatCount?: string;
  };
  marketMood?: {
    summary?: string;
    limitUpCount?: string;
    limitDownCount?: string;
    brokenBoardCount?: string;
    brokenBoardRate?: string;
    heightBoard?: string;
    boardStructure?: string;
    highPositionFeedback?: string;
    turnover?: string;
    moneyMakingEffect?: string;
    lossEffect?: string;
    score?: number;
    scoreReason?: string;
  };
  previousDayComparison?: {
    previousMainline?: string;
    continuity?: string;
    previousCoreFeedback?: string;
    marketStageChange?: string;
    keyChanges?: string[];
    confidence?: number;
  };
  mainline?: {
    name?: string;
    reason?: string;
    branches?: string[];
    evidence?: EvidenceItem[];
    score?: number;
    confidence?: number;
    isClearMainline?: boolean;
    riskOrDivergence?: string;
    scoreReason?: string;
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
  secondaryLines?: Array<{ name?: string; reason?: string }>;
  rotationLines?: Array<{ name?: string; reason?: string; evidence?: EvidenceItem[] }>;
  fakeOrWeakLines?: Array<{ name?: string; reason?: string }>;
  watchPoints?: Array<string | WatchPoint>;
  keyRisks?: EvidenceItem[];
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

type BeginnerFocus = {
  name: string;
  reason?: string;
  condition?: string;
};

type BeginnerCondition = {
  time?: string;
  observation: string;
  action: string;
};

type BeginnerTimelineItem = {
  time: "09:25" | "09:35" | "10:30";
  observation: string;
  action: string;
  if_unmet: string;
};

type BeginnerDecision = {
  stance: "observe" | "cautious" | "stand_aside";
  headline: string;
  what_changed: string[];
  primary_focus: BeginnerFocus | null;
  continue_conditions: BeginnerCondition[];
  stop_conditions: BeginnerCondition[];
  timeline: BeginnerTimelineItem[];
  backup_focus: BeginnerFocus | null;
  avoid_actions: string[];
  term_explanations: Array<{ term: string; plain: string }>;
};

export function hasBeginnerMarketDayDashboard(report?: MarketDayReport | null) {
  return Boolean(report?.beginner_decision);
}

export function MarketDayReportView({
  envelope,
  billingMessage = "",
}: {
  envelope: MarketDayEnvelope;
  billingMessage?: string;
}) {
  const report = envelope.report;
  if (!report) return null;
  if (hasBeginnerMarketDayDashboard(report)) {
    return <BeginnerMarketDayReport report={report as MarketDayReport & { beginner_decision: BeginnerDecision }} billingMessage={billingMessage} />;
  }

  const strongestStocks = report.strongestStocks || [];

  return (
    <div className="dated-report-content" id="market-day-inline-report">
      <section className="review-workbench-hero market-day-report-hero">
        <div className="review-hero-copy">
          <p className="review-kicker">MARKET JUDGE RESULT</p>
          <TableAwareHeading value={report.oneLineConclusion || "AI 当日行情复盘"} level={1} />
          <TableAwareText value={report.mainline?.reason || "系统已完成当日行情主线判断。"} />
          {billingMessage ? <div className="market-day-billing-note">{billingMessage}</div> : null}
        </div>
        <div className="market-day-score-board">
          <div><span>最强主线</span><b>{report.mainline?.name || "-"}</b></div>
          <div><span>主线强度</span><b>{formatScore(report.mainline?.score)}</b></div>
          <div><span>市场情绪</span><b>{formatScore(report.marketMood?.score)}</b></div>
        </div>
      </section>

      <section className="research-panel market-day-mood-panel">
        <span className="card-label">市场情绪</span>
        <TableAwareHeading value={report.marketMood?.summary || "市场情绪证据不足"} level={2} />
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
        <TableAwareText value={report.mainline?.reason || "暂无主线判断。"} />
        <div className="market-day-chip-row">
          {(report.mainline?.branches || []).map((branch) => <span key={branch}>{branch}</span>)}
        </div>
        <EvidenceList items={report.mainline?.evidence} />
      </section>

      <section className="research-panel market-day-strong-panel">
        <div className="recent-report-head">
          <div><span className="card-label">主线内最强势个股</span><h2>强弱排名</h2></div>
        </div>
        <div className="market-day-strong-list">
          {strongestStocks.length ? strongestStocks.map((stock) => (
            <article key={`${stock.rank}-${stock.name}`}>
              <div className="market-day-stock-rank">#{stock.rank || "-"}</div>
              <div>
                <h3>{stock.name || "未命名个股"} <small>{stock.code || ""}</small></h3>
                <TableAwareText value={stock.strengthReason || "强势原因证据不足。"} />
                <div className="market-day-chip-row">
                  <span>{stock.leaderType || "证据不足"}</span>
                  <span>{stock.theme || "主线待确认"}</span>
                  <span>{formatScore(stock.score)}</span>
                </div>
                <EvidenceList items={stock.evidence} />
                {stock.riskOrDivergence ? <TableAwareText value={stock.riskOrDivergence} emphasis /> : null}
              </div>
            </article>
          )) : <p className="market-day-empty-text">暂无强势个股数据。</p>}
        </div>
      </section>

      <MobileReportDisclosure title="次主线与弱方向" summary="更多市场背景，点击展开">
      <section className="review-workbench-grid">
        <section className="research-panel">
          <span className="card-label">次主线</span>
          <NamedLineList items={report.secondaryLines} />
        </section>
        <section className="research-panel">
          <span className="card-label">伪主线 / 弱方向</span>
          <NamedLineList items={report.fakeOrWeakLines} />
        </section>
      </section>
      </MobileReportDisclosure>

      <MobileReportDisclosure title="复盘观察与证据" summary="详细观察点和来源提醒">
      <section className="research-panel market-day-audit-panel">
        <span className="card-label">复盘观察</span>
        <LineList items={report.watchPoints} icon />
        <div className="market-day-audit-grid">
          <article><b>证据不足</b><LineList items={report.audit?.missingEvidence} /></article>
          <article><b>来源提醒</b><LineList items={report.audit?.sourceWarnings} /></article>
        </div>
      </section>
      </MobileReportDisclosure>
    </div>
  );
}

function BeginnerMarketDayReport({
  report,
  billingMessage,
}: {
  report: MarketDayReport & { beginner_decision: BeginnerDecision };
  billingMessage?: string;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const decision = report.beginner_decision;
  const strongestStocks = report.strongestStocks || [];
  const guidance = decision.timeline[0] || decision.timeline[1];
  const stanceLabels = {
    observe: "可以观察",
    cautious: "谨慎观察",
    stand_aside: "先不参与",
  } as const;

  return (
    <div className="dated-report-content ai-beginner-dashboard ai-beginner-market-day" id="market-day-inline-report">
      {billingMessage ? <div className="market-day-billing-note">{billingMessage}</div> : null}
      <section className="ai-beginner-prototype" aria-labelledby="tomorrow-title">
        <section className="hero">
          <div className="hero-icon"><PhTarget size={38} weight="duotone" /></div>
          <div className="hero-copy">
            <p className="status">明日观察态度 · {stanceLabels[decision.stance]}</p>
            <h2 id="tomorrow-title">{decision.headline || report.oneLineConclusion || "明天先观察，不急着行动"}</h2>
            <p className="focus">明天只观察：<strong>{decision.primary_focus?.name || "明天暂不行动"}</strong></p>
            <p className="focus-reason">{decision.primary_focus?.reason || "今天没有足够证据支持明天预设一个观察方向。"}</p>
          </div>
          {guidance ? <p className="hero-guidance"><PhClock size={20} weight="duotone" />下个交易日 {guidance.time}：{stripTrailingPunctuation(guidance.action)}。若不满足，{guidance.if_unmet}</p> : null}
        </section>

        <section className="avoid-actions market-day-beginner-changes">
          <div className="section-heading"><PhArticle size={23} weight="duotone" /><h3>今天发生了什么 / 相比昨天</h3></div>
          <ul>{decision.what_changed.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>

        <section className="decision-grid" aria-label="明日判断条件">
          <article className="decision-panel positive">
            <div className="panel-title"><PhCheckCircle size={34} weight="duotone" /><div><span>满足全部条件</span><h3>继续观察</h3></div></div>
            <div className="condition-list">
              {decision.continue_conditions.length ? decision.continue_conditions.map((item) => (
                <div className="condition" key={`${item.time}-${item.observation}`}>
                  <span>{item.time}</span>
                  <div><p>{item.observation}</p><small>{item.action}</small></div>
                </div>
              )) : <p className="market-day-empty-text">没有继续观察条件时，默认明天暂不行动。</p>}
            </div>
            <p className="panel-outcome"><PhCheckCircle size={19} weight="fill" />可以继续观察，但仍不是推荐。</p>
          </article>

          <article className="decision-panel negative">
            <div className="panel-title"><PhXCircle size={34} weight="duotone" /><div><span>出现任意一条</span><h3>立即停止</h3></div></div>
            <div className="condition-list">
              {decision.stop_conditions.map((item) => (
                <div className="condition" key={`${item.time}-${item.observation}`}>
                  <span>{item.time}</span>
                  <div><p>{item.observation}</p><small>{item.action}</small></div>
                </div>
              ))}
            </div>
            <p className="panel-outcome"><PhXCircle size={19} weight="fill" />明天暂不行动</p>
          </article>
        </section>

        <section className="action-flow">
          <div className="section-heading"><PhClock size={23} weight="duotone" /><h3>明天开盘后怎么观察</h3></div>
          <ol>{decision.timeline.map((item) => <li key={item.time}><span>{item.time}</span><strong>{item.action}</strong><small>看：{item.observation}</small><em>不满足：{item.if_unmet}</em></li>)}</ol>
        </section>

        <section className="backup">
          <div><Pill size={25} weight="duotone" /><span>备用观察方向</span><strong>{decision.backup_focus?.name || "明天先不切换方向"}</strong></div>
          <p>{decision.backup_focus?.condition || "如果主方向条件不满足，就直接停手，不临时找新题材。"}</p>
        </section>

        <section className="avoid-actions">
          <div className="section-heading"><PhShieldCheck size={23} weight="duotone" /><h3>明天最需要避开</h3></div>
          <ul>{decision.avoid_actions.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>

        <section className={`research-details ${detailsOpen ? "open" : ""}`}>
          <button type="button" aria-expanded={detailsOpen} onClick={() => setDetailsOpen((value) => !value)}>
            <span><PhArticle size={22} weight="duotone" />研究依据与术语解释</span>
            <span className="details-hint">给想进一步了解的人<CaretDown size={20} /></span>
          </button>
          {detailsOpen ? <div className="details-body">
            <div className="research-stats">
              <span><b>{report.marketStage?.label || scoreToLabel(report.marketMood?.score, "中性")}</b>市场强弱</span>
              <span><b>{report.previousDayComparison?.continuity || (report.mainline?.isClearMainline ? "可跟踪" : "待确认")}</b>持续性</span>
              <span><b>{scoreToLabel(report.mainline?.confidence ?? report.marketStage?.confidence ?? report.previousDayComparison?.confidence ?? report.marketMood?.score, "待核实")}</b>证据把握</span>
            </div>

            <div className="evidence">
              <h4>今天发生了什么</h4>
              <p>{report.oneLineConclusion || report.marketMood?.summary || "今天的市场信息已整理完成。"}</p>
            </div>
            <div className="evidence">
              <h4>市场强弱依据</h4>
              <p>{report.marketStage?.reason || report.marketMood?.summary || "市场强弱证据仍在补充。"}</p>
            </div>
            <div className="evidence">
              <h4>持续性依据</h4>
              <p>{report.previousDayComparison?.previousCoreFeedback || report.mainline?.riskOrDivergence || "主线持续性还需要下个交易日继续验证。"}</p>
            </div>
            <div className="evidence">
              <h4>证据把握说明</h4>
              <p>{report.marketMood?.scoreReason || report.mainline?.scoreReason || "当前结论依赖公开可核验信息，仍要以明天盘中验证为准。"}</p>
            </div>

            <div className="glossary">
              {decision.term_explanations.map((item) => <div key={item.term}><h4>{item.term}</h4><p>{item.plain}</p></div>)}
            </div>

            <details className="professional-report">
              <summary>展开完整专业复盘</summary>
              <article className="markdown-report">
                <ProfessionalSection title="指数与市场强弱">
                  {report.indices?.length ? <RecordLineList items={report.indices} /> : null}
                  {report.informationCutoff ? <LineList items={[`信息截点：${report.informationCutoff}`]} /> : null}
                  <RecordLineList items={[compactRecord(report.marketStage), compactRecord(report.marketBreadth), compactRecord(report.marketMood)]} />
                </ProfessionalSection>

                <ProfessionalSection title="上一交易日对比">
                  <RecordLineList items={[compactRecord(report.previousDayComparison)]} />
                  {report.previousDayComparison?.keyChanges?.length ? <LineList items={report.previousDayComparison.keyChanges} /> : null}
                </ProfessionalSection>

                <ProfessionalSection title="主线与轮动">
                  <p className="market-day-professional-summary"><strong>{report.mainline?.name || "没有明确单一主线"}</strong></p>
                  <TableAwareText value={report.mainline?.reason || report.marketBreadth?.summary || "专业主线判断证据仍在补充。"} />
                  <div className="market-day-chip-row">
                    {(report.mainline?.branches || []).map((branch) => <span key={branch}>{branch}</span>)}
                  </div>
                  <EvidenceList items={report.mainline?.evidence} />
                  {report.mainline?.riskOrDivergence ? <TableAwareText value={report.mainline.riskOrDivergence} emphasis /> : null}
                  {report.rotationLines?.length ? <NamedLineList items={report.rotationLines.map((item) => ({ name: item.name, reason: item.reason }))} /> : null}
                  {report.secondaryLines?.length ? <NamedLineList items={report.secondaryLines} /> : null}
                  {report.fakeOrWeakLines?.length ? <NamedLineList items={report.fakeOrWeakLines} /> : null}
                </ProfessionalSection>

                {strongestStocks.length ? (
                  <ProfessionalSection title="市场热度样本（不是推荐）">
                    <div className="market-day-strong-list market-day-strong-list--samples">
                      {strongestStocks.map((stock) => (
                        <article key={`${stock.name}-${stock.code}`}>
                          <div>
                            <h3>{stock.name || "未命名个股"} <small>{stock.code || ""}</small></h3>
                            <TableAwareText value={stock.strengthReason || "热度样本原因证据不足。"} />
                            <div className="market-day-chip-row">
                              <span>{stock.leaderType || "热度样本"}</span>
                              <span>{stock.theme || "方向待确认"}</span>
                            </div>
                            <EvidenceList items={stock.evidence} />
                            {stock.riskOrDivergence ? <TableAwareText value={stock.riskOrDivergence} emphasis /> : null}
                          </div>
                        </article>
                      ))}
                    </div>
                  </ProfessionalSection>
                ) : null}

                <ProfessionalSection title="证据与机构研究">
                  {report.evidence_table?.length ? <RecordLineList items={report.evidence_table} /> : null}
                  {report.institutional_research?.length ? <RecordLineList items={report.institutional_research} /> : null}
                </ProfessionalSection>

                <ProfessionalSection title="观察点、风险与审计">
                  {report.watchPoints?.length ? <LineList items={report.watchPoints} icon /> : null}
                  {report.keyRisks?.length ? <EvidenceList items={report.keyRisks} /> : null}
                  {report.audit?.missingEvidence?.length ? <LineList items={report.audit.missingEvidence} /> : null}
                  {report.audit?.sourceWarnings?.length ? <LineList items={report.audit.sourceWarnings} /> : null}
                </ProfessionalSection>

                {report.markdown ? (
                  <ProfessionalSection title="完整专业复盘正文">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        a: ({ children, ...props }) => <a {...props} target="_blank" rel="noreferrer">{children}</a>,
                        table: ({ children, ...props }) => <div className="markdown-table-scroll"><table {...props}>{children}</table></div>,
                      }}
                    >
                      {report.markdown}
                    </ReactMarkdown>
                  </ProfessionalSection>
                ) : null}

                {report.sources?.length ? (
                  <ProfessionalSection title="公开来源">
                    <LineList items={report.sources.map(formatSource)} />
                  </ProfessionalSection>
                ) : null}
              </article>
            </details>
          </div> : null}
        </section>

        <footer><PhShieldCheck size={20} weight="duotone" /><strong>不是买点提示，不推荐具体股票。</strong><span>条件不满足时，明天不行动就是正确决定。</span></footer>
      </section>
    </div>
  );
}

function ProfessionalSection({ title, children }: { title: string; children: ReactNode }) {
  if (!children) return null;
  return <section className="market-day-professional-section"><h2>{title}</h2>{children}</section>;
}

function Metric({ label, value }: { label: string; value?: string }) {
  return <div><span>{label}</span><b>{value || "-"}</b></div>;
}

function EvidenceList({ items }: { items?: EvidenceItem[] }) {
  const entries = (items || []).map(evidenceReportText).filter((parts) => parts.length).slice(0, 6);
  if (!entries.length) return null;
  return <ul className="market-day-evidence-list">{entries.map((parts, index) => <li key={index}><div className="report-labeled-text"><LabeledTextParts parts={parts} /></div></li>)}</ul>;
}

function LineList({ items, icon = false }: { items?: unknown[]; icon?: boolean }) {
  const entries = (items || []).map(watchPointReportText).filter((parts) => parts.length);
  if (!entries.length) return <p className="market-day-empty-text">暂无明确证据。</p>;
  return (
    <ul className="market-day-line-list">
      {entries.map((parts, index) => <li key={index}>{icon ? <ShieldCheck /> : null}<div className="report-labeled-text"><LabeledTextParts parts={parts} /></div></li>)}
    </ul>
  );
}

function NamedLineList({ items }: { items?: Array<{ name?: string; reason?: string }> }) {
  const entries = (items || []).map((item) => namedReportText(item.name, item.reason));
  if (!entries.length) return <p className="market-day-empty-text">暂无明确证据。</p>;
  return <ul className="market-day-line-list">{entries.map((parts, index) => <li key={index}><div className="report-labeled-text"><LabeledTextParts parts={parts} /></div></li>)}</ul>;
}

function RecordLineList({ items }: { items?: Array<Record<string, unknown> | null | undefined> }) {
  const entries = (items || []).map((item) => normalizeRecordParts(item)).filter((parts) => parts.length);
  if (!entries.length) return null;
  return <ul className="market-day-line-list">{entries.map((parts, index) => <li key={index}><div className="report-labeled-text"><LabeledTextParts parts={parts} /></div></li>)}</ul>;
}

function normalizeRecordParts(item: Record<string, unknown> | null | undefined) {
  if (!item) return [];
  return Object.entries(item)
    .flatMap(([key, value]) => {
      const text = stringifyValue(value);
      if (!text) return [];
      return [{ label: keyLabel(key), value: text }] as LabeledReportText[];
    });
}

function compactRecord<T extends Record<string, unknown> | undefined>(item: T) {
  if (!item) return undefined;
  return Object.fromEntries(Object.entries(item).filter(([, value]) => stringifyValue(value)));
}

function stringifyValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    return value.map((item) => stringifyValue(item)).filter(Boolean).join(" | ");
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => {
        const text = stringifyValue(item);
        return text ? `${keyLabel(key)}：${text}` : "";
      })
      .filter(Boolean)
      .join("；");
  }
  return "";
}

function keyLabel(key: string) {
  const labels: Record<string, string> = {
    name: "名称",
    code: "代码",
    close: "收盘",
    changePct: "涨跌幅",
    label: "标签",
    reason: "原因",
    confidence: "置信度",
    summary: "摘要",
    largeVsSmall: "大盘与小盘",
    weightVsTheme: "权重与题材",
    upCount: "上涨家数",
    downCount: "下跌家数",
    flatCount: "平盘家数",
    limitUpCount: "涨停家数",
    limitDownCount: "跌停家数",
    brokenBoardCount: "炸板家数",
    brokenBoardRate: "炸板率",
    heightBoard: "连板高度",
    boardStructure: "连板结构",
    highPositionFeedback: "高位反馈",
    turnover: "成交额",
    moneyMakingEffect: "赚钱效应",
    lossEffect: "亏钱效应",
    previousMainline: "上一交易日主线",
    continuity: "延续性",
    previousCoreFeedback: "上一交易日核心反馈",
    marketStageChange: "阶段变化",
    keyChanges: "关键变化",
    title: "标题",
    publisher: "发布机构",
    institution: "机构",
    industry: "行业",
    conclusion: "结论",
    impact: "影响",
    published_at: "发布时间",
    publishedAt: "发布时间",
    accessedAt: "抓取时间",
    retrieved_at: "抓取时间",
    sourceType: "来源类型",
    supports: "支持事实",
    event: "事件",
    evidence: "证据",
    source_summary: "来源摘要",
    a_share_mapping: "A股映射",
    sourceIds: "来源编号",
    evidenceSourceIds: "来源编号",
    type: "类型",
    content: "内容",
    url: "链接",
    time: "时间",
  };
  return labels[key] || key;
}

function LabeledTextParts({ parts }: { parts: LabeledReportText[] }) {
  return (
    <>
      {parts.map((part, index) => containsMarkdownPipeTable(part.value) ? (
        <div className="report-labeled-text-part report-labeled-text-part--table" key={`${part.label}-${index}`}>
          {index > 0 ? <span className="report-labeled-text-separator">；</span> : null}
          {part.label ? <b>{part.label}</b> : null}
          <TableAwareText value={part.value} inline />
        </div>
      ) : (
        <span className="report-labeled-text-part" key={`${part.label}-${index}`}>
          {index > 0 ? <span className="report-labeled-text-separator">；</span> : null}
          {part.label ? <b>{part.label}</b> : null}
          {part.value}
        </span>
      ))}
    </>
  );
}

function formatScore(value?: number) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return `${Math.round(value * 10) / 10}/10`;
}

function scoreToLabel(value: number | undefined, fallback: string) {
  if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
  if (value >= 8) return "偏强";
  if (value >= 6) return "中等";
  if (value >= 4) return "偏弱";
  return "较弱";
}

function stripTrailingPunctuation(value: string) {
  return value.replace(/[。！？!?；;，,]+$/, "");
}

function TableAwareHeading({ value, level }: { value: string; level: 1 | 2 }) {
  if (containsMarkdownPipeTable(value)) return <div className="report-table-aware-heading"><ReportPipeContent value={value} /></div>;
  return level === 1 ? <h1>{value}</h1> : <h2>{value}</h2>;
}

function TableAwareText({ value, inline = false, emphasis = false }: { value: string; inline?: boolean; emphasis?: boolean }) {
  if (!containsMarkdownPipeTable(value)) {
    if (emphasis) return <em>{value}</em>;
    return inline ? <>{value}</> : <p>{value}</p>;
  }
  return (
    <div className={`report-table-aware-text${emphasis ? " report-table-aware-text--emphasis" : ""}`}>
      <ReportPipeContent
        value={value}
        renderText={(lines, index) => <p key={index}>{lines.filter(Boolean).join("\n")}</p>}
      />
    </div>
  );
}

function formatSource(source: string | Record<string, unknown>) {
  if (typeof source === "string") return source;
  return [
    field(source, "title", "source", "name"),
    field(source, "publisher"),
    field(source, "sourceType"),
    field(source, "time", "published_at", "publishedAt"),
    field(source, "retrieved_at", "accessedAt"),
    field(source, "supports"),
    field(source, "url"),
  ].filter(Boolean).join(" | ");
}

function field(item: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const value = item[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number") return String(value);
  }
  return "";
}
