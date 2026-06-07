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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

export default function ReviewReportPage({ params }: ReviewReportPageProps) {
  const reportId = decodeURIComponent(params.id);
  const safeReportId = encodeURIComponent(reportId);
  const presenterSrc = `${API_BASE}/api/reports/${safeReportId}/research_presenter_data.json`;
  const htmlSrc = `${API_BASE}/api/reports/${safeReportId}/index.html`;
  const [data, setData] = useState<PresenterData | null>(null);
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

      {!loading && !error && data && <StructuredWorkbench data={data} htmlSrc={htmlSrc} presenterSrc={presenterSrc} />}
    </main>
  );
}

function StructuredWorkbench({ data, htmlSrc, presenterSrc }: { data: PresenterData; htmlSrc: string; presenterSrc: string }) {
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

function number(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}
