import { ShieldCheck } from "lucide-react";
import { ReportPipeContent } from "@/components/report-pipe-table";
import { containsMarkdownPipeTable } from "@/lib/markdown-pipe-table";
import { evidenceReportText, namedReportText, watchPointReportText, type LabeledReportText } from "@/lib/market-day-report-content";

export type MarketDayEnvelope = {
  run_id?: string;
  market_date?: string;
  report?: MarketDayReport;
};

export type MarketDayReport = {
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
    evidence?: EvidenceItem[];
    score?: number;
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
  fakeOrWeakLines?: Array<{ name?: string; reason?: string }>;
  watchPoints?: Array<string | WatchPoint>;
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

export function MarketDayReportView({
  envelope,
  billingMessage = "",
}: {
  envelope: MarketDayEnvelope;
  billingMessage?: string;
}) {
  const report = envelope.report;
  if (!report) return null;
  const strongestStocks = report.strongestStocks || [];

  return (
    <div className="dated-report-content" id="market-day-inline-report">
      <section className="review-workbench-hero market-day-report-hero">
        <div className="review-hero-copy">
          <p className="review-kicker">MARKET JUDGE RESULT</p>
          <TableAwareHeading value={report.oneLineConclusion || "AI 当日行情复盘"} level={1} />
          <TableAwareText value={report.mainline?.reason || "系统已完成当天行情主线判断。"} />
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

      <section className="research-panel market-day-audit-panel">
        <span className="card-label">复盘观察</span>
        <LineList items={report.watchPoints} icon />
        <div className="market-day-audit-grid">
          <article><b>证据不足</b><LineList items={report.audit?.missingEvidence} /></article>
          <article><b>来源提醒</b><LineList items={report.audit?.sourceWarnings} /></article>
        </div>
      </section>
    </div>
  );
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
