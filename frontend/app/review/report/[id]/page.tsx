"use client";

import Link from "next/link";

type ReviewReportPageProps = {
  params: {
    id: string;
  };
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

const TEXT = {
  back: "\u8fd4\u56de\u590d\u76d8",
  secure: "\u6b63\u5f0f Agent \u8f93\u51fa",
  eyebrow: "APPLE SYSTEM REVIEW",
  title: "AI \u590d\u76d8\u62a5\u544a",
  subtitle:
    "\u66f4\u63a5\u8fd1 Apple \u7cfb\u7edf\u754c\u9762\u7684\u8bc4\u4f30\u9875\uff1a\u6d45\u8272\u80cc\u666f\u3001\u73bb\u7483\u6d6e\u5c42\u3001\u84dd\u8272\u4e3b\u64cd\u4f5c\u3001\u514b\u5236\u7684\u8bed\u4e49\u72b6\u6001\u8272\uff0c\u8ba9\u590d\u76d8\u50cf\u4e00\u4e2a\u6e05\u723d\u7684\u7cfb\u7edf\u7ea7\u5de5\u4f5c\u53f0\u3002",
  refresh: "\u5237\u65b0",
  html: "\u6253\u5f00 HTML",
  presenter: "Presenter JSON",
  debug: "Debug JSON",
  iframeTitle: "\u590d\u76d8\u62a5\u544a HTML",
};

const REPORT_APPLE_STYLE = `
:root {
  --report-bg: #f5f5f7;
  --report-text: #1d1d1f;
  --report-muted: #6e6e73;
  --report-hairline: rgba(60, 60, 67, 0.14);
  --report-glass: rgba(255, 255, 255, 0.68);
  --report-glass-strong: rgba(255, 255, 255, 0.86);
  --report-blue: #007aff;
  --report-blue-dark: #005ecb;
  --report-green: #34c759;
  --report-yellow: #ffcc00;
  --report-red: #ff3b30;
}

body {
  margin: 0;
  min-height: 100vh;
  color: var(--report-text);
  background:
    radial-gradient(circle at 12% 6%, rgba(0, 122, 255, 0.18), transparent 28%),
    radial-gradient(circle at 88% 4%, rgba(255, 149, 0, 0.16), transparent 24%),
    radial-gradient(circle at 72% 82%, rgba(52, 199, 89, 0.14), transparent 30%),
    linear-gradient(180deg, #fbfbfd 0%, #f5f5f7 58%, #ececf1 100%);
  overflow-x: hidden;
  letter-spacing: 0;
}

.app, .app * {
  box-sizing: border-box;
}

.app {
  width: min(1180px, calc(100vw - 32px));
  min-height: 100vh;
  margin: 0 auto;
  padding: 18px 0 48px;
  color: var(--report-text);
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", "Microsoft YaHei", sans-serif;
}

.app a {
  color: inherit;
  text-decoration: none;
}

.glass {
  background: var(--report-glass);
  border: 1px solid rgba(255, 255, 255, 0.8);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.92),
    0 22px 60px rgba(29, 29, 31, 0.08);
  backdrop-filter: blur(30px) saturate(1.45);
  -webkit-backdrop-filter: blur(30px) saturate(1.45);
}

.topbar {
  position: sticky;
  top: 14px;
  z-index: 10;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 16px;
  align-items: center;
  min-height: 58px;
  padding: 10px 12px;
  border-radius: 24px;
}

.back,
.status {
  min-height: 38px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.56);
  color: rgba(29, 29, 31, 0.78);
  font-size: 14px;
  font-weight: 650;
  white-space: nowrap;
}

.back {
  justify-self: start;
}

.status {
  justify-self: end;
}

.status::before {
  content: "";
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--report-green);
  box-shadow: 0 0 0 5px rgba(52, 199, 89, 0.14);
}

.brand {
  text-align: center;
  line-height: 1.18;
}

.brand strong {
  display: block;
  font-size: 15px;
  font-weight: 760;
}

.brand span {
  display: block;
  margin-top: 4px;
  color: var(--report-muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
}

.hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 28px;
  align-items: end;
  margin-top: 18px;
  padding: 34px;
  border-radius: 34px;
  background:
    linear-gradient(135deg, rgba(255,255,255,.88), rgba(255,255,255,.48)),
    rgba(255,255,255,.62);
  border: 1px solid rgba(255,255,255,.82);
  box-shadow: 0 24px 70px rgba(29, 29, 31, 0.1);
  backdrop-filter: blur(34px) saturate(1.4);
  -webkit-backdrop-filter: blur(34px) saturate(1.4);
}

.eyebrow {
  margin: 0 0 12px;
  color: var(--report-blue);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: .1em;
}

.hero h1 {
  margin: 0;
  max-width: 720px;
  font-size: clamp(40px, 6vw, 78px);
  line-height: .96;
  font-weight: 780;
  letter-spacing: 0;
}

.lead {
  max-width: 700px;
  margin: 18px 0 0;
  color: var(--report-muted);
  font-size: 17px;
  line-height: 1.7;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
  max-width: 430px;
}

.btn {
  height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 16px;
  border: 1px solid var(--report-hairline);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  color: rgba(29, 29, 31, 0.82);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.82), 0 8px 22px rgba(29,29,31,.06);
  font-size: 14px;
  font-weight: 650;
  white-space: nowrap;
  cursor: pointer;
}

.btn.primary {
  color: #fff;
  border-color: rgba(0, 122, 255, 0.2);
  background: linear-gradient(180deg, var(--report-blue), var(--report-blue-dark));
  box-shadow: 0 12px 28px rgba(0, 122, 255, 0.26);
}

.workspace {
  display: grid;
  grid-template-columns: 270px minmax(0, 1fr);
  gap: 16px;
  margin-top: 16px;
  align-items: start;
  min-width: 0;
}

.sidebar {
  position: sticky;
  top: 92px;
  padding: 16px;
  border-radius: 28px;
  min-width: 0;
}

.side-title {
  margin: 0 0 12px;
  color: var(--report-muted);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: .08em;
}

.nav-item {
  display: grid;
  grid-template-columns: 34px 1fr;
  gap: 10px;
  align-items: center;
  padding: 10px;
  border-radius: 18px;
  color: rgba(29, 29, 31, 0.68);
  font-size: 14px;
  font-weight: 650;
}

.nav-item + .nav-item {
  margin-top: 4px;
}

.nav-item.active {
  background: rgba(0, 122, 255, 0.1);
  color: var(--report-blue-dark);
}

.bubble {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 13px;
  background: rgba(255,255,255,.72);
  color: var(--report-blue);
  font-size: 13px;
  font-weight: 760;
}

.report-card {
  padding: 20px;
  border-radius: 32px;
  min-width: 0;
}

.report-paper {
  padding: 0;
  border-radius: 26px;
  background: var(--report-glass-strong);
  border: 1px solid rgba(255,255,255,.86);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.92), 0 18px 44px rgba(29,29,31,.07);
  overflow: hidden;
}

.report-frame {
  width: 100%;
  height: max(720px, calc(100vh - 164px));
  display: block;
  border: 0;
  background: #fff;
}

@media (max-width: 920px) {
  .workspace {
    grid-template-columns: 1fr;
  }

  .sidebar {
    position: static;
  }

  .sidebar nav {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    max-width: 100%;
  }

  .nav-item + .nav-item {
    margin-top: 0;
  }

  .nav-item {
    min-width: 150px;
  }

  .hero {
    grid-template-columns: 1fr;
  }

  .actions {
    justify-content: flex-start;
    max-width: 100%;
  }
}

@media (max-width: 640px) {
  .app {
    width: 100%;
    padding: 0 0 34px;
  }

  .topbar {
    top: 0;
    grid-template-columns: 1fr;
    align-items: start;
    border-radius: 0 0 26px 26px;
  }

  .brand {
    text-align: left;
  }

  .status {
    justify-self: start;
  }

  .hero {
    margin: 12px;
    padding: 24px 20px;
    border-radius: 28px;
  }

  .actions {
    width: 100%;
    flex-wrap: nowrap;
    overflow-x: auto;
    padding-bottom: 4px;
  }

  .workspace {
    margin: 12px;
  }

  .report-card {
    padding: 12px;
    border-radius: 28px;
  }

  .report-paper {
    border-radius: 24px;
  }

  .report-frame {
    height: max(620px, calc(100vh - 260px));
  }
}

.app .topbar,
.app .hero,
.app .workspace,
.app .sidebar,
.app .report-card,
.app .report-paper {
  opacity: 1 !important;
  transform: none !important;
}

.app .hero {
  min-height: 0 !important;
  height: auto !important;
  color: var(--report-text) !important;
}

.app .hero h1 {
  color: var(--report-text) !important;
  opacity: 1 !important;
  text-shadow: none !important;
}

.app .lead,
.app .brand span,
.app .side-title {
  opacity: 1 !important;
}

.app .brand strong,
.app .brand span,
.app .status,
.app .back,
.app .btn,
.app .nav-item {
  text-shadow: none !important;
}

.app .brand strong {
  color: var(--report-text) !important;
}

.app .brand span {
  color: var(--report-muted) !important;
}
`;

export default function ReviewReportPage({ params }: ReviewReportPageProps) {
  const reportId = decodeURIComponent(params.id);
  const safeReportId = encodeURIComponent(reportId);
  const reportBase = `${API_BASE}/api/reports/${safeReportId}`;
  const htmlSrc = `${reportBase}/index.html`;
  const presenterSrc = `${reportBase}/research_presenter_data.json`;
  const debugSrc = `${reportBase}/research_debug_data.json`;

  return (
    <main className="app">
      <style>{REPORT_APPLE_STYLE}</style>

      <nav className="topbar glass">
        <Link className="back" href="/review">
          {TEXT.back}
        </Link>
        <div className="brand">
          <strong>Final WANG Agent</strong>
          <span>{reportId}</span>
        </div>
        <div className="status">{TEXT.secure}</div>
      </nav>

      <header className="hero">
        <div>
          <p className="eyebrow">{TEXT.eyebrow}</p>
          <h1>{TEXT.title}</h1>
          <p className="lead">{TEXT.subtitle}</p>
        </div>
        <div className="actions" aria-label="\u62a5\u544a\u64cd\u4f5c">
          <button className="btn primary" type="button" onClick={() => window.location.reload()}>
            {TEXT.refresh}
          </button>
          <a className="btn" href={htmlSrc} target="_blank" rel="noreferrer">
            {TEXT.html}
          </a>
          <a className="btn" href={presenterSrc} target="_blank" rel="noreferrer">
            {TEXT.presenter}
          </a>
          <a className="btn" href={debugSrc} target="_blank" rel="noreferrer">
            {TEXT.debug}
          </a>
        </div>
      </header>

      <div className="workspace">
        <aside className="sidebar glass" aria-label="\u62a5\u544a\u76ee\u5f55">
          <p className="side-title">REPORT MAP</p>
          <nav>
            <a className="nav-item active" href="#report-frame">
              <span className="bubble">01</span>
              <span>{"\u6700\u7ec8\u5224\u65ad"}</span>
            </a>
            <a className="nav-item" href="#report-frame">
              <span className="bubble">02</span>
              <span>{"\u5173\u952e\u8bc1\u636e"}</span>
            </a>
            <a className="nav-item" href="#report-frame">
              <span className="bubble">03</span>
              <span>{"\u98ce\u9669\u8d28\u91cf"}</span>
            </a>
            <a className="nav-item" href="#report-frame">
              <span className="bubble">04</span>
              <span>{"\u4e0b\u6b21\u89c4\u5219"}</span>
            </a>
          </nav>
        </aside>

        <section className="report-card glass" aria-label="\u590d\u76d8\u6b63\u6587">
          <article className="report-paper">
            <iframe id="report-frame" className="report-frame" src={htmlSrc} title={TEXT.iframeTitle} />
          </article>
        </section>
      </div>
    </main>
  );
}
