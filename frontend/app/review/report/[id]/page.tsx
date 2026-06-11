"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ExternalLink, FileText, Loader2, LockKeyhole } from "lucide-react";

type ReviewReportPageProps = {
  params: {
    id: string;
  };
};

type PresenterData = {
  company?: {
    name?: string;
    code?: string;
    subtitle?: string;
    theme?: string;
    node?: string;
  };
  hero?: {
    kicker?: string;
    title?: string;
    industry_rating?: string;
    investment_rating?: string;
    tags?: string[];
    claims?: string[];
    note?: string;
  };
  profit_flow?: {
    title?: string;
    description?: string;
    value_pool?: string;
    items?: Array<{ name?: string; share_pct?: number; highlight?: boolean }>;
    company_position?: string;
    why_profit_flows_here?: string;
  };
  logic_tree?: Array<{ node?: string; certainty_pct?: number }>;
  expectation_gap?: {
    market_believes?: string[];
    analyst_view?: string[];
    gap_score?: number;
    underestimated?: string;
    overestimated?: string;
  };
  moat?: {
    summary?: string;
    items?: string[];
  };
  financial_validation?: string[];
  valuation_odds?: string;
  catalysts?: string[];
  disconfirming_signals?: string[];
  next_action?: {
    current_action?: string;
    suitable_for?: string;
    not_suitable_for?: string;
    recheck_conditions?: string[];
  };
  newbie_summary?: string;
  claim_cards?: Array<{ title?: string; claim?: string; evidence?: string; confidence_pct?: number; risk?: string }>;
  evidence_blocks?: Array<{ type?: string; title?: string; evidence?: string; status?: string }>;
  chart_annotations?: Record<string, string[]>;
  presenter_copy?: Record<string, string>;
};

type ReportManifest = {
  trade_execution_url?: string;
  reports?: Array<{
    trade_execution_url?: string;
  }>;
};

type TradeExecutionData = {
  trade_timing?: {
    buy_points?: unknown;
    sell_points?: unknown;
    [key: string]: unknown;
  };
  execution_advice?: {
    summary?: unknown;
    buy_issue?: unknown;
    sell_issue?: unknown;
    next_time_rules?: unknown;
    confirmation_signals?: unknown;
    [key: string]: unknown;
  };
  peer_comparison?: {
    rows?: Array<Record<string, unknown>>;
    [key: string]: unknown;
  };
  peer_recommendations?: {
    basis?: unknown;
    items?: Array<{
      rank?: unknown;
      name?: unknown;
      code?: unknown;
      why_strong?: unknown;
      moat_reason?: unknown;
      profit_flow_reason?: unknown;
      risk_note?: unknown;
      [key: string]: unknown;
    }>;
    [key: string]: unknown;
  };
  [key: string]: unknown;
};

type TradeExecutionState = {
  data: TradeExecutionData | null;
  status: "loading" | "ready" | "unavailable";
  message: string;
  src: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

export default function ReviewReportPage({ params }: ReviewReportPageProps) {
  const reportId = decodeURIComponent(params.id);
  const safeReportId = encodeURIComponent(reportId);
  const presenterSrc = `${API_BASE}/api/reports/${safeReportId}/research_presenter_data.json`;
  const manifestSrc = `${API_BASE}/api/reports/${safeReportId}/report_manifest.json`;
  const htmlSrc = `${API_BASE}/api/reports/${safeReportId}/index.html`;
  const [data, setData] = useState<PresenterData | null>(null);
  const [tradeExecution, setTradeExecution] = useState<TradeExecutionState>({
    data: null,
    status: "loading",
    message: "",
    src: "",
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function loadPresenterData() {
      setLoading(true);
      setError("");
      try {
        const response = await fetch(presenterSrc, { cache: "no-store" });
        if (!response.ok) throw new Error(`Presenter JSON 加载失败：${response.status}`);
        const payload = (await response.json()) as PresenterData;
        if (!cancelled) setData(payload);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Presenter JSON 加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadPresenterData();
    return () => {
      cancelled = true;
    };
  }, [presenterSrc]);

  useEffect(() => {
    let cancelled = false;
    async function loadTradeExecutionData() {
      setTradeExecution({ data: null, status: "loading", message: "", src: "" });
      try {
        const manifestResponse = await fetch(manifestSrc, { cache: "no-store" });
        if (!manifestResponse.ok) {
          throw new Error(`report_manifest.json \u52a0\u8f7d\u5931\u8d25\uff1a${manifestResponse.status}`);
        }

        const manifest = (await manifestResponse.json()) as ReportManifest;
        const tradeExecutionUrl = manifest.reports?.[0]?.trade_execution_url || manifest.trade_execution_url || "";
        if (!tradeExecutionUrl) {
          if (!cancelled) {
            setTradeExecution({
              data: null,
              status: "unavailable",
              message: "\u4e70\u5356\u70b9\u6570\u636e\u672a\u751f\u6210/\u4e0d\u53ef\u7528",
              src: "",
            });
          }
          return;
        }

        const executionSrc = resolveReportAssetUrl(tradeExecutionUrl, safeReportId);
        const executionResponse = await fetch(executionSrc, { cache: "no-store" });
        if (!executionResponse.ok) {
          throw new Error(`Trade Execution JSON \u52a0\u8f7d\u5931\u8d25\uff1a${executionResponse.status}`);
        }

        const payload = (await executionResponse.json()) as TradeExecutionData;
        if (!cancelled) {
          setTradeExecution({
            data: payload,
            status: "ready",
            message: "",
            src: executionSrc,
          });
        }
      } catch (err) {
        if (!cancelled) {
          setTradeExecution({
            data: null,
            status: "unavailable",
            message:
              err instanceof Error
                ? err.message
                : "\u4e70\u5356\u70b9\u6570\u636e\u672a\u751f\u6210/\u4e0d\u53ef\u7528",
            src: "",
          });
        }
      }
    }

    loadTradeExecutionData();
    return () => {
      cancelled = true;
    };
  }, [manifestSrc, safeReportId]);

  return (
    <main className="review-report-detail-page">
      <header className="review-report-detail-topbar">
        <Link href="/review" className="review-report-back">
          <ArrowLeft />
          返回复盘工作台
        </Link>
        <div className="review-report-detail-title">
          <span>
            <FileText />
            Research Workbench
          </span>
          <b>{reportId}</b>
        </div>
        <div className="review-report-secure">
          <LockKeyhole />
          结构化渲染
        </div>
      </header>

      {loading && (
        <section className="review-report-state">
          <Loader2 className="spin-icon" />
          <span>正在读取 Presenter JSON...</span>
        </section>
      )}

      {!loading && error && (
        <section className="review-report-state">
          <b>{error}</b>
          <a href={htmlSrc} target="_blank" rel="noreferrer">
            打开 HTML 兜底报告 <ExternalLink />
          </a>
        </section>
      )}

      {!loading && !error && data && (
        <StructuredWorkbench
          data={data}
          htmlSrc={htmlSrc}
          presenterSrc={presenterSrc}
          tradeExecution={tradeExecution}
        />
      )}
    </main>
  );
}

function StructuredWorkbench({
  data,
  htmlSrc,
  presenterSrc,
  tradeExecution,
}: {
  data: PresenterData;
  htmlSrc: string;
  presenterSrc: string;
  tradeExecution: TradeExecutionState;
}) {
  const company = data.company || {};
  const hero = data.hero || {};
  const profit = data.profit_flow || {};
  const gap = data.expectation_gap || {};
  const action = data.next_action || {};
  const claims = list(hero.claims).slice(0, 4);
  const tags = list(hero.tags).slice(0, 5);
  const profitItems = list(profit.items).slice(0, 6);
  const logicTree = list(data.logic_tree).slice(0, 6);
  const marketBelieves = list(gap.market_believes).slice(0, 4);
  const analystView = list(gap.analyst_view).slice(0, 4);
  const moatItems = list(data.moat?.items).slice(0, 6);
  const financialValidation = list(data.financial_validation).slice(0, 5);
  const risks = list(data.disconfirming_signals).slice(0, 5);
  const catalysts = list(data.catalysts).slice(0, 5);
  const recheck = list(action.recheck_conditions).slice(0, 5);
  const evidenceBlocks = list(data.evidence_blocks).slice(0, 6);
  const claimCards = list(data.claim_cards).slice(0, 4);
  const maxProfit = useMemo(() => Math.max(100, ...profitItems.map((item) => number(item?.share_pct, 0))), [profitItems]);

  return (
    <section className="structured-report-shell">
      <div className="structured-report-links">
        <a href={presenterSrc} target="_blank" rel="noreferrer">Presenter JSON <ExternalLink /></a>
        <a href={htmlSrc} target="_blank" rel="noreferrer">HTML 兜底报告 <ExternalLink /></a>
      </div>

      <section className="structured-hero">
        <div>
          <p className="structured-kicker">{hero.kicker || "这家公司值得研究吗？"}</p>
          <h1>{company.name || hero.title || "标的公司"}</h1>
          <h2>{company.subtitle || `${company.code || ""} · ${company.theme || "待验证"} / ${company.node || "待验证"}`}</h2>
          <div className="structured-rating-row">
            <span>产业评级 {hero.industry_rating || "B"}</span>
            <span>投资评级 {hero.investment_rating || "B"}</span>
          </div>
          <div className="structured-tag-row">
            {tags.map((tag) => <span key={tag}>{tag}</span>)}
          </div>
        </div>
        <article className="structured-conclusion-card">
          <h3>一句话结论</h3>
          <ul>
            {(claims.length ? claims : ["研究结论待验证。"]).map((claim) => <li key={claim}>{claim}</li>)}
          </ul>
          <p>{hero.note || data.newbie_summary || "首屏回答它为什么值得研究、风险在哪里、下一步验证什么。"}</p>
        </article>
      </section>

      {data.newbie_summary && (
        <section className="structured-section">
          <div className="structured-section-head">
            <h2>新手摘要</h2>
            <span>summary</span>
          </div>
          <p className="structured-body-text">{data.newbie_summary}</p>
        </section>
      )}

      <TradeExecutionAdvicePanel tradeExecution={tradeExecution} />

      <section className="structured-section">
        <div className="structured-section-head">
          <div>
            <h2>{profit.title || "利润流向图"}</h2>
            <p>{profit.description || data.presenter_copy?.profit_flow || "用资金流和利润池解释为什么是它。"}</p>
          </div>
          <span>核心模块</span>
        </div>
        <div className="structured-profit-grid">
          <article className="structured-value-pool">
            <b>{profit.value_pool || company.theme || "价值池"}</b>
            <span>价值池 100%</span>
          </article>
          <div className="structured-flow-bars">
            {profitItems.map((item, index) => {
              const pct = number(item?.share_pct, 0);
              return (
                <div className={item?.highlight ? "is-highlight" : ""} key={`${item?.name || "profit"}-${index}`}>
                  <span>{item?.name || `产业环节 ${index + 1}`}</span>
                  <i><em style={{ width: `${Math.max(4, Math.min(100, (pct / maxProfit) * 100))}%` }} /></i>
                  <b>{pct ? `${Math.round(pct)}%` : "待验证"}</b>
                </div>
              );
            })}
          </div>
          <article className="structured-target-box">
            <span>高亮位置</span>
            <b>{company.name || "目标公司"}</b>
            <p>{profit.company_position || company.node || "产业链位置待验证"}</p>
            <p>{profit.why_profit_flows_here || "利润流向原因待验证"}</p>
          </article>
        </div>
      </section>

      <section className="structured-section">
        <div className="structured-section-head">
          <div>
            <h2>产业逻辑树</h2>
            <p>{data.presenter_copy?.logic_tree || "把上涨逻辑拆成节点，显示每一步的确定性。"}</p>
          </div>
          <span>因果链</span>
        </div>
        <div className="structured-logic-grid">
          {(logicTree.length ? logicTree : [{ node: "逻辑待验证", certainty_pct: 50 }]).map((node, index) => (
            <article key={`${node?.node || "logic"}-${index}`}>
              <h3>{node?.node || `节点 ${index + 1}`}</h3>
              <b>{Math.round(number(node?.certainty_pct, 50))}%</b>
            </article>
          ))}
        </div>
      </section>

      <section className="structured-section">
        <div className="structured-section-head">
          <div>
            <h2>市场预期差</h2>
            <p>{data.presenter_copy?.expectation_gap || "展示市场叙事和研究判断之间的差距。"}</p>
          </div>
          <span>涨幅来源</span>
        </div>
        <div className="structured-gap-grid">
          <article>
            <h3>市场认为</h3>
            <BulletList items={marketBelieves} fallback="市场共识待验证" />
          </article>
          <article className="structured-gap-score">
            <b>{Math.round(number(gap.gap_score, 50))}</b>
            <span>预期差</span>
          </article>
          <article>
            <h3>实际情况</h3>
            <BulletList items={analystView} fallback="研究判断待验证" />
          </article>
        </div>
      </section>

      <section className="structured-section">
        <div className="structured-section-head">
          <div>
            <h2>产业壁垒与验证清单</h2>
            <p>{data.presenter_copy?.moat_validation || "保留 Agent 的关键判断，防止图表把研究结论过度压扁。"}</p>
          </div>
          <span>moat</span>
        </div>
        <div className="structured-three-grid">
          <InfoCard title="壁垒" items={moatItems} fallback={data.moat?.summary || "壁垒待验证"} />
          <InfoCard title="财务验证" items={financialValidation} fallback="财务验证待补充" />
          <InfoCard title="反证点" items={risks} fallback="反证点待验证" />
        </div>
      </section>

      <section className="structured-section">
        <div className="structured-section-head">
          <div>
            <h2>估值赔率、催化剂和下一步</h2>
            <p>{data.presenter_copy?.decision || "把能不能研究进一步落到现在该怎么跟踪。"}</p>
          </div>
          <span>decision</span>
        </div>
        <div className="structured-three-grid">
          <InfoCard title="估值赔率" items={data.valuation_odds ? [data.valuation_odds] : []} fallback="估值赔率待验证" />
          <InfoCard title="催化剂" items={catalysts} fallback="催化剂待验证" />
          <InfoCard title="复查条件" items={recheck} fallback={action.current_action || "复查条件待验证"} />
        </div>
      </section>

      {(claimCards.length > 0 || evidenceBlocks.length > 0) && (
        <section className="structured-section">
          <div className="structured-section-head">
            <div>
              <h2>结论卡与证据块</h2>
              <p>这里展示 Presenter Agent 给前端准备的表达型结构。</p>
            </div>
            <span>evidence</span>
          </div>
          <div className="structured-two-grid">
            <InfoCard title="结论卡" items={claimCards.map((card) => `${card.title || "结论"}：${card.claim || "待验证"}（置信度 ${Math.round(number(card.confidence_pct, 0))}%）`)} fallback="结论卡待验证" />
            <InfoCard title="证据块" items={evidenceBlocks.map((block) => `${block.title || block.type || "证据"}：${block.evidence || "待验证"}（${block.status || "待验证"}）`)} fallback="证据块待验证" />
          </div>
        </section>
      )}
    </section>
  );
}

function TradeExecutionAdvicePanel({ tradeExecution }: { tradeExecution: TradeExecutionState }) {
  const data = tradeExecution.data;
  const buyPoints = useMemo(() => pointList(data?.trade_timing?.buy_points), [data?.trade_timing?.buy_points]);
  const sellPoints = useMemo(() => pointList(data?.trade_timing?.sell_points), [data?.trade_timing?.sell_points]);
  const peerRows = useMemo(
    () => (Array.isArray(data?.peer_comparison?.rows) ? data.peer_comparison.rows : []),
    [data?.peer_comparison?.rows],
  );

  return (
    <section className="structured-section trade-execution-section">
      <div className="structured-section-head">
        <div>
          <h2>{"\u4e70\u5356\u70b9\u8bc4\u4ef7"}</h2>
          <p>
            {
              "\u57fa\u4e8e\u72ec\u7acb Trade Execution \u6570\u636e\uff0c\u805a\u7126\u8fd9\u7b14\u4ea4\u6613\u7684\u4e70\u70b9\u3001\u5356\u70b9\u548c\u4e0b\u6b21\u6267\u884c\u89c4\u5219\u3002"
            }
          </p>
        </div>
        <span>{"\u590d\u76d8\u5efa\u8bae"}</span>
      </div>

      {tradeExecution.status === "loading" && (
        <div className="trade-execution-state">
          <Loader2 className="spin-icon" />
          <span>{"\u6b63\u5728\u8bfb\u53d6\u4e70\u5356\u70b9\u590d\u76d8\u6570\u636e..."}</span>
        </div>
      )}

      {tradeExecution.status !== "loading" && !data && (
        <div className="trade-execution-state is-unavailable">
          <b>{"\u4e70\u5356\u70b9\u6570\u636e\u672a\u751f\u6210/\u4e0d\u53ef\u7528"}</b>
          {tradeExecution.message && <span>{tradeExecution.message}</span>}
        </div>
      )}

      {tradeExecution.status === "ready" && data && (
        <div className="trade-execution-layout">
          <CombinedTradeTimingCard buyPoints={buyPoints} sellPoints={sellPoints} />
          <BuyDayComparisonChart point={buyPoints[0]} />
          <ExecutionAdvicePanel advice={data.execution_advice} />
          <PeerRecommendationsPanel recommendations={data.peer_recommendations} fallbackRows={peerRows} />
        </div>
      )}
    </section>
  );
}

function CombinedTradeTimingCard({
  buyPoints,
  sellPoints,
}: {
  buyPoints: Array<Record<string, unknown>>;
  sellPoints: Array<Record<string, unknown>>;
}) {
  return (
    <article className="trade-execution-card trade-timing-card">
      <h3>{"\u4e70\u5356\u70b9\u4f9d\u636e"}</h3>
      <div className="trade-timing-sections">
        <TradePointSummaryCard title={"\u4e70\u70b9"} points={buyPoints} fallback={"\u4e70\u70b9\u8bc4\u4ef7\u6682\u672a\u751f\u6210"} tone="buy" />
        <TradePointSummaryCard title={"\u5356\u70b9"} points={sellPoints} fallback={"\u5356\u70b9\u8bc4\u4ef7\u6682\u672a\u751f\u6210"} tone="sell" />
      </div>
    </article>
  );
}

function TradePointSummaryCard({
  title,
  points,
  fallback,
  tone,
}: {
  title: string;
  points: Array<Record<string, unknown>>;
  fallback: string;
  tone: "buy" | "sell";
}) {
  const summary = tradePointSummary(points, tone);

  return (
    <section className={`trade-point-summary-card is-${tone}`}>
      <div className="trade-point-summary-head">
        <h4>{title}</h4>
        <span>{summary.count ? `${summary.count} \u7b14\u6210\u4ea4` : "\u6682\u65e0\u6570\u636e"}</span>
      </div>
      {summary.count ? (
        <>
          <div className="trade-point-deals">
            {summary.deals.map((deal) => (
              <span key={deal}>{deal}</span>
            ))}
          </div>
          <div className="trade-point-verdict">
            <span>{"\u6838\u5fc3\u5224\u65ad"}</span>
            <strong>{summary.verdict}</strong>
          </div>
          <div className="trade-point-reason">
            <span>{"\u5224\u65ad\u4f9d\u636e"}</span>
            <p>{summary.reason}</p>
          </div>
          <dl className="trade-point-condition-grid">
            {summary.conditions.map((item) => (
              <div key={item.label}>
                <dt>{item.label}</dt>
                <dd>{item.value}</dd>
              </div>
            ))}
          </dl>
        </>
      ) : (
        <p className="trade-execution-muted">{fallback}</p>
      )}
    </section>
  );
}

function BuyDayComparisonChart({ point }: { point?: Record<string, unknown> }) {
  const items = buyDayChartItems(point);
  const maxAbs = Math.max(1, ...items.map((item) => Math.abs(item.value)));

  return (
    <article className="trade-execution-card trade-buy-chart">
      <h3>{"\u4e70\u5165\u65e5\u6da8\u5e45\u5bf9\u6bd4"}</h3>
      {items.length ? (
        <div className="trade-buy-bars">
          {items.map((item) => {
            const width = `${Math.max(3, (Math.abs(item.value) / maxAbs) * 50)}%`;
            return (
              <div className="trade-buy-bar-row" key={item.label}>
                <span className="trade-buy-bar-label">{item.label}</span>
                <div className="trade-buy-bar-track">
                  <i />
                  <span className={`trade-buy-bar ${item.value >= 0 ? "is-positive" : "is-negative"}`} style={{ width }} />
                </div>
                <strong>{formatPercent(item.value)}</strong>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="trade-execution-muted">{"\u4e70\u5165\u65e5\u6da8\u5e45\u5bf9\u6bd4\u6682\u672a\u751f\u6210"}</p>
      )}
    </article>
  );
}

function PeerRecommendationsPanel({
  recommendations,
  fallbackRows,
}: {
  recommendations?: TradeExecutionData["peer_recommendations"];
  fallbackRows: Array<Record<string, unknown>>;
}) {
  const rows = peerRecommendationItems(recommendations, fallbackRows);

  return (
    <article className="trade-execution-card trade-peer-recommendations">
      <h3>{"\u540c\u4e1a\u5f3a\u8005\u89c2\u5bdf"}</h3>
      {hasMeaningfulValue(recommendations?.basis) && <p className="trade-peer-basis">{formatValue(recommendations?.basis)}</p>}
      {rows.length ? (
        <div className="trade-peer-recommendation-list">
          {rows.map((item, index) => (
            <section className="trade-peer-recommendation-card" key={`${formatValue(item.code)}-${index}`}>
              <div className="trade-peer-recommendation-head">
                <span>{formatRank(item.rank, index)}</span>
                <strong>
                  {formatValue(item.name)}
                  {hasMeaningfulValue(item.code) && <small>{formatValue(item.code)}</small>}
                </strong>
              </div>
              <div className="trade-peer-copy">
                <b>{"\u4e3a\u4ec0\u4e48\u5f3a"}</b>
                <p>{formatValue(item.why_strong)}</p>
              </div>
              <div className="trade-peer-detail-grid">
                <PeerReason title={"\u58c1\u5792\u7406\u7531"} value={item.moat_reason} />
                <PeerReason title={"\u5229\u6da6\u6d41\u5411"} value={item.profit_flow_reason} />
                <PeerReason title={"\u98ce\u9669\u63d0\u793a"} value={item.risk_note} />
              </div>
            </section>
          ))}
        </div>
      ) : (
        <p className="trade-execution-muted">{"\u540c\u4e1a\u5f3a\u8005\u89c2\u5bdf\u6682\u672a\u751f\u6210"}</p>
      )}
    </article>
  );
}

function PeerReason({ title, value }: { title: string; value: unknown }) {
  return (
    <div>
      <span>{title}</span>
      <p>{hasMeaningfulValue(value) ? formatValue(value) : "\u5f85\u8865\u5145"}</p>
    </div>
  );
}

function ExecutionAdvicePanel({ advice }: { advice?: TradeExecutionData["execution_advice"] }) {
  const hasRuleAdvice = Boolean(
    advice && (hasMeaningfulValue(advice.next_time_rules) || hasMeaningfulValue(advice.confirmation_signals)),
  );
  const hasAdvice = Boolean(
    advice &&
      ["summary", "next_time_rules", "confirmation_signals"].some((key) =>
        hasMeaningfulValue(advice[key]),
      ),
  );

  return (
    <article className="trade-execution-card trade-advice-card is-subtle">
      <h3>{"\u4e0b\u6b21\u6267\u884c\u89c4\u5219"}</h3>
      {!hasAdvice || !advice ? (
        <p className="trade-execution-muted">{"\u4e0b\u6b21\u6267\u884c\u89c4\u5219\u6682\u672a\u751f\u6210"}</p>
      ) : (
        <>
          {hasMeaningfulValue(advice.summary) && (
            <div className="trade-advice-summary">
              <span>{"\u6267\u884c\u5907\u6ce8"}</span>
              <p>{formatValue(advice.summary)}</p>
            </div>
          )}
          {hasRuleAdvice && (
            <div className="trade-advice-grid">
              <AdviceItem title={"\u4e0b\u6b21\u6267\u884c\u89c4\u5219"} value={advice.next_time_rules} />
              <AdviceItem title={"\u786e\u8ba4\u4fe1\u53f7"} value={advice.confirmation_signals} />
            </div>
          )}
        </>
      )}
    </article>
  );
}

function AdviceItem({ title, value }: { title: string; value: unknown }) {
  if (!hasMeaningfulValue(value)) return null;
  const items = adviceList(value);

  return (
    <div className="trade-advice-item">
      <h4>{title}</h4>
      {items.length > 1 ? (
        <ul className="trade-advice-list">
          {items.map((item, index) => (
            <li key={`${title}-${index}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <p>{items[0] || formatValue(value)}</p>
      )}
    </div>
  );
}

function InfoCard({ title, items, fallback }: { title: string; items: string[]; fallback: string }) {
  return (
    <article className="structured-info-card">
      <h3>{title}</h3>
      <BulletList items={items} fallback={fallback} />
    </article>
  );
}

function BulletList({ items, fallback }: { items: string[]; fallback: string }) {
  const rows = items.length ? items : [fallback];
  return (
    <ul>
      {rows.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
    </ul>
  );
}

function list<T>(value?: T[] | T | null): T[] {
  if (Array.isArray(value)) return value.filter((item) => item !== null && item !== undefined && item !== "");
  if (value) return [value];
  return [];
}

function pointList(value: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(value)) return value.filter(isPlainObject);
  if (isPlainObject(value)) return [value];
  return [];
}

function number(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function tradePointTitle(point: Record<string, unknown>, index: number) {
  const date = formatValue(point.date || point["\u65e5\u671f"]);
  if (date !== "-") return date;
  return `\u7b2c ${index + 1} \u7b14`;
}

function tradePointMeta(point: Record<string, unknown>) {
  const price = formatValue(point.price || point["\u6210\u4ea4\u4ef7"]);
  return price === "-" ? "\u6210\u4ea4\u4ef7\u5f85\u8865\u5145" : `\u6210\u4ea4\u4ef7 ${price}`;
}

function tradePointSummary(points: Array<Record<string, unknown>>, tone: "buy" | "sell") {
  const first = points[0];
  const fallbackVerdict = tone === "buy" ? "\u4e70\u70b9\u5224\u65ad\u5f85\u8865\u5145" : "\u5356\u70b9\u5224\u65ad\u5f85\u8865\u5145";
  const fallbackReason = tone === "buy" ? "\u7f3a\u5c11\u4e70\u70b9\u6761\u4ef6\u4f9d\u636e\u3002" : "\u7f3a\u5c11\u5356\u70b9\u6761\u4ef6\u4f9d\u636e\u3002";
  return {
    count: points.length,
    deals: points.map((point, index) => `${tradePointTitle(point, index)} \u00b7 ${tradePointMeta(point)}`),
    verdict: uniqueFormattedValues(points, ["judgment", "\u5224\u65ad"])[0] || fallbackVerdict,
    reason: uniqueFormattedValues(points, ["reason", "\u539f\u56e0"]).join("\uff1b") || fallbackReason,
    conditions: first ? tradePointConditions(first) : [],
  };
}

function tradePointConditions(point: Record<string, unknown>) {
  return [
    { label: "\u4e2a\u80a1\u5f53\u65e5", value: formatPercent(pointValue(point, ["stock_pct", "stock pct"])) },
    { label: "\u6caa\u6df1300", value: formatPercent(pointValue(point, ["hs300_etf_pct", "hs300 etf pct"])) },
    { label: "\u677f\u5757/\u6982\u5ff5", value: formatPercent(pointValue(point, ["sector_pct", "sector pct"])) },
    { label: "\u76f8\u5bf9\u6caa\u6df1300", value: formatPercent(pointValue(point, ["excess_vs_hs300_pct", "vs_hs300_pct"])) },
    { label: "\u76f8\u5bf9\u677f\u5757", value: formatPercent(pointValue(point, ["excess_vs_sector_pct", "vs_sector_pct"])) },
    { label: "\u65e5\u5185\u4f4d\u7f6e", value: intradayPositionText(point.intraday_position) },
  ].filter((item) => item.value !== "-");
}

function pointValue(point: Record<string, unknown>, keys: string[]) {
  return keys.map((key) => point[key]).find((value) => value !== null && value !== undefined && value !== "");
}

function uniqueFormattedValues(points: Array<Record<string, unknown>>, keys: string[]) {
  const seen = new Set<string>();
  const values: string[] = [];
  for (const point of points) {
    const value = keys.map((key) => point[key]).find(hasMeaningfulValue);
    const text = formatValue(value);
    if (text === "-" || seen.has(text)) continue;
    seen.add(text);
    values.push(text);
  }
  return values;
}

function intradayPositionText(value: unknown) {
  const text = formatValue(value);
  const labels: Record<string, string> = {
    low: "\u65e5\u5185\u4f4e\u4f4d",
    middle: "\u65e5\u5185\u4e2d\u4f4d",
    high: "\u65e5\u5185\u9ad8\u4f4d",
    unknown: "\u6682\u65e0\u65e5\u5185\u4f4d\u7f6e",
  };
  return labels[text] || text;
}

function buyDayChartItems(point?: Record<string, unknown>) {
  if (!point) return [];
  const stockPctKey = "stock" + " pct";
  const hs300PctKey = "hs300 etf" + " pct";
  const sectorPctKey = "sector" + " pct";
  const chartKeys: Array<{ label: string; keys: string[] }> = [
    { label: "\u4e2a\u80a1", keys: ["stock_pct", stockPctKey] },
    { label: "\u6caa\u6df1300ETF", keys: ["hs300_etf_pct", hs300PctKey] },
    { label: "\u6240\u5c5e\u677f\u5757/\u6982\u5ff5", keys: ["sector_pct", sectorPctKey] },
  ];

  return chartKeys.flatMap(({ label, keys }) => {
    const value = pickValue(point, keys);
    if (!hasMeaningfulValue(value)) return [];
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return [];
    return [{ label, value: parsed }];
  });
}

function peerRecommendationItems(
  recommendations: TradeExecutionData["peer_recommendations"] | undefined,
  fallbackRows: Array<Record<string, unknown>>,
) {
  const items = Array.isArray(recommendations?.items) ? recommendations.items : [];
  if (items.length) return items.slice(0, 3);

  return fallbackRows.slice(0, 3).map((row, index) => ({
    rank: index + 1,
    name: row.name || row.stock_name || row.symbol,
    code: row.code || row.symbol,
    why_strong: "\u540c\u884c\u8868\u73b0\u53c2\u8003\uff0c\u63a8\u8350\u7406\u7531\u5f85\u8865\u5145\u3002",
    moat_reason: "\u58c1\u5792\u7406\u7531\u5f85\u8865\u5145\u3002",
    profit_flow_reason: "\u5229\u6da6\u6d41\u5411\u7406\u7531\u5f85\u8865\u5145\u3002",
    risk_note: "\u8be5\u6761\u4e3a\u4fdd\u5b88\u5360\u4f4d\uff0c\u4ec5\u4f9b\u540c\u884c\u8868\u73b0\u53c2\u8003\u3002",
  }));
}

function formatRank(rank: unknown, index: number) {
  const parsed = Number(rank);
  return `#${Number.isFinite(parsed) ? Math.round(parsed) : index + 1}`;
}

function pickValue(source: Record<string, unknown>, keys: string[]) {
  return keys.map((key) => source[key]).find(hasMeaningfulValue);
}

function formatPercent(value: unknown) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return formatValue(value);
  const sign = parsed > 0 ? "+" : "";
  return `${sign}${parsed.toFixed(2)}%`;
}

function hasMeaningfulValue(value: unknown): boolean {
  if (value === null || value === undefined || value === "") return false;
  if (Array.isArray(value)) return value.some(hasMeaningfulValue);
  if (isPlainObject(value)) return Object.values(value).some(hasMeaningfulValue);
  return true;
}

function adviceList(value: unknown): string[] {
  if (!hasMeaningfulValue(value)) return [];
  if (Array.isArray(value)) return value.flatMap((item) => adviceList(item)).filter((item) => item !== "-");
  if (isPlainObject(value)) return Object.values(value).flatMap((item) => adviceList(item)).filter((item) => item !== "-");
  return [formatValue(value)];
}

function resolveReportAssetUrl(url: string, safeReportId: string) {
  const trimmed = url.trim();
  if (!trimmed) return "";
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  if (trimmed.startsWith("/")) return `${API_BASE}${trimmed}`;
  const cleaned = trimmed.replace(/^\.?\//, "");
  return `${API_BASE}/api/reports/${safeReportId}/${cleaned}`;
}

function labelize(key: string) {
  const labels: Record<string, string> = {
    code: "\u4ee3\u7801",
    name: "\u540d\u79f0",
    symbol: "\u4ee3\u7801",
    stock_name: "\u540d\u79f0",
    day_pct: "\u5f53\u65e5\u6da8\u8dcc\u5e45",
    five_day_pct: "5\u65e5\u6da8\u8dcc\u5e45",
    twenty_day_pct: "20\u65e5\u6da8\u8dcc\u5e45",
    pct_chg: "\u6da8\u8dcc\u5e45",
    change_pct: "\u6da8\u8dcc\u5e45",
    score: "\u8bc4\u5206",
    note: "\u8bf4\u660e",
    advantage: "\u4f18\u52bf",
    weakness: "\u77ed\u677f",
    judgment: "\u5224\u65ad",
    reason: "\u539f\u56e0",
    stock_pct: "\u4e2a\u80a1\u6da8\u8dcc\u5e45",
    hs300_etf_pct: "\u6caa\u6df1300ETF\u6da8\u8dcc\u5e45",
    sector_pct: "\u677f\u5757\u6da8\u8dcc\u5e45",
    vs_hs300_pct: "\u76f8\u5bf9\u6caa\u6df1300ETF",
    excess_vs_hs300_pct: "\u76f8\u5bf9\u6caa\u6df1300ETF",
    vs_sector_pct: "\u76f8\u5bf9\u677f\u5757",
    excess_vs_sector_pct: "\u76f8\u5bf9\u677f\u5757",
    buy_issue: "\u4e70\u70b9\u95ee\u9898",
    sell_issue: "\u5356\u70b9\u95ee\u9898",
    next_time_rules: "\u4e0b\u6b21\u6267\u884c\u89c4\u5219",
    confirmation_signals: "\u786e\u8ba4\u4fe1\u53f7",
    summary: "\u6267\u884c\u5907\u6ce8",
    date: "\u65e5\u671f",
    price: "\u6210\u4ea4\u4ef7",
  };
  return labels[key] || "\u5176\u4ed6";
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === "boolean") return value ? "\u662f" : "\u5426";
  if (Array.isArray(value)) return value.map((item) => formatValue(item)).filter((item) => item !== "-").join("\uff1b");
  if (isPlainObject(value)) {
    return Object.entries(value)
      .map(([key, item]) => `${labelize(key)}\uff1a${formatValue(item)}`)
      .join("\uff1b");
  }
  return String(value);
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
