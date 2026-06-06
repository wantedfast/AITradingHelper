import Image from "next/image";
import Link from "next/link";
import { BellRing, FileSearch, LineChart, ShieldCheck, Sparkles, UploadCloud } from "lucide-react";
import { GoldMagicCube } from "@/components/gold-magic-cube";
import { HomeMusic } from "@/components/home-music";

const features = [
  {
    href: "/review",
    title: "AI 复盘",
    label: "Trade Review",
    icon: FileSearch,
    description:
      "上传交割单后，系统自动结构化买卖点，结合个股 K 线、大盘情绪、板块强弱和产业链定位，给出可执行的复盘结论。",
    points: ["买卖点评分", "最佳卖点推演", "板块与指数共振", "产业链位置判断"],
  },
  {
    href: "/watch",
    title: "AI 盯盘",
    label: "Trading Watch",
    icon: BellRing,
    description:
      "把复盘结论变成盘中预案：价格、涨跌幅、量能、指数环境触发后提醒交易者执行，避免临盘凭感觉改剧本。",
    points: ["预案触发", "声音提醒", "风险条件", "执行记录"],
  },
];

export default function Page() {
  return (
    <main className="site-page">
      <HomeMusic />
      <div className="noise-layer" />
      <div className="site-shell">
        <header className="nav">
          <Link className="brand" href="/">
            <Image src="/brand-logo.png" width={42} height={42} alt="AI Trading logo" priority />
            <span>AI Trading</span>
          </Link>
          <nav className="nav-links" aria-label="Main navigation">
            <a href="#features">Features</a>
            <Link href="/review">AI Review</Link>
            <Link href="/watch">AI Watch</Link>
            <Link className="login" href="/review">
              Start
            </Link>
          </nav>
        </header>

        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow">
              <Sparkles className="h-4 w-4" />
              AI Trade Review Agent
            </div>
            <h1>AI Trading for Beginners</h1>
            <p className="headline-sub">Stop Guessing. Start Trading With Your Best Strategy.</p>
            <p className="cn-slogan">摆脱盲从，依托优策。</p>
            <p className="description">
              从交割单开始，AI 自动还原你的交易现场：市场情绪、板块方向、个股强度、产业链位置和最佳执行方案。
            </p>
            <div className="actions">
              <Link className="primary" href="/review">
                <Sparkles className="h-5 w-5" />
                立即开始
              </Link>
              <a className="secondary" href="#tutorial">
                观看教学视频
              </a>
            </div>
          </div>

          <div className="visual" aria-hidden="true">
            <div className="orb" />
            <div className="cube-stage">
              <GoldMagicCube />
            </div>
          </div>
        </section>

        <section id="features" className="features">
          <div className="section-heading">
            <p>Two Core Modules</p>
            <h2>从复盘到盯盘，只保留真正影响交易决策的功能。</h2>
          </div>

          <div className="feature-grid">
            {features.map((feature) => {
              const Icon = feature.icon;
              return (
                <Link className="feature-card" href={feature.href} key={feature.title}>
                  <div className="feature-top">
                    <div className="feature-icon">
                      <Icon className="h-6 w-6" />
                    </div>
                    <div>
                      <span>{feature.label}</span>
                      <h3>{feature.title}</h3>
                    </div>
                  </div>
                  <p>{feature.description}</p>
                  <ul>
                    {feature.points.map((point) => (
                      <li key={point}>
                        <ShieldCheck className="h-4 w-4" />
                        {point}
                      </li>
                    ))}
                  </ul>
                </Link>
              );
            })}
          </div>

          <div className="flow-card">
            <LineChart className="h-5 w-5" />
            <span>上传交割单</span>
            <i />
            <span>AI 复盘</span>
            <i />
            <span>生成策略</span>
            <i />
            <span>盯盘执行</span>
          </div>
        </section>

        <section id="tutorial" className="features">
          <div className="section-heading">
            <p>Tutorial Video</p>
            <h2>先看一遍完整流程，再开始上传你的第一份交割单。</h2>
          </div>
          <div className="flow-card">
            <UploadCloud className="h-5 w-5" />
            <span>1 分钟看懂：上传交割单</span>
            <i />
            <span>自动结构化成交</span>
            <i />
            <span>生成复盘报告</span>
            <i />
            <Link href="/review">进入 AI 复盘</Link>
          </div>
        </section>
      </div>
    </main>
  );
}
