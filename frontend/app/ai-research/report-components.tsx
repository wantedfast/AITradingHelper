"use client";

import { useState } from "react";
import { Building2, CalendarDays, CheckCircle2, Clock3, FileText, ListChecks, Target, TrendingUp } from "lucide-react";
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
import { MobileReportDisclosure } from "@/components/mobile-report-disclosure";
import { parseMarkdownPipeTables } from "@/lib/markdown-pipe-table";

export type AiResearchSummary = {
  run_id: string;
  title?: string;
  created_at?: string;
  research_date?: string;
  summary?: string;
  source?: string;
};

export type AiResearchReport = {
  schema_version?: number;
  beginner_decision?: BeginnerDecision | null;
  run_id?: string;
  received_at?: string;
  source?: string;
  research_date?: string;
  title?: string;
  summary?: string;
  markdown?: string;
  sections?: Array<{ title?: string; content?: string; body?: string; summary?: string }>;
  sources?: Array<string | Record<string, unknown>>;
  tags?: string[];
  decision_cards?: Array<Record<string, unknown>>;
  evidence_table?: Array<Record<string, unknown>>;
  watchlist?: Array<Record<string, unknown>>;
  scenario_plan?: Array<Record<string, unknown>>;
  risk_calendar?: Array<Record<string, unknown>>;
  data_gaps?: Array<string | Record<string, unknown>>;
  institutional_research?: Array<Record<string, unknown>>;
};

export type BeginnerFocus = {
  name: string;
  reason?: string;
  condition?: string;
};

export type BeginnerCondition = {
  time?: string;
  observation: string;
  action: string;
};

export type BeginnerTimelineItem = {
  time: "09:25" | "09:35" | "10:30";
  observation: string;
  action: string;
  if_unmet: string;
};

export type BeginnerDecision = {
  stance: "observe" | "cautious" | "stand_aside";
  headline: string;
  primary_focus: BeginnerFocus | null;
  continue_conditions: BeginnerCondition[];
  stop_conditions: BeginnerCondition[];
  timeline: BeginnerTimelineItem[];
  backup_focus: BeginnerFocus | null;
  avoid_actions: string[];
  term_explanations: Array<{ term: string; plain: string }>;
};

type MarkdownBlock = {
  title: string;
  lines: string[];
};

export function isBeginnerResearchReport(report: AiResearchReport): report is AiResearchReport & { schema_version: 2; beginner_decision: BeginnerDecision } {
  return report.schema_version === 2 && Boolean(report.beginner_decision);
}

export function ReportBody({ report, compact = false }: { report: AiResearchReport; compact?: boolean }) {
  if (!isBeginnerResearchReport(report)) return <ProfessionalReportBody report={report} compact={compact} />;
  return <BeginnerPrototypeReport report={report} />;
}

function ProfessionalReportBody({ report, compact = false }: { report: AiResearchReport; compact?: boolean }) {
  const blocks = splitMarkdown(report.markdown || "");
  const fallbackDecisionLines = findBlockLines(blocks, ["30秒", "盘前结论", "核心结论"]);
  const fallbackEvidenceLines = findBlockLines(blocks, ["证据", "隔夜变化", "外围风险"]);
  const fallbackWatchLines = findBlockLines(blocks, ["盘中观察", "验证点"]);
  const fallbackRiskLines = findBlockLines(blocks, ["信息缺口", "风险", "合规"]);

  return (
    <section className="ai-report-body">
      <section className="ai-report-section ai-report-brief">
        <div className="ai-report-section-head">
          <span><Target /></span>
          <div>
            <p>30秒结论</p>
            <h2>先判断今天该看什么，再判断什么情况作废</h2>
          </div>
        </div>
        {report.decision_cards?.length ? (
          <div className="ai-decision-grid">
            {report.decision_cards.map((item, index) => <DecisionCard item={item} key={index} />)}
          </div>
        ) : (
          <LineCards lines={fallbackDecisionLines} emptyText="本篇暂无结构化结论，后续报告会直接生成主线、验证点和失效条件。" />
        )}
      </section>

      <MobileReportDisclosure title="海外机构研究" summary="背景资料，点击展开">
      <section className="ai-report-section">
        <div className="ai-report-section-head">
          <span><Building2 /></span>
          <div>
            <p>海外机构研究</p>
            <h2>最近公开的产业观点与A股映射</h2>
          </div>
        </div>
        {report.institutional_research?.length ? (
          <div className="ai-institution-grid">
            {report.institutional_research.map((item, index) => (
              <article key={index}>
                <span>{field(item, "institution", "publisher") || "机构待确认"}</span>
                <h3>{field(item, "title", "report_title") || "产业研究观点"}</h3>
                <b>{field(item, "industry", "sector") || "产业方向待确认"} · {field(item, "published_at", "date") || "日期待确认"}</b>
                <p>{field(item, "conclusion", "key_view", "summary") || "公开摘要未提供明确结论。"}</p>
                <strong>{field(item, "a_share_mapping", "impact") || "A股映射需要结合盘中证据验证。"}</strong>
                <small>{field(item, "access_note", "source_status") || "仅使用公开可核验内容"}</small>
              </article>
            ))}
          </div>
        ) : (
          <LineCards lines={[]} emptyText="本篇未找到可公开核验的海外机构产业研报；不使用无法验证的付费墙内容。" />
        )}
      </section>
      </MobileReportDisclosure>

      <MobileReportDisclosure title="证据链" summary="判断依据，点击展开">
      <section className="ai-report-section">
        <div className="ai-report-section-head">
          <span><FileText /></span>
          <div>
            <p>证据链</p>
            <h2>只保留能影响今天决策的信息</h2>
          </div>
        </div>
        {report.evidence_table?.length ? (
          <div className="ai-evidence-table">
            {report.evidence_table.map((item, index) => <EvidenceRow item={item} key={index} />)}
          </div>
        ) : (
          <LineCards lines={fallbackEvidenceLines} emptyText="本篇暂无结构化证据表。" />
        )}
      </section>
      </MobileReportDisclosure>

      <section className="ai-report-section">
        <div className="ai-report-section-head">
          <span><Clock3 /></span>
          <div>
            <p>盘中验证</p>
            <h2>把观点转换成可观察的时间点和条件</h2>
          </div>
        </div>
        {report.watchlist?.length ? (
          <div className="ai-watch-grid">
            {report.watchlist.map((item, index) => <WatchItem item={item} key={index} />)}
          </div>
        ) : (
          <LineCards lines={fallbackWatchLines} emptyText="本篇暂无结构化观察清单。" />
        )}
      </section>

      <section className="ai-report-section">
        <div className="ai-report-section-head">
          <span><TrendingUp /></span>
          <div>
            <p>情景推演</p>
            <h2>盘面不按预期走时，知道该怎么切换视角</h2>
          </div>
        </div>
        {report.scenario_plan?.length ? (
          <div className="ai-scenario-grid">
            {report.scenario_plan.map((item, index) => <ScenarioCard item={item} key={index} />)}
          </div>
        ) : (
          <LineCards lines={[]} emptyText="本篇暂无情景推演。新版本会生成高开高走、高开回落、低开转强等分支。" />
        )}
      </section>

      {(report.risk_calendar?.length || fallbackRiskLines.length || report.data_gaps?.length) ? (
        <section className="ai-report-section">
          <div className="ai-report-section-head">
            <span><CalendarDays /></span>
            <div>
              <p>日历与风险</p>
              <h2>今天可能改变判断的事件和信息缺口</h2>
            </div>
          </div>
          {report.risk_calendar?.length ? (
            <div className="ai-risk-list">
              {report.risk_calendar.map((item, index) => (
                <article key={index}>
                  <b>{field(item, "event", "title", "name") || "待跟踪事件"}</b>
                  <span>{field(item, "time", "date", "window") || "时间待确认"}</span>
                  <p>{field(item, "impact", "why", "note") || "需要观察对市场风险偏好的影响。"}</p>
                </article>
              ))}
            </div>
          ) : null}
          {report.data_gaps?.length ? <LineCards lines={report.data_gaps.map(formatUnknown)} /> : <LineCards lines={fallbackRiskLines} />}
        </section>
      ) : null}

      {!compact ? (
        <>
          {blocks.length ? (
            <MobileReportDisclosure title="深度分析" summary="完整研究框架与判断依据">
            <section className="ai-report-section">
              <div className="ai-report-section-head">
                <span><ListChecks /></span>
                <div>
                  <p>深度分析</p>
                  <h2>完整的研究框架与判断依据</h2>
                </div>
              </div>
              <article className="ai-markdown-rendered">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    a: ({ children, ...props }) => <a {...props} target="_blank" rel="noreferrer">{children}</a>,
                    table: ({ children, ...props }) => <div className="ai-markdown-table-scroll"><table {...props}>{children}</table></div>,
                  }}
                >
                  {report.markdown || ""}
                </ReactMarkdown>
              </article>
            </section>
            </MobileReportDisclosure>
          ) : null}

          {report.sources?.length ? (
            <MobileReportDisclosure title="信息来源" summary="用于复核的公开来源">
            <section className="ai-report-section">
              <div className="ai-report-section-head">
                <span><CheckCircle2 /></span>
                <div>
                  <p>信息来源</p>
                  <h2>用于复核的公开来源</h2>
                </div>
              </div>
              <LineCards lines={report.sources.map(formatSource)} />
            </section>
            </MobileReportDisclosure>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function BeginnerPrototypeReport({ report }: { report: AiResearchReport & { schema_version: 2; beginner_decision: BeginnerDecision } }) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const decision = report.beginner_decision;
  const stanceLabels = { observe: "可以观察", cautious: "谨慎观察", stand_aside: "暂不参与" } as const;
  const guidance = decision.timeline[1] || decision.timeline[0];

  return (
    <section className="ai-beginner-prototype" aria-labelledby="today-title">
      <section className="hero">
        <div className="hero-icon"><PhTarget size={38} weight="duotone" /></div>
        <div className="hero-copy">
          <p className="status">今日态度 · {stanceLabels[decision.stance]}</p>
          <h2 id="today-title">{decision.headline}</h2>
          <p className="focus">今天只看：<strong>{decision.primary_focus?.name || "没有明确方向"}</strong></p>
          <p className="focus-reason">{decision.primary_focus?.reason || "证据不足，今天先不参与。"}</p>
        </div>
        {guidance ? <p className="hero-guidance"><PhClock size={20} weight="duotone" />{guidance.action} {guidance.if_unmet}</p> : null}
      </section>

      <section className="decision-grid" aria-label="今日判断条件">
        <article className="decision-panel positive">
          <div className="panel-title"><PhCheckCircle size={34} weight="duotone" /><div><span>满足全部条件</span><h3>继续观察</h3></div></div>
          <div className="condition-list">
            {decision.continue_conditions.map((item) => <div className="condition" key={`${item.time}-${item.observation}`}><span>{item.time}</span><div><p>{item.observation}</p><small>{item.action}</small></div></div>)}
          </div>
          <p className="panel-outcome"><PhCheckCircle size={19} weight="fill" />可以继续看，但仍不是买入提示</p>
        </article>

        <article className="decision-panel negative">
          <div className="panel-title"><PhXCircle size={34} weight="duotone" /><div><span>出现任意一种</span><h3>立即放弃</h3></div></div>
          <div className="condition-list">
            {decision.stop_conditions.map((item) => <div className="condition" key={`${item.time}-${item.observation}`}><span>{item.time}</span><div><p>{item.observation}</p><small>{item.action}</small></div></div>)}
          </div>
          <p className="panel-outcome"><PhXCircle size={19} weight="fill" />今天不操作</p>
        </article>
      </section>

      <section className="action-flow">
        <div className="section-heading"><PhClock size={23} weight="duotone" /><h3>我该怎么做</h3></div>
        <ol>{decision.timeline.map((item) => <li key={item.time}><span>{item.time}</span><strong>{item.action}</strong><small>看：{item.observation}</small><em>不满足：{item.if_unmet}</em></li>)}</ol>
      </section>

      <section className="backup">
        <div><Pill size={25} weight="duotone" /><span>备选方向</span><strong>{decision.backup_focus?.name || "今天不设备选方向"}</strong></div>
        <p>{decision.backup_focus?.condition || "不临时找题材凑数。"}</p>
      </section>

      <section className="avoid-actions">
        <div className="section-heading"><PhShieldCheck size={23} weight="duotone" /><h3>今天最需要避免</h3></div>
        <ul>{decision.avoid_actions.map((item) => <li key={item}>{item}</li>)}</ul>
      </section>

      <section className={`research-details ${detailsOpen ? "open" : ""}`}>
        <button type="button" aria-expanded={detailsOpen} onClick={() => setDetailsOpen((value) => !value)}>
          <span><PhArticle size={22} weight="duotone" />研究依据与术语解释</span>
          <span className="details-hint">给想深入了解的人<CaretDown size={20} /></span>
        </button>
        {detailsOpen ? <div className="details-body">
          <div className="research-stats"><span><b>{report.sources?.length || 0}</b> 个公开来源</span><span><b>{report.evidence_table?.length || 0}</b> 条证据</span><span><b>{report.institutional_research?.length || 0}</b> 条机构研究</span></div>
          <div className="evidence"><h4>当天专业摘要</h4><p>{report.summary}</p></div>
          <div className="glossary">{decision.term_explanations.map((item) => <div key={item.term}><h4>{item.term}</h4><p>{item.plain}</p></div>)}</div>
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
                {report.markdown || ""}
              </ReactMarkdown>
            </article>
          </details>
        </div> : null}
      </section>

      <footer><PhShieldCheck size={20} weight="duotone" /><strong>不是买点提示，不推荐具体股票。</strong><span>条件不满足时，今天不操作就是正确决定。</span></footer>
    </section>
  );
}

export function ReportMeta({ report }: { report: AiResearchReport }) {
  return (
    <div className="market-day-score-board">
      <article><span>研报日期</span><b>{report.research_date || "-"}</b></article>
      <article><span>内容来源</span><b>{sourceLabel(report.source)}</b></article>
      <article><span>生成时间</span><b>{report.received_at || "-"}</b></article>
    </div>
  );
}

function DecisionCard({ item }: { item: Record<string, unknown> }) {
  return (
    <article className="ai-decision-card">
      <span>{field(item, "label", "priority") || "关注"}</span>
      <h3>{field(item, "title", "theme", "mainline") || "盘前主线"}</h3>
      <p>{field(item, "conclusion", "summary", "view") || "等待盘中验证。"}</p>
      <dl>
        <div><dt>验证</dt><dd>{field(item, "trigger", "valid_condition", "watch") || "开盘后观察量能和板块广度。"}</dd></div>
        <div><dt>失效</dt><dd>{field(item, "invalidates", "invalid_condition", "risk") || "若主线高开低走且放量滞涨，结论失效。"}</dd></div>
      </dl>
      {field(item, "confidence") ? <em>{field(item, "confidence")}</em> : null}
    </article>
  );
}

function EvidenceRow({ item }: { item: Record<string, unknown> }) {
  return (
    <article>
      <b>{field(item, "event", "message", "title") || "核心信息"}</b>
      <p>{field(item, "evidence", "fact", "source_summary") || "证据待补充。"}</p>
      <strong>{field(item, "impact", "a_share_mapping", "decision_use") || "观察其对A股主线的映射。"}</strong>
      <span>{field(item, "confidence") || "置信度待确认"}</span>
    </article>
  );
}

function WatchItem({ item }: { item: Record<string, unknown> }) {
  return (
    <article>
      <b>{field(item, "name", "target", "indicator") || "观察对象"}</b>
      <span>{field(item, "check_time", "time", "window") || "盘中"}</span>
      <p>{field(item, "valid_condition", "trigger", "watch") || "观察是否有量能和广度确认。"}</p>
      <small>{field(item, "invalid_condition", "invalidates", "risk") || "若承接不足则降低该方向优先级。"}</small>
    </article>
  );
}

function ScenarioCard({ item }: { item: Record<string, unknown> }) {
  return (
    <article>
      <b>{field(item, "scenario", "title", "name") || "盘中情景"}</b>
      <p>{field(item, "condition", "trigger") || "触发条件待确认。"}</p>
      <strong>{field(item, "read", "interpretation", "meaning") || "用于判断主线强弱。"}</strong>
      <small>{field(item, "action", "next_step") || "按验证结果调整关注优先级。"}</small>
    </article>
  );
}

function LineCards({ lines, emptyText = "暂无内容。" }: { lines: string[]; emptyText?: string }) {
  const safeLines = lines.filter(Boolean);
  if (!safeLines.length) return <p className="ai-report-empty">{emptyText}</p>;
  return (
    <div className="ai-line-cards">
      {safeLines.map((line, index) => <article key={`${line}-${index}`}>{line}</article>)}
    </div>
  );
}

function splitMarkdown(markdown: string) {
  const lines = markdown.split(/\r?\n/);
  const blocks: MarkdownBlock[] = [];
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    const heading = line.match(/^#{1,3}\s+(.+)$/);
    if (heading) {
      if (line.startsWith("# ") && !blocks.length) continue;
      blocks.push({ title: heading[1], lines: [] });
    } else {
      if (!blocks.length) blocks.push({ title: "正文", lines: [] });
      blocks[blocks.length - 1].lines.push(line);
    }
  }
  return blocks.filter((block) => block.lines.length);
}

function findBlockLines(blocks: MarkdownBlock[], keywords: string[]) {
  const found = blocks.find((block) => keywords.some((keyword) => block.title.includes(keyword)));
  if (!found) return [];
  return parseMarkdownPipeTables(found.lines)
    .filter((segment) => segment.type === "text")
    .flatMap((segment) => segment.type === "text" ? segment.lines.map(cleanMarkdownLine).filter(Boolean) : []);
}

function cleanMarkdownLine(line: string) {
  return line.trim().replace(/^[-*]\s+/, "");
}

function field(item: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const value = item[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number") return String(value);
  }
  return "";
}

function formatUnknown(value: string | Record<string, unknown>) {
  if (typeof value === "string") return value;
  return field(value, "text", "title", "summary", "note") || JSON.stringify(value);
}

function formatSource(source: string | Record<string, unknown>) {
  if (typeof source === "string") return source;
  return [field(source, "title", "source", "name"), field(source, "time", "published_at", "retrieved_at"), field(source, "url")].filter(Boolean).join(" | ");
}

export function sourceLabel(source?: string) {
  if (!source) return "系统整理";
  if (source.includes("automation") || source.includes("manual")) return "系统整理";
  return source;
}
