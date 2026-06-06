"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import {
  BarChart3,
  Bell,
  BriefcaseBusiness,
  CircleGauge,
  CircleHelp,
  FileText,
  FileUp,
  Lightbulb,
  ListChecks,
  LockKeyhole,
  Radar,
  Route,
  Shuffle,
  Sparkles,
  Triangle,
  Upload,
} from "lucide-react";

type IconComponent = typeof BarChart3;

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

const reportFeatures: Array<[IconComponent, string, string]> = [
  [BarChart3, "整体表现概览", "收益率、胜率、盈亏比等关键指标"],
  [Route, "交易行为分析", "持仓时间、交易频率、品种偏好分析"],
  [Shuffle, "盈亏原因分析", "AI 深度分析盈利和亏损的原因"],
  [ListChecks, "改进建议", "个性化的交易策略优化建议"],
  [CircleGauge, "对比分析", "与历史数据或市场基准对比"],
];

const recentReports = [
  ["交割单_2024年5月.xlsx", "2024-05-20 14:30", "已完成"],
  ["交易记录_0428.pdf", "2024-04-28 10:15", "已完成"],
  ["交割单_2024年4月.xlsx", "2024-04-20 16:45", "分析中"],
];

export default function ReviewPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const reportPanelRef = useRef<HTMLElement>(null);
  const [uploadTitle, setUploadTitle] = useState("上传交割单 / 交易记录");
  const [uploadHint, setUploadHint] = useState("支持多种格式文件，AI 将自动识别并生成复盘报告");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [generating, setGenerating] = useState(false);
  const [reportGenerated, setReportGenerated] = useState(false);
  const [reportUrl, setReportUrl] = useState("");
  const [reportCount, setReportCount] = useState(0);
  const [toast, setToast] = useState("");
  const timer = useRef<number>();

  function showToast(text: string) {
    setToast(text);
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast(""), 2600);
  }

  function resetUpload() {
    setSelectedFile(null);
    setGenerating(false);
    setReportGenerated(false);
    setReportUrl("");
    setReportCount(0);
    setUploadTitle("上传交割单 / 交易记录");
    setUploadHint("支持多种格式文件，AI 将自动识别并生成复盘报告");
    if (inputRef.current) inputRef.current.value = "";
    showToast("已回到上传入口。");
  }

  async function handleUploadZoneClick() {
    if (!selectedFile) {
      inputRef.current?.click();
      return;
    }
    if (generating) return;
    if (reportGenerated && reportUrl) {
      reportPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }

    setGenerating(true);
    setReportGenerated(false);
    setReportUrl("");
    setReportCount(0);
    setUploadTitle("文件已上传，AI 正在分析");
    setUploadHint(`${selectedFile.name} 正在结构化识别并对齐行情数据`);
    showToast("正在调用本地后端生成真实复盘报告。");

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      const response = await fetch(`${API_BASE}/api/reports`, {
        method: "POST",
        body: formData,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || payload.detail || "报告生成失败");
      }

      const count = payload.count || 1;
      setReportUrl(`${API_BASE}${payload.index_url}`);
      setReportCount(count);
      setGenerating(false);
      setReportGenerated(true);
      showToast("报告已生成，当前页面已切换为报告阅读模式。");
      window.setTimeout(() => reportPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 120);
    } catch (error) {
      setGenerating(false);
      setReportGenerated(false);
      setReportUrl("");
      setReportCount(0);
      setUploadTitle("报告生成失败");
      setUploadHint(error instanceof Error ? error.message : "请确认本地 API 服务已启动。");
      showToast(error instanceof Error ? error.message : "报告生成失败，请检查后端服务。");
    }
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    setGenerating(false);
    setReportGenerated(false);
    setReportUrl("");
    setReportCount(0);
    setUploadTitle("文件已上传，准备生成报告");
    setUploadHint(`${file.name} 已进入结构化识别流程`);
    showToast("交割单已接收，可以生成复盘报告。");
  }

  const actionText = !selectedFile
    ? "选择文件上传"
    : generating
      ? "正在生成报告"
      : "生成报告";
  const reportReady = reportGenerated && reportUrl;

  return (
    <main className="review-entry review-entry-dashboard">
      <aside className="review-entry-sidebar">
        <Link className="review-entry-brand" href="/">
          <span><Triangle /></span>
          <b>AI Trading</b>
          <em>Pro</em>
        </Link>

        <nav className="review-entry-menu review-function-cards" aria-label="核心功能">
          <Link className="active" href="/review">
            <BriefcaseBusiness />
            <span>
              <b>AI 复盘</b>
              <small>上传交割单，生成交易复盘</small>
            </span>
          </Link>
          <Link href="/watch">
            <Radar />
            <span>
              <b>AI 盯盘</b>
              <small>把复盘结论变成盘中预案</small>
            </span>
          </Link>
        </nav>

        <div className="review-side-hint">上传交割单生成复盘，再把关键结论沉淀成盯盘预案。</div>
      </aside>

      <section className="review-entry-main">
        <header className="review-entry-topbar">
          <button onClick={() => showToast("帮助中心稍后接入。")} aria-label="帮助"><CircleHelp /></button>
          <button onClick={() => showToast("暂无新通知。")} aria-label="通知"><Bell /></button>
          <button className="review-upgrade" onClick={() => showToast("会员能力后续接入支付与权益系统。")}>升级会员</button>
        </header>

        {reportReady ? (
          <section className="review-full-report" ref={reportPanelRef}>
            <div className="review-full-report-head">
              <div>
                <span>AI Review Report</span>
                <h1>复盘报告已生成</h1>
                <p>本次上传生成了 {reportCount || 1} 份报告。当前页面已经切换成报告阅读模式，不需要打开新页面。</p>
              </div>
              <div className="review-full-report-actions">
                <button onClick={resetUpload}>重新上传</button>
                <a href={reportUrl} target="_blank" rel="noreferrer">新窗口打开</a>
              </div>
            </div>
            <iframe className="review-full-report-frame" src={reportUrl} title="复盘报告" />
          </section>
        ) : (
          <>
            <section className="review-entry-hero">
              <h1>AI 复盘分析 <Sparkles /></h1>
              <p>上传您的交割单，AI 将为您深度分析交易表现，发现优势与改进空间</p>
            </section>

            <section className="review-entry-content">
              <section className="review-entry-panel review-upload-panel">
                <input
                  ref={inputRef}
                  type="file"
                  hidden
                  accept=".pdf,.xls,.xlsx,.csv,.txt,image/*"
                  onChange={handleFileChange}
                />
                <button className="review-upload-zone" onClick={handleUploadZoneClick}>
                  <FileUp />
                  <b>{uploadTitle}</b>
                  <span>{uploadHint}</span>
                  <strong><Upload />{actionText}</strong>
                  <small>支持格式：PDF、Excel（.xlsx / .xls）、CSV、截图图片 OCR<br />文件大小不超过 50MB</small>
                </button>
                <div className="review-privacy"><LockKeyhole />您的文件仅用于分析，不会被存储或泄露，请放心上传</div>

                <section className="review-recent">
                  <h2>最近复盘记录</h2>
                  {recentReports.map(([name, date, status]) => (
                    <div className="review-record" key={name}>
                      <FileText />
                      <div>
                        <b>{name}</b>
                        <small>{date}</small>
                      </div>
                      <span className={status === "分析中" ? "pending" : ""}>{status}</span>
                      <button onClick={() => showToast("历史报告列表稍后接入真实账户。")}>
                        {status === "分析中" ? "..." : "查看报告"}
                      </button>
                    </div>
                  ))}
                  <button className="review-all-records" onClick={() => showToast("全部记录稍后接入。")}>查看全部记录 →</button>
                </section>
              </section>

              <aside className={`review-right-stack ${generating ? "has-report" : ""}`}>
                {generating ? (
                  <section className="review-entry-panel review-report-panel review-report-loading" ref={reportPanelRef}>
                    <div className="review-report-orbit">
                      <span />
                      <span />
                      <span />
                    </div>
                    <h2>正在生成复盘报告</h2>
                    <p>后端正在读取交割单、对齐行情、生成黑金 visual report。稍等一下，报告会直接覆盖当前页面。</p>
                  </section>
                ) : (
                  <>
                    <section className="review-entry-panel review-how">
                      <h2>AI 如何帮您复盘？</h2>
                      {[
                        ["1", "上传交割单", "支持 PDF / Excel / CSV 格式的交割单或交易记录"],
                        ["2", "AI 智能分析", "AI 识别交易数据，分析您的交易表现"],
                        ["3", "生成复盘报告", "多维度分析报告，提供可执行的改进建议"],
                      ].map(([num, title, text]) => (
                        <div className="review-step" key={num}><span>{num}</span><div><b>{title}</b><p>{text}</p></div></div>
                      ))}
                    </section>

                    <section className="review-entry-panel review-include">
                      <h2>报告将包含</h2>
                      {reportFeatures.map(([FeatureIcon, title, text]) => (
                        <div className="review-feature" key={title}>
                          <FeatureIcon />
                          <div><b>{title}</b><p>{text}</p></div>
                        </div>
                      ))}
                    </section>
                  </>
                )}
              </aside>
            </section>

            <footer className="review-tip">
              <Lightbulb />
              <span><b>小贴士：</b>为获得更准确的分析结果，建议上传包含完整交易记录的交割单（包含成交时间、品种、方向、价格、数量、手续费等信息）</span>
            </footer>
          </>
        )}
      </section>
      <div className={`studio-toast ${toast ? "show" : ""}`}>{toast}</div>
    </main>
  );
}
