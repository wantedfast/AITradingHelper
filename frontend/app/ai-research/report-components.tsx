import { AlertTriangle, Ban, Building2, CalendarDays, CheckCircle2, Clock3, Eye, FileText, ListChecks, ShieldCheck, Target, TrendingUp, XCircle } from "lucide-react";
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

  return (
    <section className="ai-report-body ai-report-body-beginner">
      <BeginnerDecisionDashboard decision={report.beginner_decision} />
      <MobileReportDisclosure title="研究依据与术语解释" summary="完整专业研报、公开来源与白话词典">
        <section className="ai-beginner-research-details">
          {report.beginner_decision.term_explanations.length ? (
            <section className="ai-beginner-terms">
              <div className="ai-report-section-head">
                <span><FileText /></span>
                <div><p>白话词典</p><h2>看见专业词时，不必靠猜</h2></div>
              </div>
              <dl>
                {report.beginner_decision.term_explanations.map((item) => (
                  <div key={item.term}><dt>{item.term}</dt><dd>{item.plain}</dd></div>
                ))}
              </dl>
            </section>
          ) : null}
          <ProfessionalReportBody report={report} compact={compact} />
        </section>
      </MobileReportDisclosure>
    </section>
  );
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

function BeginnerDecisionDashboard({ decision }: { decision: BeginnerDecision }) {
  const stance = {
    observe: { label: "可以观察", note: "先看条件，不急着行动", icon: Eye },
    cautious: { label: "谨慎观察", note: "条件全部满足才继续看", icon: ShieldCheck },
    stand_aside: { label: "暂不参与", note: "没有足够证据时，空着也是决定", icon: Ban },
  }[decision.stance];
  const StanceIcon = stance.icon;

  return (
    <section className={`ai-beginner-dashboard stance-${decision.stance}`} aria-labelledby="beginner-decision-title">
      <header className="ai-beginner-hero">
        <div className="ai-beginner-stance"><StanceIcon /><span>{stance.label}</span></div>
        <div>
          <p>今天的 30 秒结论</p>
          <h1 id="beginner-decision-title">{decision.headline}</h1>
          <span>{stance.note}</span>
        </div>
        <aside>
          <small>今天只看</small>
          <strong>{decision.primary_focus?.name || "没有明确方向"}</strong>
          <p>{decision.primary_focus?.reason || "证据不足，今天先不参与。"}</p>
        </aside>
      </header>

      <div className="ai-beginner-decision-grid">
        <article className="ai-beginner-condition-card is-continue">
          <div className="ai-beginner-card-title"><CheckCircle2 /><div><small>满足全部条件</small><h2>继续观察</h2></div></div>
          {decision.continue_conditions.length ? (
            <ol>{decision.continue_conditions.map((item, index) => <ConditionItem item={item} index={index} key={`${item.time || "continue"}-${index}`} />)}</ol>
          ) : <p className="ai-beginner-empty">今天没有继续观察条件。</p>}
        </article>
        <article className="ai-beginner-condition-card is-stop">
          <div className="ai-beginner-card-title"><XCircle /><div><small>出现任意一种</small><h2>立即放弃</h2></div></div>
          <ol>{decision.stop_conditions.map((item, index) => <ConditionItem item={item} index={index} key={`${item.time || "stop"}-${index}`} />)}</ol>
          <strong className="ai-beginner-stop-result">今天不操作</strong>
        </article>
      </div>

      <section className="ai-beginner-timeline" aria-labelledby="beginner-timeline-title">
        <div className="ai-beginner-section-title"><Clock3 /><div><small>开盘后照着看</small><h2 id="beginner-timeline-title">我该怎么做</h2></div></div>
        <ol>
          {decision.timeline.map((item) => (
            <li key={item.time}>
              <time>{item.time}</time>
              <div><b>看什么</b><p>{item.observation}</p></div>
              <div><b>怎么做</b><p>{item.action}</p></div>
              <div className="is-unmet"><b>不满足</b><p>{item.if_unmet}</p></div>
            </li>
          ))}
        </ol>
      </section>

      <div className="ai-beginner-lower-grid">
        <section className="ai-beginner-backup">
          <div className="ai-beginner-section-title"><Target /><div><small>只能单独重新判断</small><h2>备选方向</h2></div></div>
          {decision.backup_focus ? <><strong>{decision.backup_focus.name}</strong><p>{decision.backup_focus.reason}</p><span>{decision.backup_focus.condition || "主方向不成立时，也不能自动切换到这里。"}</span></> : <p>今天不设备选方向，也不要临时找题材凑数。</p>}
        </section>
        <section className="ai-beginner-avoid">
          <div className="ai-beginner-section-title"><AlertTriangle /><div><small>当天纪律</small><h2>最需要避免</h2></div></div>
          <ul>{decision.avoid_actions.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
      </div>

      <p className="ai-beginner-disclaimer"><ShieldCheck />不是买点提示，不推荐具体股票。条件不满足时，今天不操作就是正确决定。</p>
    </section>
  );
}

function ConditionItem({ item, index }: { item: BeginnerCondition; index: number }) {
  return <li><span>{item.time || String(index + 1).padStart(2, "0")}</span><div><p>{item.observation}</p><small>{item.action}</small></div></li>;
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
