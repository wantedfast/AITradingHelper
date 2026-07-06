"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, ClipboardCopy, FileText, GitBranch, Loader2, RotateCcw, Search, Sparkles } from "lucide-react";
import { getAuthToken, storeUser, type UserProfile } from "@/lib/auth-client";
import { MainSidebar } from "@/components/main-sidebar";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8600" : "");
const MAX_TARGET_LENGTH = 100;

type AnalyzeStatus = "idle" | "loading" | "success" | "error";
type AnalyzeMode = "auto" | "industry_chain" | "stock";
type DetectedType = "stock" | "industry_chain" | "unknown";

type IndustryTrendPayload = {
  run_id?: string;
  status?: "queued" | "running" | "done" | "error";
  stage?: string;
  status_url?: string;
  query?: string;
  input_type?: "auto" | "chain" | "stock";
  answer?: string;
  source?: string;
  endpoint?: string;
  elapsed_seconds?: number;
  estimated_seconds?: number;
  poll_interval_ms?: number;
  billing_status?: string;
  user?: UserProfile;
  error?: string;
  detail?: string;
};

type AnalyzeState = {
  status: AnalyzeStatus;
  target: string;
  mode: AnalyzeMode;
  detectedType?: DetectedType;
  reportId?: string;
  generatedAt?: string;
  errorMessage?: string;
};

const examples = ["华海清科", "AI服务器液冷产业链", "亨通光电", "HBM先进封装设备", "低空经济"];

const modeOptions: Array<{ value: AnalyzeMode; label: string; hint: string }> = [
  { value: "auto", label: "自动识别", hint: "系统判断输入对象是产业链还是个股" },
  { value: "industry_chain", label: "产业链", hint: "分析主题、赛道或细分方向" },
  { value: "stock", label: "个股", hint: "分析某一家上市公司" },
];

export default function IndustryTrendPage() {
  const router = useRouter();
  const [target, setTarget] = useState("");
  const [mode, setMode] = useState<AnalyzeMode>("auto");
  const [state, setState] = useState<AnalyzeState>({ status: "idle", target: "", mode: "auto" });
  const [result, setResult] = useState<IndustryTrendPayload | null>(null);
  const [job, setJob] = useState<IndustryTrendPayload | null>(null);
  const [showReport, setShowReport] = useState(false);
  const [copied, setCopied] = useState(false);

  const resultLines = useMemo(() => splitAnswer(result?.answer || ""), [result?.answer]);
  const isLoading = state.status === "loading";
  const activeMode = modeOptions.find((item) => item.value === mode) || modeOptions[0];

  async function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (isLoading) return;
    const validation = validateTarget(target);
    if (validation) {
      setState({ status: "error", target, mode, errorMessage: validation });
      setResult(null);
      setJob(null);
      setShowReport(false);
      return;
    }
    const token = getAuthToken();
    if (!token) {
      router.push("/auth?redirect=/industry-trend");
      return;
    }

    const trimmed = target.trim();
    setState({ status: "loading", target: trimmed, mode });
    setResult(null);
    setJob(null);
    setShowReport(false);
    setCopied(false);
    try {
      const response = await fetch(`${API_BASE}/api/industry-trend`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ query: trimmed, input_type: modeToApiInput(mode) }),
        cache: "no-store",
      });
      const text = await response.text();
      const payload = text ? (JSON.parse(text) as IndustryTrendPayload) : {};
      if (!response.ok) throw new Error(payload.error || payload.detail || "请求失败，请检查本地 Stock Analyze 服务是否启动。");
      setJob(payload);
      const donePayload = payload.status === "done" ? payload : await pollIndustryTrend(payload, token);
      if (donePayload.user) storeUser(donePayload.user);
      setResult(donePayload);
      setJob(donePayload);
      setState({
        status: "success",
        target: donePayload.query || trimmed,
        mode,
        detectedType: detectedTypeFromPayload(donePayload, mode),
        reportId: donePayload.run_id,
        generatedAt: new Date().toISOString(),
      });
    } catch (error) {
      setState({
        status: "error",
        target: trimmed,
        mode,
        errorMessage: error instanceof Error ? error.message : "请求失败，请检查本地 Stock Analyze 服务是否启动。",
      });
    }
  }

  function updateTarget(value: string) {
    setTarget(value);
    if (state.status === "success" || state.status === "error") {
      setState({ status: "idle", target: value, mode });
      setResult(null);
      setJob(null);
      setShowReport(false);
      setCopied(false);
    }
  }

  function updateMode(value: AnalyzeMode) {
    setMode(value);
    if (state.status === "success" || state.status === "error") {
      setState({ status: "idle", target, mode: value });
      setResult(null);
      setJob(null);
      setShowReport(false);
      setCopied(false);
    }
  }

  function applyExample(value: string) {
    setTarget(value);
    setState({ status: "idle", target: value, mode });
    setResult(null);
    setJob(null);
    setShowReport(false);
    setCopied(false);
  }

  async function copyResult() {
    if (!result?.answer) return;
    await navigator.clipboard.writeText(result.answer);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  function viewReport() {
    if (!state.reportId && !result?.answer) {
      setState({ status: "error", target, mode, errorMessage: "未找到报告，请重新生成" });
      return;
    }
    setShowReport(true);
  }

  return (
    <main className="review-workbench-page industry-trend-page">
      <MainSidebar
        activeKey="industry-trend"
        note="先在本地启动 Stock Analyze：.\\start.ps1 -StockSkill -Port 8750，再输入一个产业链或个股。"
      />

      <section className="review-workbench-main">
        <header className="review-workbench-topbar">
          <div className="review-topbar-title">
            <span className="topbar-icon"><GitBranch /></span>
            <b>Local Stock Analyze</b>
            <i>INDUSTRY</i>
          </div>
          <div className="review-workbench-actions">
            <button type="button" onClick={() => router.push("/")}>首页</button>
          </div>
        </header>

        <section className="review-workbench-hero industry-trend-hero">
          <div className="review-hero-copy">
            <p className="review-kicker">LOCAL STOCK ANALYZE</p>
            <h1 className="industry-hero-title">
              <span>输入产业链，AI 用 BOM 拆解价值链，用“三高模型”找龙头。</span>
              <span>输入个股，AI 反向识别它在产业链中的位置、利润来源和受益逻辑。</span>
            </h1>
          </div>

          <form className="research-panel industry-trend-form industry-analyze-card" onSubmit={submit}>
            <label className="industry-target-field">
              <span>分析对象</span>
              <div className="industry-search-box">
                <Search />
                <input
                  value={target}
                  onChange={(event) => updateTarget(event.target.value)}
                  placeholder="请输入一个产业链或个股，例如：华海清科 / HBM先进封装设备"
                  maxLength={MAX_TARGET_LENGTH}
                  disabled={isLoading}
                />
              </div>
            </label>

            <div className="industry-field-group">
              <div className="industry-section-title">
                <span>分析模式</span>
                <em>{activeMode.hint}</em>
              </div>
              <div className="industry-type-toggle" aria-label="分析模式">
                {modeOptions.map((item) => (
                  <button
                    className={mode === item.value ? "active" : ""}
                    type="button"
                    key={item.value}
                    onClick={() => updateMode(item.value)}
                    disabled={isLoading}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="industry-field-group">
              <div className="industry-section-title">
                <span>常用示例</span>
                <em>点击只会填入输入框，不会自动提交</em>
              </div>
              <div className="industry-example-row">
                {examples.map((item) => (
                  <button type="button" key={item} onClick={() => applyExample(item)} disabled={isLoading}>
                    {item}
                  </button>
                ))}
              </div>
            </div>

            {state.status !== "success" ? (
              <button className="primary-gold-action" type="submit" disabled={isLoading}>
                {isLoading ? <Loader2 className="spin-icon" /> : <Sparkles />}
                {buttonText(state.status)}
              </button>
            ) : null}

            <StatusPanel
              state={state}
              job={job}
              result={result}
              onRetry={() => submit()}
              onViewReport={viewReport}
            />
          </form>
        </section>

        {showReport && result ? (
          <section className="research-panel industry-result-panel">
            <div className="industry-result-head">
              <div>
                <span className="card-label">{result.source || "stock-analyze"}</span>
                <h2>{result.query || state.target}</h2>
                <p>耗时 {result.elapsed_seconds ?? "-"} 秒 · 类型 {displayType(state.detectedType, state.mode)} · {billingText(result.billing_status)}</p>
              </div>
              <button type="button" onClick={copyResult}>
                <ClipboardCopy />
                {copied ? "已复制" : "复制结果"}
              </button>
            </div>
            <article className="industry-markdown">
              {resultLines.map((line, index) => renderLine(line, index))}
            </article>
          </section>
        ) : null}
      </section>
    </main>
  );
}

function StatusPanel({
  state,
  job,
  result,
  onRetry,
  onViewReport,
}: {
  state: AnalyzeState;
  job: IndustryTrendPayload | null;
  result: IndustryTrendPayload | null;
  onRetry: () => void;
  onViewReport: () => void;
}) {
  if (state.status === "idle") {
    return (
      <div className="industry-status-card industry-status-idle">
        <FileText />
        <span>输入一个产业链或个股，开始生成本地分析报告。</span>
      </div>
    );
  }
  if (state.status === "loading") {
    return (
      <div className="industry-status-card industry-status-loading" role="status" aria-live="polite">
        <Loader2 className="spin-icon" />
        <div>
          <b>正在生成分析报告...</b>
          <span>分析对象：{state.target}</span>
          <span>分析模式：{displayMode(state.mode)}</span>
          <p>正在调用本地 Stock Analyze 服务，请稍候。{job?.stage ? `当前阶段：${job.stage}` : ""}</p>
        </div>
      </div>
    );
  }
  if (state.status === "success") {
    return (
      <div className="industry-status-card industry-status-success">
        <CheckCircle2 />
        <div>
          <b>报告生成成功</b>
          <span>分析对象：{state.target}</span>
          <span>分析类型：{displayType(state.detectedType, state.mode)}</span>
          <span>生成时间：{formatGeneratedAt(state.generatedAt)}</span>
          <span>{billingText(result?.billing_status)}</span>
          <button type="button" onClick={onViewReport}>
            <FileText />
            查看报告
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="industry-status-card industry-status-error">
      <AlertCircle />
      <div>
        <b>报告生成失败</b>
        <span>失败原因：{state.errorMessage || "请求失败，请检查本地 Stock Analyze 服务是否启动。"}</span>
        <button type="button" onClick={onRetry}>
          <RotateCcw />
          重新生成
        </button>
      </div>
    </div>
  );
}

function validateTarget(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "请输入一个分析对象";
  if (trimmed.length > MAX_TARGET_LENGTH) return "分析对象过长，请只输入一个产业链或个股";
  if (/[\n\r,，、;；]/.test(trimmed)) return "当前仅支持每次分析一个对象，请删除多余内容";
  return "";
}

function modeToApiInput(value: AnalyzeMode) {
  if (value === "industry_chain") return "chain";
  return value;
}

function detectedTypeFromPayload(payload: IndustryTrendPayload, fallback: AnalyzeMode): DetectedType {
  if (payload.input_type === "stock") return "stock";
  if (payload.input_type === "chain") return "industry_chain";
  if (fallback === "stock") return "stock";
  if (fallback === "industry_chain") return "industry_chain";
  return "unknown";
}

function displayType(type: DetectedType | undefined, fallback: AnalyzeMode) {
  const value = type || detectedTypeFromPayload({}, fallback);
  if (value === "stock") return "个股";
  if (value === "industry_chain") return "产业链";
  if (fallback === "auto") return "自动识别";
  return "未识别";
}

function displayMode(value: AnalyzeMode) {
  if (value === "stock") return "个股";
  if (value === "industry_chain") return "产业链";
  return "自动识别";
}

function buttonText(status: AnalyzeStatus) {
  if (status === "loading") return "正在生成中...";
  if (status === "error") return "重新生成";
  return "开始分析";
}

function formatGeneratedAt(value?: string) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16).replace("T", " ");
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function splitAnswer(answer: string) {
  return answer.replace(/\r\n/g, "\n").split("\n");
}

async function pollIndustryTrend(initial: IndustryTrendPayload, token: string) {
  if (!initial.status_url) return initial;
  const interval = Math.max(1500, Math.min(8000, Number(initial.poll_interval_ms || 3000)));
  for (let attempt = 0; attempt < 180; attempt += 1) {
    await delay(interval);
    const response = await fetch(`${API_BASE}${initial.status_url}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    const text = await response.text();
    const payload = text ? (JSON.parse(text) as IndustryTrendPayload) : {};
    if (!response.ok) throw new Error(payload.error || payload.detail || "产业趋势任务查询失败");
    if (payload.status === "done") return payload;
    if (payload.status === "error") throw new Error(payload.error || payload.detail || "产业趋势分析失败");
  }
  throw new Error("生成超时，请稍后重试。");
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function billingText(status?: string) {
  if (status === "charged") return "已扣 1 次";
  if (status === "membership_free") return "会员免扣";
  if (status === "admin_free") return "管理员免扣";
  if (status === "not_charged") return "未扣次数";
  return "生成成功";
}

function renderLine(line: string, index: number) {
  const trimmed = line.trim();
  if (!trimmed) return <br key={index} />;
  if (trimmed.startsWith("### ")) return <h4 key={index}>{trimmed.slice(4)}</h4>;
  if (trimmed.startsWith("## ")) return <h3 key={index}>{trimmed.slice(3)}</h3>;
  if (trimmed.startsWith("# ")) return <h2 key={index}>{trimmed.slice(2)}</h2>;
  if (/^\*\*.*\*\*$/.test(trimmed)) return <h3 key={index}>{trimmed.replace(/\*\*/g, "")}</h3>;
  if (/^\d+\.\s/.test(trimmed)) return <p className="number-line" key={index}>{trimmed}</p>;
  if (trimmed.startsWith("- ")) return <p className="bullet-line" key={index}>{trimmed.slice(2)}</p>;
  if (trimmed.startsWith("|")) return <pre key={index}>{trimmed}</pre>;
  return <p key={index}>{trimmed}</p>;
}
