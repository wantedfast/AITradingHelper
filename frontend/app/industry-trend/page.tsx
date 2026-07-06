"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, ClipboardCopy, GitBranch, Loader2, Network, Sparkles } from "lucide-react";
import { getAuthToken, storeUser, type UserProfile } from "@/lib/auth-client";
import { MainSidebar } from "@/components/main-sidebar";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8600" : "");

type InputType = "auto" | "chain" | "stock";

type IndustryTrendPayload = {
  run_id?: string;
  status?: "queued" | "running" | "done" | "error";
  stage?: string;
  status_url?: string;
  query?: string;
  input_type?: InputType;
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

const examples = ["华海清科", "AI服务器液冷产业链", "亨通光电", "HBM先进封装设备", "低空经济"];

export default function IndustryTrendPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [inputType, setInputType] = useState<InputType>("auto");
  const [loading, setLoading] = useState(false);
  const [errorText, setErrorText] = useState("");
  const [result, setResult] = useState<IndustryTrendPayload | null>(null);
  const [job, setJob] = useState<IndustryTrendPayload | null>(null);
  const [copied, setCopied] = useState(false);

  const resultLines = useMemo(() => splitAnswer(result?.answer || ""), [result?.answer]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || loading) return;
    const token = getAuthToken();
    if (!token) {
      router.push("/auth?redirect=/industry-trend");
      return;
    }

    setLoading(true);
    setErrorText("");
    setResult(null);
    setJob(null);
    try {
      const response = await fetch(`${API_BASE}/api/industry-trend`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ query: trimmed, input_type: inputType }),
        cache: "no-store",
      });
      const text = await response.text();
      const payload = text ? (JSON.parse(text) as IndustryTrendPayload) : {};
      if (!response.ok) throw new Error(payload.error || payload.detail || "产业趋势分析失败");
      setJob(payload);
      const donePayload = payload.status === "done" ? payload : await pollIndustryTrend(payload, token);
      if (donePayload.user) storeUser(donePayload.user);
      setResult(donePayload);
      setJob(donePayload);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : "产业趋势分析失败");
    } finally {
      setLoading(false);
    }
  }

  async function copyResult() {
    if (!result?.answer) return;
    await navigator.clipboard.writeText(result.answer);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  return (
    <main className="review-workbench-page industry-trend-page">
      <MainSidebar
        activeKey="industry-trend"
        note="先在本地启动 Stock Analyze：.\\start.ps1 -StockSkill -Port 8750，再输入产业链或个股。"
      />

      <section className="review-workbench-main">
        <header className="review-workbench-topbar">
          <div className="review-topbar-title">
            <span className="topbar-icon"><GitBranch /></span>
            <b>产业趋势</b>
            <i>INDUSTRY</i>
          </div>
          <div className="review-workbench-actions">
            <button type="button" onClick={() => router.push("/")}>首页</button>
          </div>
        </header>

        <section className="review-workbench-hero industry-trend-hero">
          <div className="review-hero-copy">
            <p className="review-kicker">LOCAL STOCK ANALYZE</p>
            <h1>输入产业链或个股，拆出利润流向和核心资产。</h1>
            <p>后端会调用本地 Stock Analyze 服务，使用 stock-reverse-engineering skill 输出产业链位置、瓶颈节点、三高评分和候选公司定位。</p>
          </div>

          <form className="research-panel industry-trend-form" onSubmit={submit}>
            <label>
              <span>分析对象</span>
              <textarea
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="例如：华海清科、AI服务器液冷产业链、HBM先进封装设备"
                rows={5}
                disabled={loading}
              />
            </label>

            <div className="industry-type-toggle" aria-label="输入类型">
              {[
                ["auto", "自动识别"],
                ["chain", "产业链"],
                ["stock", "个股"],
              ].map(([value, label]) => (
                <button
                  className={inputType === value ? "active" : ""}
                  type="button"
                  key={value}
                  onClick={() => setInputType(value as InputType)}
                  disabled={loading}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="industry-example-row">
              {examples.map((item) => (
                <button type="button" key={item} onClick={() => setQuery(item)} disabled={loading}>
                  {item}
                </button>
              ))}
            </div>

            <button className="primary-gold-action" type="submit" disabled={loading || !query.trim()}>
              {loading ? <Loader2 className="spin-icon" /> : <Sparkles />}
              {loading ? "正在调用 Stock Analyze" : "生成产业趋势分析"}
            </button>

            {loading ? (
              <div className="generation-progress" role="status" aria-live="polite">
                <div className="generation-progress-head">
                  <b>{job?.status === "queued" ? "产业链分析排队中" : "产业链分析生成中"}</b>
                  <span>{job?.stage || "Stock Analyze"}</span>
                </div>
                <div className="generation-progress-track" aria-hidden="true">
                  <i style={{ width: job?.status === "queued" ? "28%" : "64%" }} />
                </div>
                <p>后台任务正在运行，页面会自动轮询完整结果；成功生成后扣除 1 次使用机会。</p>
              </div>
            ) : null}

            {errorText ? (
              <div className="upload-error">
                <b>生成失败</b>
                <span>{errorText}</span>
              </div>
            ) : null}
          </form>
        </section>

        <section className="research-panel industry-trend-setup">
          <Network />
          <div>
            <b>本地链路</b>
            <span>Stock Analyze 默认监听 8750：在另一个 PowerShell 里运行 `.\start.ps1 -StockSkill -Port 8750`。</span>
          </div>
        </section>

        {result ? (
          <section className="research-panel industry-result-panel">
            <div className="industry-result-head">
              <div>
                <span className="card-label">{result.source || "stock-analyze"}</span>
                <h2>{result.query || query}</h2>
                <p>耗时 {result.elapsed_seconds ?? "-"} 秒 · 类型 {result.input_type || inputType} · {billingText(result.billing_status)}</p>
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
        ) : (
          <section className="research-panel industry-empty-panel">
            <ArrowRight />
            <b>等待输入产业链或个股</b>
            <span>适合分析：AI服务器、液冷、光模块、先进封装、华海清科、亨通光电等。</span>
          </section>
        )}
      </section>
    </main>
  );
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
  throw new Error("产业趋势分析仍在生成，请稍后重试。");
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
