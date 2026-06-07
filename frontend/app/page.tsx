import Image from "next/image";
import Link from "next/link";
import { BellRing, FileSearch, ShieldCheck, Sparkles } from "lucide-react";
import { GoldMagicCube } from "@/components/gold-magic-cube";
import { HomeMusic } from "@/components/home-music";

const features = [
  {
    href: "/review",
    title: "AI 复盘",
    label: "Trade Review",
    icon: FileSearch,
    description:
      "上传交割单后，系统自动结构化买卖过程，结合个股 K 线、大盘情绪、板块强弱和产业链位置，给出可执行的复盘结论。",
    points: ["买卖点评分", "最佳卖点推演", "板块与指数共振", "产业链位置判断"],
  },
  {
    href: "/watch",
    title: "AI 盯盘",
    label: "Trading Watch",
    icon: BellRing,
    description:
      "把复盘结论变成盘中预案，价格、涨跌幅、量能与指数环境触发后提醒交易者执行，避免临盘凭感觉改剧本。",
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
            <Image src="/brand-logo.png" width={42} height={42} alt="盈航 logo" priority />
            <span>盈航</span>
          </Link>
          <nav className="nav-links" aria-label="Main navigation">
            <a href="#features">功能</a>
            <Link href="/review">AI 复盘</Link>
            <Link href="/watch">AI 盯盘</Link>
            <Link className="login" href="/review">
              开始
            </Link>
          </nav>
        </header>

        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow">
              <Sparkles className="h-4 w-4" />
              AI 交易决策助手
            </div>
            <h1>AI Trading for Beginners</h1>
            <p className="headline-sub">Stop Guessing. Start Trading With Your Best Strategy.</p>
            <p className="cn-slogan">摆脱盲从，依托优策。</p>
            <p className="description">
              从交割单开始，AI 自动还原你的交易现场，市场情绪、板块方向、个股强度、产业链位置和最佳执行方案一目了然。
            </p>
            <div className="actions">
              <Link className="primary" href="/review">
                <Sparkles className="h-5 w-5" />
                立即开始
              </Link>
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
          <div className="feature-shell">
            <div className="feature-shell__glow" />
            <div className="feature-grid">
              {features.map((feature) => {
                const Icon = feature.icon;
                return (
                  <Link className="feature-card feature-card--glass" href={feature.href} key={feature.title}>
                    <div className="feature-card__glow" />
                    <div className="feature-card__shine" />
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
          </div>
        </section>

      </div>
    </main>
  );
}
