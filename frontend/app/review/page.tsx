"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  BarChart3,
  BellRing,
  Camera,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  ClipboardCheck,
  FileSpreadsheet,
  FileText,
  FileUp,
  Globe2,
  Info,
  LineChart,
  Loader2,
  LockKeyhole,
  Radar,
  RefreshCw,
  ScanLine,
  ShieldCheck,
  Target,
  Upload,
} from "lucide-react";

type ReportPayload = {
  run_id?: string;
  status?: "queued" | "running" | "done" | "error";
  status_url?: string;
  count?: number;
  index_url?: string;
  debug_url?: string;
  presenter_url?: string;
  requested_research_model_tier?: string;
  research_model_tier?: string;
  actual_research_model_tier?: string;
  wang_model?: string;
  reports?: Array<{ url?: string; debug_url?: string; presenter_url?: string; title?: string; score?: number; rating?: string; requested_research_model_tier?: string; research_model_tier?: string; actual_research_model_tier?: string }>;
  error?: string;
  detail?: string;
  request_id?: string;
  stage?: string;
  code?: string;
  retryable?: boolean;
};

type AgentSummaryData = {
  company?: {
    code?: string;
    name?: string;
    theme?: string;
    sector?: string;
  };
  hero?: {
    industry_rating?: string;
    investment_rating?: string;
    tags?: string[];
    claims?: string[];
  };
  profit_flow?: {
    value_pool?: string;
    company_position?: string;
    why_profit_flows_here?: string;
    items?: Array<{ name?: string; share_pct?: number; highlight?: boolean }>;
  };
  expectation_gap?: {
    market_believes?: string[];
    analyst_view?: string[];
    gap_score?: number;
    underestimated?: string;
    overestimated?: string;
  };
  action?: {
    current_action?: string;
    status_tags?: string[];
    recheck_conditions?: string[];
    suitable_for?: string;
    not_suitable_for?: string;
  };
  trade_review?: {
    trade_return_pct?: number;
    trade_score?: number;
    buy_verdict?: string;
    sell_verdict?: string;
    execution_lesson?: string;
  };
  risks?: Array<{ name?: string; why_it_matters?: string; impact_pct?: number; downgrade_action?: string }>;
  logic_tree?: Array<{ node?: string; certainty_pct?: number }>;
  validation_panel?: Array<{ status?: string; item?: string; evidence?: string }>;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";
const STANDARD_REPORT_LABEL = "快速报告";
const BETTER_REPORT_LABEL = "更详细的报告";
const BETTER_FALLBACK_LABEL = "更详细的报告失败，已使用快速报告";

const copy = {
  navLabel: "\u6838\u5fc3\u529f\u80fd",
  review: "AI \u590d\u76d8",
  reviewSub: "\u4ea4\u6613\u8bb0\u5f55\u5230\u590d\u76d8\u62a5\u544a",
  watch: "AI \u76ef\u76d8",
  watchSub: "\u9884\u6848\u3001\u89e6\u53d1\u548c\u63d0\u9192",
  railNote: "\u5148\u590d\u76d8\u5f62\u6210\u4ea4\u6613\u89c4\u5219\uff0c\u518d\u628a\u89c4\u5219\u6c89\u6dc0\u4e3a\u76ef\u76d8\u9884\u6848\u3002",
  pageTitle: "AI \u590d\u76d8\u5206\u6790",
  helpSoon: "\u5e2e\u52a9\u6587\u6863\u7a0d\u540e\u63a5\u5165\u3002",
  noNotice: "\u6682\u65e0\u65b0\u901a\u77e5\u3002",
  heroTitle: "\u628a\u6bcf\u4e00\u7b14\u4ea4\u6613\uff0c\u62c6\u6210\u53ef\u6539\u8fdb\u7684\u80fd\u529b\u3002",
  heroDesc:
    "\u4e0a\u4f20\u4ea4\u5272\u5355\u6216\u622a\u56fe\uff0c\u7cfb\u7edf\u4f1a\u8bc6\u522b\u4e70\u5356\u8bb0\u5f55\uff0c\u8c03\u7528\u884c\u60c5\u4e0e\u6295\u7814 Agent\uff0c\u751f\u6210\u80fd\u770b\u61c2\u3001\u80fd\u590d\u76d8\u3001\u80fd\u6c89\u6dc0\u89c4\u5219\u7684\u62a5\u544a\u3002",
  workflowTitle: "\u4ea4\u5272\u5355 \u2192 \u4ea4\u6613\u4e8b\u5b9e \u2192 \u5e02\u573a\u73af\u5883 \u2192 \u590d\u76d8\u7ed3\u8bba",
  workflowDesc:
    "上传后系统会识别交易事实，调用正式 AI 复盘 Agent，并生成可打开的复盘报告。",
  uploadTitle: "\u4e0a\u4f20\u4ea4\u5272\u5355 / \u4ea4\u6613\u622a\u56fe",
  uploadReady: "\u4ea4\u5272\u5355\u5df2\u5c31\u7eea",
  uploadDesc:
    "\u70b9\u51fb\u4e0a\u4f20\u533a\u57df\u6216\u4e0b\u65b9\u6309\u94ae\u9009\u62e9\u6587\u4ef6\uff0c\u7cfb\u7edf\u4f1a\u7acb\u5373\u8bc6\u522b\u4ea4\u6613\u8bb0\u5f55\u5e76\u751f\u6210\u590d\u76d8\u62a5\u544a\u3002",
  formatHint: "\u652f\u6301\u683c\u5f0f\uff1aExcel\u3001CSV\u3001TXT\u3001\u622a\u56fe OCR",
  chooseFile: "\u9009\u62e9\u6587\u4ef6\u4e0a\u4f20",
  generate: "\u751f\u6210\u62a5\u544a",
  generating: "\u6b63\u5728\u751f\u6210\u62a5\u544a",
  reselect: "\u91cd\u65b0\u9009\u62e9",
  errorTitle: "\u62a5\u544a\u751f\u6210\u5931\u8d25",
  privacy:
    "\u6587\u4ef6\u4ec5\u7528\u4e8e\u672c\u6b21\u5206\u6790\uff1b\u5efa\u8bae\u4e0a\u4f20\u5b8c\u6574\u6210\u4ea4\u65f6\u95f4\u3001\u65b9\u5411\u3001\u4ef7\u683c\u3001\u6570\u91cf\u548c\u8d39\u7528\u3002",
  reportQuestion: "\u62a5\u544a\u5c06\u56de\u7b54\u4ec0\u4e48\uff1f",
  modulesTitle: "\u590d\u76d8\u4e0d\u662f\u8bb0\u8d26\uff0c\u662f\u628a\u4ea4\u6613\u80fd\u529b\u62c6\u5f00\u8bad\u7ec3\u3002",
  reportTitle: "AI复盘结果",
  reportDesc: "\u70b9\u51fb\u67e5\u770b\u62a5\u544a\u540e\uff0c\u4f1a\u5728\u5f53\u524d\u5e94\u7528\u5185\u6253\u5f00\u62a5\u544a\u8be6\u60c5\u9875\u3002",
  openNew: "\u67e5\u770b\u62a5\u544a",
  openBrowser: "\u6253\u5f00\u62a5\u544a",
  accepted: "\u4ea4\u5272\u5355\u5df2\u63a5\u6536\uff0c\u53ef\u4ee5\u751f\u6210\u62a5\u544a\u3002",
  calling: "\u6b63\u5728\u8c03\u7528\u540e\u7aef Agent \u751f\u6210\u771f\u5b9e\u62a5\u544a\u3002",
  modeFast: "快速报告",
  modeFastDesc: "只生成前端需要的研究 JSON，速度优先。",
  modeDetail: "更详细的报告",
  modeDetailDesc: "生成研究 JSON，并附加更长 memo。",
  done: "\u62a5\u544a\u5df2\u751f\u6210\uff0c\u6b63\u5728\u8fdb\u5165\u8be6\u60c5\u9875\u3002",
  reset: "\u5df2\u56de\u5230\u4e0a\u4f20\u72b6\u6001\u3002",
  noUrl: "\u540e\u7aef\u5df2\u8fd4\u56de\u7ed3\u679c\uff0c\u4f46\u6ca1\u6709\u62a5\u544a URL\u3002",
  fallbackError: "\u62a5\u544a\u751f\u6210\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u540e\u7aef\u670d\u52a1\u3002",
};

const workflow = [
  { icon: Upload, title: "\u4e0a\u4f20", text: "\u63d0\u4ea4\u4ea4\u5272\u5355\u6216\u622a\u56fe" },
  { icon: ScanLine, title: "\u8bc6\u522b", text: "AI \u8bc6\u522b\u4ea4\u6613\u7ec6\u8282" },
  { icon: LineChart, title: "\u7814\u7a76", text: "\u591a\u7ef4\u5ea6\u5206\u6790\u4ea4\u6613\u8868\u73b0" },
  { icon: ClipboardCheck, title: "\u62a5\u544a", text: "\u751f\u6210\u53ef\u6267\u884c\u62a5\u544a" },
];
const formats = [
  { icon: FileSpreadsheet, label: "Excel (.xlsx)" },
  { icon: FileSpreadsheet, label: "CSV (.csv)" },
  { icon: FileText, label: "TXT (.txt)" },
  { icon: Camera, label: "\u622a\u56fe OCR" },
];
const reportBlocks = [
  "\u8fd9\u7b14\u4ea4\u6613\u7684\u6574\u4f53\u8868\u73b0\u5982\u4f55\uff1f\u6536\u76ca\u6765\u6e90\u4e0e\u4e8f\u635f\u539f\u56e0\u5206\u522b\u662f\u4ec0\u4e48\uff1f",
  "\u6211\u7684\u4ea4\u6613\u6267\u884c\u662f\u5426\u5b58\u5728\u7cfb\u7edf\u6027\u95ee\u9898\uff1f",
  "\u5e02\u573a\u73af\u5883\u5982\u4f55\u5f71\u54cd\u4e86\u8fd9\u7b14\u4ea4\u6613\u7684\u7ed3\u679c\uff1f",
  "\u57fa\u4e8e\u5386\u53f2\u6570\u636e\uff0c\u6211\u7684\u7b56\u7565\u671f\u671b\u503c\u662f\u591a\u5c11\uff1f",
  "\u6211\u4e0b\u4e00\u6b65\u5e94\u8be5\u5982\u4f55\u8c03\u6574\u548c\u6539\u8fdb\uff1f",
];

const capabilityCards = [
  {
    icon: BarChart3,
    title: "\u4ea4\u6613\u7ee9\u6548\u5206\u6790",
    text: "\u6536\u76ca\u3001\u80dc\u7387\u3001\u76c8\u4e8f\u6bd4\u7b49",
  },
  {
    icon: ShieldCheck,
    title: "\u98ce\u9669\u5206\u6790",
    text: "\u56de\u64a4\u3001\u6ce2\u52a8\u7387\u3001\u98ce\u9669\u66b4\u9732\u7b49",
  },
  {
    icon: Radar,
    title: "\u884c\u4e3a\u5206\u6790",
    text: "\u6301\u4ed3\u65f6\u95f4\u3001\u6b62\u635f\u6267\u884c\u3001\u60c5\u7eea\u504f\u5dee\u7b49",
  },
  {
    icon: Globe2,
    title: "\u5e02\u573a\u73af\u5883\u5206\u6790",
    text: "\u5b8f\u89c2\u3001\u884c\u4e1a\u3001\u5e02\u573a\u72b6\u6001\u5f71\u54cd",
  },
  {
    icon: Target,
    title: "\u7b56\u7565\u8bc4\u4f30",
    text: "\u7b56\u7565\u6709\u6548\u6027\u3001\u7a33\u5b9a\u6027\u3001\u671f\u671b\u503c",
  },
  {
    icon: ClipboardCheck,
    title: "\u6539\u8fdb\u5efa\u8bae",
    text: "\u9488\u5bf9\u6027\u6539\u8fdb\u8ba1\u5212\u4e0e\u884c\u52a8\u6e05\u5355",
  },
];

export default function ReviewPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const reportPanelRef = useRef<HTMLElement | null>(null);
  const toastTimer = useRef<number | null>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [generating, setGenerating] = useState(false);
  const [reportUrl, setReportUrl] = useState("");
  const [reportRoute, setReportRoute] = useState("");
  const [agentSummaryUrl, setAgentSummaryUrl] = useState("");
  const [agentSummaryData, setAgentSummaryData] = useState<AgentSummaryData | null>(null);
  const [agentSummaryLoading, setAgentSummaryLoading] = useState(false);
  const [reportCount, setReportCount] = useState(0);
  const [researchModelTier, setResearchModelTier] = useState<"standard" | "better">("standard");
  const [researchModelLabel, setResearchModelLabel] = useState(STANDARD_REPORT_LABEL);
  const [errorText, setErrorText] = useState("");
  const [toast, setToast] = useState("");
  const [isDragging, setIsDragging] = useState(false);

  const reportReady = Boolean(reportUrl);

  function showToast(text: string) {
    setToast(text);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(""), 2600);
  }

  function openFilePicker() {
    if (!generating) inputRef.current?.click();
  }

  function handleUploadStageKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openFilePicker();
    }
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    acceptFile(file);
  }

  function acceptFile(file?: File) {
    if (!file) return;
    setSelectedFile(file);
    setReportUrl("");
    setReportRoute("");
    setAgentSummaryUrl("");
    setAgentSummaryData(null);
    setReportCount(0);
    setResearchModelLabel(selectedResearchModelLabel());
    setErrorText("");
    showToast(copy.accepted);
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    acceptFile(event.dataTransfer.files?.[0]);
  }

  async function parseJsonResponse(response: Response): Promise<ReportPayload> {
    const text = await response.text();
    if (!text) return {};
    try {
      return JSON.parse(text) as ReportPayload;
    } catch {
      return { error: text };
    }
  }

  function selectedResearchModelLabel() {
    return researchModelTier === "better" ? BETTER_REPORT_LABEL : STANDARD_REPORT_LABEL;
  }

  function normalizePayloadTier(value?: string) {
    return value === "better" ? "better" : "standard";
  }

  function formatResearchModelLabel(payload: ReportPayload) {
    const firstReport = payload.reports?.[0];
    const requested = normalizePayloadTier(
      payload.requested_research_model_tier || firstReport?.requested_research_model_tier || researchModelTier,
    );
    const actual = normalizePayloadTier(
      payload.actual_research_model_tier ||
        payload.research_model_tier ||
        firstReport?.actual_research_model_tier ||
        firstReport?.research_model_tier ||
        requested,
    );
    if (requested === "better" && actual !== "better") return BETTER_FALLBACK_LABEL;
    return actual === "better" ? BETTER_REPORT_LABEL : STANDARD_REPORT_LABEL;
  }

  function formatReportError(payload: ReportPayload, fallback: string) {
    const lines = [payload.error || fallback];
    if (payload.detail && payload.detail !== payload.error) lines.push(payload.detail);
    const meta = [
      payload.code ? `code: ${payload.code}` : "",
      payload.stage ? `stage: ${payload.stage}` : "",
      payload.request_id ? `request: ${payload.request_id}` : "",
      payload.run_id ? `run: ${payload.run_id}` : "",
    ]
      .filter(Boolean)
      .join(" | ");
    if (meta) lines.push(meta);
    return lines.join("\n");
  }

  function isPendingReport(payload: ReportPayload) {
    return payload.status === "queued" || payload.status === "running";
  }

  async function pollReportStatus(statusUrl: string): Promise<ReportPayload> {
    const target = statusUrl.startsWith("http") ? statusUrl : `${API_BASE}${statusUrl}`;
    for (let attempt = 0; attempt < 240; attempt += 1) {
      const response = await fetch(target, { cache: "no-store" });
      const payload = await parseJsonResponse(response);
      if (!response.ok) throw new Error(formatReportError(payload, copy.errorTitle));
      if (payload.status === "done") return payload;
      if (payload.status === "error") throw new Error(formatReportError(payload, copy.errorTitle));
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
    }
    throw new Error("\u62a5\u544a\u751f\u6210\u8d85\u65f6\uff0c\u8bf7\u7a0d\u540e\u5237\u65b0\u62a5\u544a\u5217\u8868\u3002");
  }

  async function generateReport() {
    if (!selectedFile) {
      openFilePicker();
      return;
    }
    if (generating) return;

    setGenerating(true);
    setErrorText("");
    setReportUrl("");
    setAgentSummaryUrl("");
    setAgentSummaryData(null);
    setReportCount(0);
    showToast(copy.calling);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("research_model_tier", researchModelTier);

      const response = await fetch(`${API_BASE}/api/reports`, {
        method: "POST",
        body: formData,
      });
      let payload = await parseJsonResponse(response);

      if (!response.ok) {
        throw new Error(formatReportError(payload, copy.errorTitle));
      }

      if (isPendingReport(payload) && payload.status_url) {
        showToast("\u62a5\u544a\u751f\u6210\u4e2d\uff0c\u6b63\u5728\u8bfb\u53d6\u7814\u7a76\u7ed3\u679c\u3002");
        payload = await pollReportStatus(payload.status_url);
      }

      if (payload.status === "error") {
        throw new Error(formatReportError(payload, copy.errorTitle));
      }

      const firstReport = payload.reports?.[0];
      const firstReportUrl = firstReport?.url || payload.index_url;
      if (!firstReportUrl) throw new Error(copy.noUrl);

      const reportId = payload.run_id || extractReportId(firstReportUrl);
      if (!reportId) throw new Error(copy.noUrl);

      const nextReportRoute = `/review/report/${encodeURIComponent(reportId)}`;
      const structuredUrl =
        firstReport?.presenter_url ||
        payload.presenter_url ||
        firstReport?.debug_url ||
        payload.debug_url ||
        "";
      setReportUrl(`${API_BASE}${firstReportUrl}`);
      setReportRoute(nextReportRoute);
      setAgentSummaryUrl(structuredUrl ? `${API_BASE}${structuredUrl}` : "");
      setReportCount(payload.count || payload.reports?.length || 1);
      setResearchModelLabel(formatResearchModelLabel(payload));
      if (structuredUrl) {
        setAgentSummaryLoading(true);
        try {
          const structuredResponse = await fetch(`${API_BASE}${structuredUrl}`, { cache: "no-store" });
          if (structuredResponse.ok) {
            setAgentSummaryData((await structuredResponse.json()) as AgentSummaryData);
          }
        } catch {
          setAgentSummaryData(null);
        } finally {
          setAgentSummaryLoading(false);
        }
      }
      showToast(copy.done);
      router.push(nextReportRoute);
    } catch (error) {
      const message = error instanceof Error ? error.message : copy.fallbackError;
      setErrorText(message);
      showToast(message);
    } finally {
      setGenerating(false);
    }
  }

  function resetUpload() {
    setSelectedFile(null);
    setReportUrl("");
    setReportRoute("");
    setAgentSummaryUrl("");
    setAgentSummaryData(null);
    setReportCount(0);
    setResearchModelLabel(selectedResearchModelLabel());
    setErrorText("");
    if (inputRef.current) inputRef.current.value = "";
    showToast(copy.reset);
  }

  function openReportDetail() {
    if (reportRoute) router.push(reportRoute);
  }


  return (
    <main className="review-console-page">
      <aside className="review-console-rail">
        <Link className="review-console-brand" href="/">
          <span className="brand-mark">{"\u76c8"}</span>
          <span>
            <b>{"\u76c8\u822a"}</b>
            <small>REVIEW TERMINAL</small>
          </span>
        </Link>
        <nav className="review-console-nav" aria-label={copy.navLabel}>
          <Link className="active" href="/review">
            <FileUp />
            <span><b>{copy.review}</b></span>
          </Link>
          <Link href="/watch">
            <BarChart3 />
            <span><b>{copy.watch}</b></span>
          </Link>
        </nav>
        <div className="review-rail-note">
          <Info />
          <span>{copy.railNote}</span>
        </div>
      </aside>
      <section className="review-console-main">
        <header className="review-console-topbar">
          <div className="review-topbar-title">
            <span className="topbar-icon"><FileUp /></span>
            <b>{copy.pageTitle}</b>
            <i>BETA</i>
          </div>
          <div className="review-console-actions">
            <button type="button" onClick={() => showToast(copy.helpSoon)} aria-label="help"><CircleHelp /><span>{"\u5e2e\u52a9"}</span></button>
            <button type="button" onClick={() => showToast(copy.noNotice)} aria-label="notice"><BellRing /><span>{"\u901a\u77e5"}</span></button>
          </div>
        </header>
        <section className="review-console-hero">
          <div className="review-hero-copy">
            <p className="review-kicker">AI REVIEW AGENT</p>
            <h1>
              {"AI \u590d\u76d8\u5206\u6790"}
              <br />
              {"\u4ea4\u6613\u7814\u7a76\u5de5\u4f5c\u53f0"}
            </h1>
            <p>{copy.heroDesc}</p>
            <div className="review-hero-actions">
              <button className="hero-primary-upload" type="button" onClick={openFilePicker} disabled={generating}>
                <Upload />
                {copy.chooseFile}
              </button>
              <span>{copy.formatHint}</span>
            </div>
          </div>
          <section className="research-panel upload-research-panel hero-upload-card">
            <input
              ref={inputRef}
              type="file"
              hidden
              accept=".xls,.xlsx,.csv,.txt,image/*"
              onChange={handleFileChange}
            />
            <div
              className={`upload-stage ${isDragging ? "is-dragging" : ""}`}
              onClick={openFilePicker}
              onDragEnter={(event) => {
                event.preventDefault();
                setIsDragging(true);
              }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onKeyDown={handleUploadStageKeyDown}
              role="button"
              tabIndex={0}
            >
              <FileUp />
              <h2>{selectedFile ? copy.uploadReady : "\u62d6\u62fd\u6216\u70b9\u51fb\u4e0a\u4f20\u4ea4\u5272\u5355\u4e0e\u4ea4\u6613\u622a\u56fe"}</h2>
              <p>
                {selectedFile
                  ? `${selectedFile.name} \u5df2\u8fdb\u5165\u8bc6\u522b\u6d41\u7a0b\u3002\u70b9\u51fb\u4e0b\u65b9\u6309\u94ae\u751f\u6210\u62a5\u544a\u3002`
                  : "\u6587\u4ef6\u5c06\u5728\u672c\u5730\u5904\u7406\uff0c\u7528\u4e8e\u751f\u6210\u672c\u6b21\u590d\u76d8\u62a5\u544a\u3002"}
              </p>
              <div className="upload-format-row">
                {formats.map((format) => {
                  const Icon = format.icon;
                  return (
                    <span key={format.label}>
                      <Icon />
                      {format.label}
                    </span>
                  );
                })}
              </div>
            </div>
            {selectedFile && (
              <>
                <div className="report-mode-toggle" aria-label="报告详细程度">
                  <button
                    className={researchModelTier === "standard" ? "active" : ""}
                    type="button"
                    onClick={() => setResearchModelTier("standard")}
                    disabled={generating}
                  >
                    <FileText />
                    <span>
                      <b>{copy.modeFast}</b>
                      <small>{copy.modeFastDesc}</small>
                    </span>
                  </button>
                  <button
                    className={researchModelTier === "better" ? "active" : ""}
                    type="button"
                    onClick={() => setResearchModelTier("better")}
                    disabled={generating}
                  >
                    <ClipboardCheck />
                    <span>
                      <b>{copy.modeDetail}</b>
                      <small>{copy.modeDetailDesc}</small>
                    </span>
                  </button>
                </div>
                <div className="upload-action-row">
                  <button className="primary-gold-action" type="button" onClick={generateReport} disabled={generating}>
                    {generating ? <Loader2 className="spin-icon" /> : <Upload />}
                    {generating ? copy.generating : copy.generate}
                  </button>
                  <button className="ghost-action" type="button" onClick={resetUpload} disabled={generating}>
                    <RefreshCw />
                    {copy.reselect}
                  </button>
                </div>
              </>
            )}
            {errorText && (
              <div className="upload-error">
                <b>{copy.errorTitle}</b>
                <span>{errorText}</span>
              </div>
            )}
            {selectedFile && (
              <div className="privacy-line">
                <LockKeyhole />
                <span>{copy.privacy}</span>
              </div>
            )}
          </section>
        </section>
        <section className="research-panel review-flow-panel">
          <b>{"\u590d\u76d8\u6d41\u7a0b"}</b>
          <div className="workflow-track">
            {workflow.map((item, index) => {
              const Icon = item.icon;
              return (
                <div className="workflow-node" key={item.title}>
                  <span><Icon /></span>
                  <strong>{item.title}</strong>
                  <small>{item.text}</small>
                  {index < workflow.length - 1 && <ChevronRight className="workflow-arrow" />}
                </div>
              );
            })}
          </div>
        </section>
        <section className="review-console-grid">
          <section className="research-panel report-outline-panel">
            <span className="card-label">{"\u62a5\u544a\u4f1a\u91cd\u70b9\u5206\u6790"}</span>
            <div className="report-analysis-layout">
              <div className="report-block-list">
                {reportBlocks.map((item) => (
                  <div className="report-block" key={item}>
                    <CheckCircle2 />
                    <b>{item}</b>
                  </div>
                ))}
              </div>
              <div className="review-radar-card" aria-hidden="true">
                <div className="radar-visual">
                  <span>{"\u4ea4\u6613\u7ee9\u6548"}</span>
                  <span>{"\u98ce\u9669\u66b4\u9732"}</span>
                  <span>{"\u884c\u4e3a\u504f\u5dee"}</span>
                  <span>{"\u7b56\u7565\u4e00\u81f4\u6027"}</span>
                  <span>{"\u5e02\u573a\u73af\u5883"}</span>
                </div>
              </div>
            </div>
          </section>
          <aside className="research-panel analysis-module-panel">
            <span className="card-label">{"\u5206\u6790\u6a21\u5757\u80fd\u529b"}</span>
            <div className="capability-grid">
              {capabilityCards.map((card) => {
                const Icon = card.icon;
                return (
                  <article className="capability-card" key={card.title}>
                    <Icon />
                    <div>
                      <h3>{card.title}</h3>
                      <p>{card.text}</p>
                    </div>
                  </article>
                );
              })}
            </div>
          </aside>
        </section>
        <div className="review-security-line">
          <LockKeyhole />
          <span>{"\u5168\u7a0b\u52a0\u5bc6\u4f20\u8f93 \u00b7 \u6587\u4ef6\u6700\u5c0f\u7559\u5b58 \u00b7 \u7ed3\u679c\u4ec5\u5f53\u524d\u4f1a\u8bdd\u53ef\u89c1"}</span>
        </div>
        {reportReady && (
          <section className="report-reader-section" ref={reportPanelRef}>
            <div className="report-reader-head">
              <div>
                <span><CheckCircle2 /> {`\u5df2\u751f\u6210 ${reportCount || 1} \u4efd\u62a5\u544a`}</span>
                <h2>{copy.reportTitle}</h2>
                <p>{copy.reportDesc} \u7814\u7a76\u6a21\u578b\uff1a{researchModelLabel}</p>
              </div>
              <button type="button" onClick={openReportDetail}>
                {copy.openNew} <ArrowRight />
              </button>
            </div>
            <AgentSummary data={agentSummaryData} loading={agentSummaryLoading} url={agentSummaryUrl} />
          </section>
        )}
      </section>
      <div className={`studio-toast ${toast ? "show" : ""}`}>{toast}</div>
    </main>
  );
}

function extractReportId(url?: string) {
  const match = url?.match(/\/api\/reports\/([^/]+)/);
  return match?.[1] || "";
}


function AgentSummary({ data, loading, url }: { data: AgentSummaryData | null; loading: boolean; url: string }) {
  if (loading) {
    return (
      <section className="agent-summary-panel">
        <div className="agent-summary-loading">
          <Loader2 className="spin-icon" />
          <span>{"\u6b63\u5728\u8bfb\u53d6\u7ed3\u6784\u5316\u7814\u7a76\u7ed3\u679c..."}</span>
        </div>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="agent-summary-panel is-empty">
        <span>{"\u7ed3\u6784\u5316\u7814\u7a76 JSON \u6682\u672a\u8fd4\u56de"}</span>
        {url && <a href={url} target="_blank" rel="noreferrer">{"\u67e5\u770b\u539f\u59cb JSON"}</a>}
      </section>
    );
  }

  const companyName = data.company?.name || "\u672a\u547d\u540d\u6807\u7684";
  const companyCode = data.company?.code || "";
  const themeOrSector = data.company?.theme || data.company?.sector || "";
  const claims = cleanList(data.hero?.claims).slice(0, 4);
  const tags = cleanList(data.hero?.tags).slice(0, 5);
  const profitItems = (data.profit_flow?.items || []).slice(0, 5);
  const logicTree = (data.logic_tree || []).slice(0, 6);
  const riskItems = (data.risks || []).slice(0, 3);
  const recheck = cleanList(data.action?.recheck_conditions).slice(0, 4);

  return (
    <section className="agent-summary-panel">
      <div className="agent-summary-hero">
        <div>
          <span className="card-label">Structured Research</span>
          <h3>{companyName}</h3>
          <p>{companyCode}{companyCode && themeOrSector ? " - " : ""}{themeOrSector}</p>
          <div className="agent-chip-row">
            {tags.map((tag) => <span key={tag}>{tag}</span>)}
          </div>
        </div>
        <div className="agent-rating-grid">
          <MetricCard label={"\u884c\u4e1a\u8bc4\u7ea7"} value={data.hero?.industry_rating || "-"} />
          <MetricCard label={"\u6295\u8d44\u8bc4\u7ea7"} value={data.hero?.investment_rating || "-"} />
          <MetricCard label={"\u4ea4\u6613\u8bc4\u5206"} value={formatValue(data.trade_review?.trade_score, "-")} />
          <MetricCard label={"\u9884\u671f\u5dee"} value={formatValue(data.expectation_gap?.gap_score, "-")} />
        </div>
      </div>

      <div className="agent-summary-grid">
        <article>
          <h4>{"\u6838\u5fc3\u7ed3\u8bba"}</h4>
          <ul className="cyan-bullets">
            {(claims.length ? claims : ["\u7b49\u5f85 Agent \u8fd4\u56de\u6838\u5fc3\u7ed3\u8bba\u3002"]).map((item) => <li key={item}>{item}</li>)}
          </ul>
        </article>

        <article>
          <h4>{"\u4ef7\u503c\u6d41\u5411"}</h4>
          <p>{data.profit_flow?.value_pool || "\u6682\u65e0\u4ef7\u503c\u6c60\u63cf\u8ff0\u3002"}</p>
          <div className="profit-flow-bars">
            {profitItems.map((item) => (
              <div className={item.highlight ? "highlight" : ""} key={`${item.name || "profit"}-${item.share_pct ?? "na"}`}>
                <span>{item.name || "\u672a\u547d\u540d\u73af\u8282"}</span>
                <b>{formatPct(item.share_pct)}</b>
                <i style={{ width: `${clampPct(item.share_pct)}%` }} />
              </div>
            ))}
          </div>
          {data.profit_flow?.company_position && <small>{data.profit_flow.company_position}</small>}
        </article>

        <article>
          <h4>{"\u4ea7\u4e1a\u903b\u8f91\u6811"}</h4>
          <div className="logic-tree-row">
            {logicTree.map((node, index) => (
              <div key={`${node.node}-${index}`}>
                <b>{node.node || `\u903b\u8f91\u8282\u70b9 ${index + 1}`}</b>
                <span>{formatPct(node.certainty_pct)}</span>
              </div>
            ))}
          </div>
        </article>

        <article>
          <h4>{"\u884c\u52a8\u4e0e\u590d\u6838"}</h4>
          <p>{data.action?.current_action || data.trade_review?.execution_lesson || "\u7b49\u5f85\u751f\u6210\u53ef\u6267\u884c\u52a8\u4f5c\u3002"}</p>
          <ul>
            {recheck.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </article>

        <article>
          <h4>{"\u98ce\u9669\u70b9"}</h4>
          <ul>
            {riskItems.map((risk) => (
              <li key={risk.name || risk.why_it_matters}>
                <b>{risk.name || "\u98ce\u9669\u9879"}</b>
                <span>{risk.why_it_matters || risk.downgrade_action}</span>
              </li>
            ))}
          </ul>
        </article>

        <article>
          <h4>{"\u4e70\u5356\u70b9\u590d\u76d8"}</h4>
          <p>{data.trade_review?.buy_verdict || "\u4e70\u70b9\u7ed3\u8bba\u5f85\u8865\u5145\u3002"}</p>
          <p>{data.trade_review?.sell_verdict || "\u5356\u70b9\u7ed3\u8bba\u5f85\u8865\u5145\u3002"}</p>
          {typeof data.trade_review?.trade_return_pct === "number" && (
            <strong>{formatPct(data.trade_review.trade_return_pct)} {"\u6301\u6709\u6536\u76ca"}</strong>
          )}
        </article>
      </div>
    </section>
  );
}
function MetricCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="agent-metric-card">
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

function cleanList(items?: string[]) {
  return (items || []).map((item) => item.trim()).filter(Boolean);
}

function formatValue(value: unknown, fallback: string) {
  if (typeof value === "number" && Number.isFinite(value)) return String(Math.round(value));
  if (typeof value === "string" && value.trim()) return value;
  return fallback;
}

function formatPct(value: unknown) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return `${Math.round(value)}%`;
}

function clampPct(value: unknown) {
  if (typeof value !== "number" || !Number.isFinite(value)) return 8;
  return Math.max(4, Math.min(100, value));
}

