"use client";

import Image from "next/image";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { BellRing, ChevronDown, Copy, FileSearch, Gift, Info, LogOut, MessageSquare, ShieldCheck, Sparkles, UserRound, X } from "lucide-react";
import { GoldMagicCube } from "@/components/gold-magic-cube";
import { HomeMusic } from "@/components/home-music";
import { apiFetch, clearAuth, getStoredUser, inviteUrl, refreshCurrentUser, type UserProfile } from "@/lib/auth-client";

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
  const [hydrated, setHydrated] = useState(false);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [feedback, setFeedback] = useState("");
  const [feedbackCategory, setFeedbackCategory] = useState("产品建议");
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [showProductGuide, setShowProductGuide] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [inviteCopied, setInviteCopied] = useState(false);

  useEffect(() => {
    setHydrated(true);
    setUser(getStoredUser());
    refreshCurrentUser().then(setUser).catch(() => setUser(null));
    function handleAuth(event: Event) {
      setUser((event as CustomEvent<UserProfile | null>).detail || null);
    }
    window.addEventListener("ai-trade-auth", handleAuth);
    return () => window.removeEventListener("ai-trade-auth", handleAuth);
  }, []);

  async function copyInvite() {
    const url = inviteUrl(user);
    if (!url) return;
    await navigator.clipboard.writeText(url);
    setInviteCopied(true);
    setFeedbackMessage("邀请链接已复制。新用户用该链接注册登录后，你会获得 5 次免费机会。");
    window.setTimeout(() => setInviteCopied(false), 2200);
  }

  function scrollToFeedback() {
    setShowUserMenu(false);
    document.getElementById("feedback")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function openProductGuide() {
    setShowUserMenu(false);
    setShowProductGuide(true);
  }

  function logout() {
    clearAuth();
    setUser(null);
    setShowUserMenu(false);
    setInviteCopied(false);
  }

  const currentInviteUrl = hydrated && user ? inviteUrl(user) : "";

  async function submitFeedback(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFeedbackMessage("");
    if (!user) {
      setFeedbackMessage("请先登录后提交反馈。");
      return;
    }
    try {
      await apiFetch("/api/feedback", {
        method: "POST",
        body: JSON.stringify({ category: feedbackCategory, content: feedback }),
      });
      setFeedback("");
      setFeedbackMessage("反馈已提交。若被采纳，管理员会为你发放 10 次免费机会。");
    } catch (error) {
      setFeedbackMessage(error instanceof Error ? error.message : "提交失败，请稍后重试");
    }
  }

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
          <nav className="nav-links" aria-label="主导航">
            <button className="nav-action" type="button" onClick={openProductGuide}>
              功能
            </button>
            <button className="nav-action" type="button" onClick={scrollToFeedback}>
              反馈
            </button>
            <Link href="/review">AI 复盘</Link>
            <Link href="/watch">AI 盯盘</Link>
            {hydrated && user?.role === "admin" && <Link href="/admin">管理台</Link>}
            {hydrated && user ? (
              <div className="home-user-menu">
                <button className="login home-user-pill" type="button" onClick={() => setShowUserMenu((value) => !value)} aria-expanded={showUserMenu}>
                  <UserRound className="h-4 w-4" />
                  {user.role === "admin" ? "管理员" : `${user.credits} 次`}
                  <ChevronDown className="h-4 w-4" />
                </button>
                {showUserMenu && (
                  <div className="home-user-popover">
                    <div className="home-user-head">
                      <span>
                        <UserRound className="h-4 w-4" />
                        当前账号
                      </span>
                      <b>{user.username || user.phone}</b>
                    </div>
                    <div className="home-user-row">
                      <span>邮箱</span>
                      <em>{user.email || "暂未绑定邮箱"}</em>
                    </div>
                    <div className="home-user-row">
                      <span>剩余次数</span>
                      <em>{user.role === "admin" ? "管理员免扣次数" : `${user.credits} 次`}</em>
                    </div>
                    <div className="home-user-row">
                      <span>邀请码</span>
                      <em>{user.invite_code}</em>
                    </div>
                    {currentInviteUrl && (
                      <div className="home-invite-link-box" aria-label="邀请链接">
                        <span>邀请链接</span>
                        <code title={currentInviteUrl}>{currentInviteUrl}</code>
                      </div>
                    )}
                    <button className="home-user-copy" type="button" onClick={copyInvite}>
                      <Copy className="h-4 w-4" />
                      {inviteCopied ? "已复制邀请链接" : "复制邀请链接"}
                    </button>
                    <button className="home-user-logout" type="button" onClick={logout}>
                      <LogOut className="h-4 w-4" />
                      退出登录
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <Link className="login" href="/auth">
                登录
              </Link>
            )}
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
              从交割单开始，AI 自动还原你的交易现场：市场情绪、板块方向、个股强度、产业链位置和下一步执行方案一目了然。
            </p>
            <div className="actions">
              <Link className="primary" href="/review">
                <Sparkles className="h-5 w-5" />
                立即开始
              </Link>
              {hydrated && !user && (
                <Link className="secondary home-auth-link" href="/auth?redirect=/review">
                  手机号注册，送 5 次免费
                </Link>
              )}
            </div>
            {hydrated && user && user.role !== "admin" && (
              <div className="home-credit-strip">
                <span>
                  <Gift className="h-4 w-4" />
                  {`剩余 ${user.credits} 次免费机会`}
                </span>
                <button type="button" onClick={copyInvite}>
                  <Copy className="h-4 w-4" />
                  复制邀请链接
                </button>
              </div>
            )}
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
            <div className="feature-top-edge" aria-hidden="true" />
            <Image
              className="feature-cat-mark"
              src="/brand-logo-transparent.png"
              width={136}
              height={136}
              alt=""
              aria-hidden="true"
            />
            <h2 className="feature-section-title">看懂市场涨跌</h2>
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

        <section id="feedback" className="home-feedback-section">
          <div className="home-feedback-copy">
            <span>
              <MessageSquare className="h-4 w-4" />
              反馈建议
            </span>
            <h2>有意义的反馈被采纳后，奖励 10 次免费使用机会。</h2>
            <p>
              可以告诉我们复盘报告哪里不够准、盯盘预案缺了什么字段、页面哪里用起来别扭。管理员采纳后会直接给你的账号增加次数。
            </p>
          </div>
          <form className="home-feedback-form" onSubmit={submitFeedback}>
            <select value={feedbackCategory} onChange={(event) => setFeedbackCategory(event.target.value)}>
              <option>产品建议</option>
              <option>报告准确性</option>
              <option>页面体验</option>
              <option>付费与次数</option>
            </select>
            <textarea
              value={feedback}
              onChange={(event) => setFeedback(event.target.value)}
              placeholder="写下你的建议。越具体，越容易被采纳。"
              rows={5}
            />
            <button type="submit">
              <MessageSquare className="h-4 w-4" />
              提交反馈
            </button>
            {feedbackMessage && <p>{feedbackMessage}</p>}
          </form>
        </section>
      </div>
      {showProductGuide && (
        <div className="product-guide-backdrop" role="presentation" onMouseDown={() => setShowProductGuide(false)}>
          <section className="product-guide-modal" role="dialog" aria-modal="true" aria-labelledby="product-guide-title" onMouseDown={(event) => event.stopPropagation()}>
            <button className="product-guide-close" type="button" onClick={() => setShowProductGuide(false)} aria-label="关闭功能说明">
              <X className="h-5 w-5" />
            </button>
            <div className="product-guide-kicker">
              <Info className="h-4 w-4" />
              产品使用说明
            </div>
            <h2 id="product-guide-title">从复盘到盯盘，把交易动作沉淀成可执行流程。</h2>
            <p>
              盈航目前围绕两个核心环节工作：先用 AI 复盘拆解交易事实和改进点，再把结论转成次日盯盘预案，提醒你按计划执行。
            </p>
            <div className="product-guide-grid">
              {features.map((feature) => {
                const Icon = feature.icon;
                return (
                  <article key={feature.title}>
                    <Icon className="h-5 w-5" />
                    <h3>{feature.title}</h3>
                    <p>{feature.description}</p>
                    <Link href={feature.href} onClick={() => setShowProductGuide(false)}>
                      进入{feature.title}
                    </Link>
                  </article>
                );
              })}
            </div>
            <div className="product-guide-table">
              <div>
                <b>1. 上传或录入</b>
                <span>复盘上传交割单，盯盘录入持仓和观察条件。</span>
              </div>
              <div>
                <b>2. 生成结论</b>
                <span>系统输出买卖点评价、市场环境、风险条件和执行建议。</span>
              </div>
              <div>
                <b>3. 持续改进</b>
                <span>通过邀请、反馈或购买次数继续使用，管理员可在后台查看统计。</span>
              </div>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
