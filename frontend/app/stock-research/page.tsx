"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowRight, Boxes, Clock3, ExternalLink, Loader2, RefreshCcw, Search, ShieldCheck } from "lucide-react";
import { MainSidebar, MobileFeatureNav } from "@/components/main-sidebar";
import { FinancialDisclaimer } from "@/components/financial-disclaimer";
import { ApiError, apiFetch, getAuthToken, getStoredUser, refreshCurrentUser, type UserProfile } from "@/lib/auth-client";

type JobStatus = "queued" | "running" | "retrying" | "completed" | "failed" | "timed_out" | "payment_required";
type ResearchJob = {
  id: string; subject_type: "stock" | "industry_chain"; subject_name: string; stock_code?: string;
  status: JobStatus; stage: string; progress: number; provider: string; report_id?: string;
  error_message?: string; estimated_wait_seconds?: number; created_at: string;
};
type Evidence = { id: string; title: string; url: string; publisher?: string; published_at?: string; source_tier: string; excerpt?: string };
type CitationSection = { summary?: string; evidence_ids?: string[] };
type Ranking = { name: string; code?: string; position?: string; reason: string; barrier?: number; profit?: number; growth?: number; core_score?: number; evidence_ids?: string[] };
type RoleConflict = string | { issue?: string; roles?: string[]; resolution?: string; evidence_ids?: string[] };
type ResearchDocument = {
  schema_version: number; subject: { type: "stock" | "industry_chain"; name: string; code?: string }; headline: string;
  capital_logic: CitationSection; product_path: CitationSection; bom: CitationSection & { items?: unknown[] };
  bottleneck: CitationSection; profit_flow: CitationSection; positioning: CitationSection & { label?: string };
  input_stock_score?: { barrier: number; profit: number; growth: number; core_score: number; evidence_ids?: string[] };
  core_asset_ranking: Ranking[]; same_chain_core_asset_ranking?: Ranking[];
  same_chain_core_asset_status?: { status: "ranked" | "none"; reason?: string; evidence_ids?: string[] };
  bottleneck_ranking?: Ranking[]; profit_capture_ranking?: Ranking[];
  judge: CitationSection & { conclusion?: string; role_conflicts?: RoleConflict[]; disconfirming_signals?: string[]; classifications?: Record<string, unknown> };
  evidence: Evidence[]; role_outputs?: Record<string, unknown>; research_board?: Record<string, unknown>;
  meta: { provider: string; input_tokens: number; output_tokens: number; search_count: number; cost_cny: number };
};
type ReportRecord = { id: string; job_id: string; subject_type: string; subject_name: string; stock_code?: string; created_at: string; report?: ResearchDocument };
type ResearchQuota = {
  membership_active: boolean; monthly_included: number; monthly_used: number; monthly_remaining: number;
  daily_limit: number | null; daily_used: number; daily_remaining: number | null;
  credit_balance: number; next_billing_mode: "admin_free" | "membership_included" | "credits"; next_credit_cost: number;
};

const STAGE_LABELS: Record<string, string> = {
  queued: "进入研究队列", recovering: "恢复未完成任务", collecting_evidence: "联网收集证据",
  capital_logic: "分析资金逻辑", product_path: "映射产品路径", bom: "拆解 BOM",
  bottleneck: "识别产业瓶颈", profit_flow: "判断利润流向", evidence_gap_search: "补齐证据缺口",
  fund_manager: "基金经理裁决", completed: "报告完成",
};

export default function StockResearchPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserProfile | null>(() => getStoredUser());
  const [kind, setKind] = useState<"stock" | "industry_chain">("stock");
  const [value, setValue] = useState("");
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [reports, setReports] = useState<ReportRecord[]>([]);
  const [quota, setQuota] = useState<ResearchQuota | null>(null);
  const [selected, setSelected] = useState<ReportRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const loadHistory = useCallback(async () => {
    const payload = await apiFetch<{ reports: ReportRecord[]; quota: ResearchQuota }>("/api/stock-research/reports");
    setReports(payload.reports || []);
    setQuota(payload.quota || null);
  }, []);

  const openReport = useCallback(async (reportId: string) => {
    setBusy(true);
    try {
      const payload = await apiFetch<{ report: ReportRecord }>(`/api/stock-research/reports/${encodeURIComponent(reportId)}`);
      setSelected(payload.report);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取报告失败");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (!getAuthToken()) {
      router.replace(`/auth?redirect=${encodeURIComponent("/stock-research")}`);
      return;
    }
    refreshCurrentUser().then(setUser).catch(() => router.replace(`/auth?redirect=${encodeURIComponent("/stock-research")}`));
    loadHistory().catch(() => undefined);
  }, [loadHistory, router]);

  useEffect(() => {
    if (!job || !["queued", "running", "retrying"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const payload = await apiFetch<{ job: ResearchJob }>(`/api/stock-research/jobs/${job.id}/status`);
        setJob(payload.job);
        if (payload.job.status === "completed" && payload.job.report_id) {
          window.clearInterval(timer);
          await loadHistory();
          await openReport(payload.job.report_id);
          await refreshCurrentUser().then(setUser);
        } else if (["failed", "timed_out", "payment_required"].includes(payload.job.status)) {
          window.clearInterval(timer);
        }
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "查询任务失败");
      }
    }, 2200);
    return () => window.clearInterval(timer);
  }, [job, loadHistory, openReport]);

  async function submit() {
    if (!value.trim()) return setMessage(kind === "stock" ? "请输入一只 A 股简称或六位代码" : "请输入一个产业链名称");
    setBusy(true); setMessage(""); setSelected(null);
    try {
      const payload = await apiFetch<{ job: ResearchJob; quota: ResearchQuota }>("/api/stock-research/jobs", {
        method: "POST", body: JSON.stringify({ type: kind, value: value.trim() }),
      });
      setJob(payload.job);
      setQuota(payload.quota || null);
    } catch (error) {
      const fallback = error instanceof ApiError && error.status === 403 ? "该功能目前仅供管理员完成双引擎评测。" : "创建研究任务失败";
      setMessage(error instanceof Error ? error.message : fallback);
    } finally { setBusy(false); }
  }

  const document = selected?.report;
  const evidenceMap = useMemo(() => new Map((document?.evidence || []).map((item) => [item.id, item])), [document]);

  return (
    <main className="stock-research-page">
      <MainSidebar activeKey="stock-research" note={<>每次只研究一个对象<br />仅成功报告计费</>} />
      <section className="stock-research-shell">
        <header className="stock-research-hero">
          <div><span className="eyebrow">SIX-ROLE REVERSE RESEARCH</span><h1>产业链逆向研究</h1><p>从资金为何交易，一路拆到真实产品、BOM、瓶颈与利润中心，再由基金经理角色裁决。</p></div>
          <div className="stock-research-balance"><ShieldCheck /><span>当前权限</span><b>{user?.role === "admin" ? "管理员评测" : `${user?.credits ?? "—"} 次`}</b></div>
        </header>

        {quota ? <section className="stock-research-quota" aria-label="产业链逆向研究额度">
          {user?.role === "admin" ? <><b>管理员评测免扣</b><span>仅成功报告计入统计</span></> : quota.membership_active ? <>
            <b>本月会员额度 {quota.monthly_used}/{quota.monthly_included}</b>
            <span>今日 {quota.daily_used}/{quota.daily_limit} · {quota.next_billing_mode === "credits" ? "下一份成功后扣 3 次" : `本月还可免费生成 ${quota.monthly_remaining} 份`}</span>
          </> : <><b>每份成功报告扣 3 次</b><span>当前可用 {quota.credit_balance} 次 · 失败不扣</span></>}
        </section> : null}

        <section className="stock-research-input-card">
          <div className="stock-research-kind" role="tablist" aria-label="研究对象类型">
            <button className={kind === "stock" ? "active" : ""} onClick={() => setKind("stock")} type="button">单只 A 股</button>
            <button className={kind === "industry_chain" ? "active" : ""} onClick={() => setKind("industry_chain")} type="button">产业链</button>
          </div>
          <div className="stock-research-form">
            <label><Search /><input maxLength={kind === "stock" ? 20 : 30} onChange={(event) => setValue(event.target.value)} placeholder={kind === "stock" ? "例如：华正新材 / 603186" : "例如：算力租赁产业链"} value={value} /></label>
            <button disabled={busy || Boolean(job && ["queued", "running", "retrying"].includes(job.status))} onClick={submit} type="button">
              {busy ? <Loader2 className="spin" /> : <Boxes />}开始六角色研究
            </button>
          </div>
          <p>{quota?.next_billing_mode === "membership_included" ? "本次使用会员月度额度" : quota?.next_billing_mode === "admin_free" ? "管理员评测不扣次数" : "本次报告成功后扣 3 次"}；失败、超时不扣。内容是研究资料，不提供买卖指令。</p>
        </section>

        {message ? <div className="stock-research-alert"><AlertTriangle />{message}</div> : null}
        {job && job.status !== "completed" ? <JobProgress job={job} /> : null}
        {document ? <ReportView report={document} evidenceMap={evidenceMap} /> : <History reports={reports} onOpen={openReport} busy={busy} />}
        <FinancialDisclaimer />
      </section>
      <MobileFeatureNav activeKey="stock-research" />
    </main>
  );
}

function JobProgress({ job }: { job: ResearchJob }) {
  const failed = ["failed", "timed_out", "payment_required"].includes(job.status);
  return <section className={`stock-research-progress ${failed ? "failed" : ""}`}>
    <div><span>{failed ? <AlertTriangle /> : <Loader2 className="spin" />}</span><div><b>{failed ? "研究未完成" : STAGE_LABELS[job.stage] || "六角色正在协作"}</b><small>{failed ? job.error_message : `预计还需约 ${Math.ceil((job.estimated_wait_seconds || 0) / 60)} 分钟`}</small></div><strong>{job.progress}%</strong></div>
    <div className="progress-track"><i style={{ width: `${job.progress}%` }} /></div>
    <ol>{["资金逻辑", "产品路径", "BOM", "瓶颈", "利润流向", "最终裁决"].map((label, index) => <li className={job.progress >= 12 + index * 12 ? "done" : ""} key={label}>{index + 1}<span>{label}</span></li>)}</ol>
  </section>;
}

function History({ reports, onOpen, busy }: { reports: ReportRecord[]; onOpen: (id: string) => void; busy: boolean }) {
  return <section className="stock-research-history"><div className="section-heading"><div><span>MY RESEARCH</span><h2>历史研究</h2></div><RefreshCcw /></div>
    {reports.length ? <div className="stock-research-history-grid">{reports.map((item) => <button disabled={busy} key={item.id} onClick={() => onOpen(item.id)} type="button"><span>{item.subject_type === "stock" ? "股票" : "产业链"}</span><h3>{item.subject_name}{item.stock_code ? ` · ${item.stock_code}` : ""}</h3><small><Clock3 />{formatDate(item.created_at)}</small><ArrowRight /></button>)}</div> : <div className="stock-research-empty"><Boxes /><h2>还没有产业链研究</h2><p>输入一只 A 股或一个产业链，六个角色会共享证据、互相质疑，最后给出统一裁决。</p></div>}
  </section>;
}

function ReportView({ report, evidenceMap }: { report: ResearchDocument; evidenceMap: Map<string, Evidence> }) {
  const sameChain = report.same_chain_core_asset_ranking || report.core_asset_ranking || [];
  return <article className="stock-research-report">
    <header><span>{report.subject.type === "stock" ? "股票逆向研究" : "产业链逆向研究"}</span><h2>{report.subject.name}{report.subject.code ? ` · ${report.subject.code}` : ""}</h2><p>{report.headline}</p><small>引擎 {report.meta.provider} · {report.evidence.length} 条证据 · 成本 ¥{Number(report.meta.cost_cny || 0).toFixed(2)}</small></header>
    <section className="stock-research-dashboard">
      <InsightCard title="资金为什么炒" section={report.capital_logic} evidenceMap={evidenceMap} />
      <InsightCard title="利润真正流向" section={report.profit_flow} evidenceMap={evidenceMap} />
      <InsightCard title="当前产业瓶颈" section={report.bottleneck} evidenceMap={evidenceMap} />
      <InsightCard title="输入对象定位" section={{ ...report.positioning, summary: report.positioning.label ? `${report.positioning.label}：${report.positioning.summary || ""}` : report.positioning.summary }} evidenceMap={evidenceMap} />
      <InsightCard danger title="最重要证伪信号" section={{ summary: (report.judge.disconfirming_signals || []).join("；"), evidence_ids: report.judge.evidence_ids }} evidenceMap={evidenceMap} />
    </section>
    {report.input_stock_score ? <ScoreCard score={report.input_stock_score} schemaVersion={report.schema_version} /> : null}
    <RankingCard emptyText={report.same_chain_core_asset_status?.reason || "未识别到中等置信度的同链核心资产"} title="同产业链核心资产" rows={sameChain} evidenceMap={evidenceMap} />
    {report.bottleneck_ranking ? <RankingCard title="瓶颈环节榜" rows={report.bottleneck_ranking} evidenceMap={evidenceMap} /> : null}
    {report.profit_capture_ranking ? <RankingCard title="利润捕获榜" rows={report.profit_capture_ranking} evidenceMap={evidenceMap} /> : null}
    <details className="stock-research-professional"><summary>展开专业研究、BOM、角色争议与完整证据</summary>
      <div className="stock-research-professional-grid"><InsightCard title="产品路径" section={report.product_path} evidenceMap={evidenceMap} /><InsightCard title="BOM 拆解" section={report.bom} evidenceMap={evidenceMap} /></div>
      {report.bom.items?.length ? <section><h3>BOM 明细</h3><pre className="stock-research-json">{JSON.stringify(report.bom.items, null, 2)}</pre></section> : null}
      {report.judge.conclusion ? <section><h3>基金经理裁决</h3><p>{report.judge.conclusion}</p></section> : null}
      {report.judge.role_conflicts?.length ? <section><h3>角色争议与裁决</h3><ul>{report.judge.role_conflicts.map((item, index) => <li key={index}>{formatConflict(item)}</li>)}</ul></section> : null}
      {report.role_outputs ? <section><h3>六角色完整研究底稿</h3><pre className="stock-research-json">{JSON.stringify(report.role_outputs, null, 2)}</pre></section> : null}
      {report.research_board ? <section><h3>共享研究板</h3><pre className="stock-research-json">{JSON.stringify(report.research_board, null, 2)}</pre></section> : null}
      <section><h3>完整证据</h3><div className="stock-research-evidence-list">{report.evidence.map((item) => <a href={item.url} key={item.id} rel="noreferrer" target="_blank"><b>{item.id} · {item.source_tier}级</b><span>{item.title}</span><small>{item.publisher} {item.published_at}</small><ExternalLink /></a>)}</div></section>
    </details>
  </article>;
}

function InsightCard({ title, section, evidenceMap, danger = false }: { title: string; section: CitationSection; evidenceMap: Map<string, Evidence>; danger?: boolean }) {
  return <section className={`stock-research-insight ${danger ? "danger" : ""}`}><span>{title}</span><p>{section.summary || "证据不足，暂不下结论"}</p><Citations ids={section.evidence_ids} evidenceMap={evidenceMap} /></section>;
}
function Citations({ ids, evidenceMap }: { ids?: string[]; evidenceMap: Map<string, Evidence> }) {
  return <div className="stock-research-citations">{(ids || []).map((id) => { const item = evidenceMap.get(id); return item ? <a href={item.url} key={id} rel="noreferrer" target="_blank">{id}</a> : <span key={id}>{id}</span>; })}</div>;
}
function ScoreCard({ score, schemaVersion }: { score: NonNullable<ResearchDocument["input_stock_score"]>; schemaVersion: number }) {
  const scale = schemaVersion >= 2 ? 10 : 100;
  return <section className="stock-research-score"><div><span>三高综合评分</span><strong>{score.core_score.toFixed(1)}<small> / {scale}</small></strong><small>不是上涨概率或买入评级</small></div>{[["壁垒高度", score.barrier], ["利润质量", score.profit], ["成长确定性", score.growth]].map(([label, value]) => <label key={String(label)}><span>{label}</span><i><b style={{ width: `${Number(value) / scale * 100}%` }} /></i><strong>{value}</strong></label>)}</section>;
}
function RankingCard({ title, rows, evidenceMap, emptyText = "证据不足" }: { title: string; rows: Ranking[]; evidenceMap: Map<string, Evidence>; emptyText?: string }) {
  return <section className="stock-research-ranking"><h3>{title}</h3>{rows.length ? rows.map((row, index) => <div key={`${row.name}-${index}`}><b>{index + 1}</b><span><strong>{row.name}{row.code ? ` · ${row.code}` : ""}{typeof row.core_score === "number" ? ` · ${row.core_score.toFixed(1)}分` : ""}</strong><small>{row.position || "待核实定位"} · {row.reason}</small></span><Citations ids={row.evidence_ids} evidenceMap={evidenceMap} /></div>) : <p>{emptyText}</p>}</section>;
}
function formatConflict(item: RoleConflict) {
  if (typeof item === "string") return item;
  return `${item.issue || "存在争议"}${item.roles?.length ? `（${item.roles.join(" / ")}）` : ""}：${item.resolution || "待验证"}`;
}
function formatDate(value: string) { return value ? value.slice(0, 16).replace("T", " ") : ""; }
