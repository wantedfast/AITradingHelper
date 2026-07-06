"use client";

import Image from "next/image";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { BellRing, ChevronDown, Copy, CreditCard, FileSearch, GitBranch, Gift, Info, LogOut, Megaphone, MessageSquare, ShieldCheck, Sparkles, TrendingUp, Trophy, UserRound, X } from "lucide-react";
import { AuctionStrengthPerformanceTicker, useAuctionStrengthPerformance } from "@/components/auction-strength-performance-ticker";
import { GoldMagicCube } from "@/components/gold-magic-cube";
import { HomeMusic } from "@/components/home-music";
import { apiFetch, clearAuth, getStoredUser, inviteUrl, refreshCurrentUser, userAccessLabel, userBalanceText, type UserProfile } from "@/lib/auth-client";

const features = [
  {
    href: "/review",
    title: "AI 复盘",
    label: "TRADE REVIEW",
    icon: FileSearch,
    description: "上传交割单，自动还原买卖过程，结合个股走势、市场情绪与板块强弱，生成可执行的复盘结论。",
    points: ["买卖点评分", "交易逻辑拆解", "板块强弱判断", "复盘结论生成"],
  },
  {
    href: "/watch",
    title: "AI 盯盘",
    label: "TRADING WATCH",
    icon: BellRing,
    description: "围绕买入价、仓位和市场环境生成次日交易预案，触发关键条件时提醒执行，减少临盘犹豫。",
    points: ["次日预案", "执行提醒", "风险条件", "执行记录"],
  },
  {
    href: "/market-day",
    title: "AI 当日行情",
    label: "MARKET DAY",
    icon: TrendingUp,
    description: "自动梳理当日 A 股行情，识别主线题材、强势梯队与核心个股，帮助你抓住市场真正的方向。",
    points: ["主线识别", "强势个股", "梯队判断", "证据链复盘"],
  },
  {
    href: "/industry-trend",
    title: "产业趋势",
    label: "INDUSTRY TREND",
    icon: GitBranch,
    description: "输入产业链或个股，调用本地 Stock Analyze，拆解产业利润流向、瓶颈节点和三高选股排序。",
    points: ["产业链拆解", "瓶颈识别", "三高评分", "个股定位"],
  },
  {
    href: "/auction-strength",
    title: "竞价强者",
    label: "AUCTION STRENGTH",
    icon: Trophy,
    description: "解析集合竞价后的强弱信号，筛选高关注标的、回避风险方向，并给出开盘前的执行重点。",
    points: ["竞价强弱", "开盘重点", "风险回避", "题材结论"],
  },
];

type UpdateNotice = {
  id: number;
  title: string;
  version: string;
  items: string[];
  published_at?: string | null;
};

const UPDATE_NOTICE_SEEN_KEY = "ai_trade_seen_update_notice_id";

export default function Page() {
  const [hydrated, setHydrated] = useState(false);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [feedback, setFeedback] = useState("");
  const [feedbackCategory, setFeedbackCategory] = useState("产品建议");
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [showProductGuide, setShowProductGuide] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showAuctionTooltip, setShowAuctionTooltip] = useState(false);
  const [inviteCopied, setInviteCopied] = useState(false);
  const [updateNotice, setUpdateNotice] = useState<UpdateNotice | null>(null);
  const [showUpdateNotice, setShowUpdateNotice] = useState(false);
  const auctionPerformance = useAuctionStrengthPerformance();
  const recentAuctionTop1Rows = auctionPerformance.rows.slice(-5).reverse();

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

  useEffect(() => {
    apiFetch<{ notice: UpdateNotice | null }>("/api/update-notices/latest")
      .then((payload) => {
        if (!payload.notice) return;
        const noticeId = String(payload.notice.id);
        if (window.localStorage.getItem(UPDATE_NOTICE_SEEN_KEY) === noticeId) return;
        setUpdateNotice(payload.notice);
        setShowUpdateNotice(true);
      })
      .catch(() => {
        // Update notices should never block the homepage.
      });
  }, []);

  function closeUpdateNotice() {
    if (updateNotice) {
      window.localStorage.setItem(UPDATE_NOTICE_SEEN_KEY, String(updateNotice.id));
    }
    setShowUpdateNotice(false);
  }

  async function copyInvite() {
    const url = inviteUrl(user);
    if (!url) return;
    await navigator.clipboard.writeText(url);
    setInviteCopied(true);
    setFeedbackMessage("邀请链接已复制。新用户用该链接注册后，邀请方增加 5 次；被邀请方在注册赠送 5 次基础上，再额外增加 2 次。");
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
            <Link href="/market-day">AI当日行情</Link>
            <Link href="/industry-trend">产业趋势</Link>
            <Link href="/auction-strength">竞价强者</Link>
            {hydrated && user?.role === "admin" && <Link href="/admin">管理台</Link>}
            {hydrated && user ? (
              <div className="home-user-menu">
                <button className="login home-user-pill" type="button" onClick={() => setShowUserMenu((value) => !value)} aria-expanded={showUserMenu}>
                  <UserRound className="h-4 w-4" />
                  {userAccessLabel(user)}
                  <ChevronDown className="h-4 w-4" />
                </button>
                {showUserMenu && (
                  <div className="home-user-popover">
                    <div className="home-user-head">
                      <span>
                        <UserRound className="h-4 w-4" />
                        当前账号
                      </span>
                      <b>{user.username || user.email || user.phone}</b>
                    </div>
                    <div className="home-user-row">
                      <span>邮箱</span>
                      <em>{user.email || "暂未绑定邮箱"}</em>
                    </div>
                    <div className="home-user-row">
                      <span>剩余次数</span>
                      <em>{userBalanceText(user)}</em>
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
                    <Link className="home-user-copy" href="/billing" onClick={() => setShowUserMenu(false)}>
                      <CreditCard className="h-4 w-4" />
                      购买次数
                    </Link>
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
                <Link className="secondary home-auth-link" href="/auth">
                  邮箱注册，送 5 次免费
                </Link>
              )}
            </div>
            <div
              className={`hero-performance-chip${showAuctionTooltip ? " is-tooltip-open" : ""}`}
              tabIndex={0}
              aria-label="查看最近五个交易日竞价强者 Top1"
              onMouseEnter={() => setShowAuctionTooltip(true)}
              onMouseLeave={() => setShowAuctionTooltip(false)}
              onFocus={() => setShowAuctionTooltip(true)}
              onBlur={() => setShowAuctionTooltip(false)}
              onClick={() => setShowAuctionTooltip((value) => !value)}
            >
              <div className="hero-performance-label">竞价强者选股胜率</div>
              <div className="hero-performance-rate">{auctionPerformance.win_rate_text}</div>
              <div className="hero-performance-meta">
                <span>集合竞价强者 Top1</span>
                <span>
                  持有一天收益 <strong>{auctionPerformance.recent_5_avg_return_text}</strong>
                </span>
              </div>
              <div className="hero-performance-tooltip" role="tooltip">
                <div className="hero-performance-tooltip-head">
                  <span>最近五个交易日</span>
                  <strong>Top1</strong>
                </div>
                <div className="hero-performance-tooltip-list">
                  {recentAuctionTop1Rows.map((row) => (
                    <div className="hero-performance-tooltip-row" key={`${row.trade_date}-${row.code || row.name}`}>
                      <span>{row.trade_date}</span>
                      <b>{row.name}</b>
                      <em>{row.return_text}</em>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            {hydrated && user && user.role !== "admin" && (
              <div className="home-credit-strip">
                <span>
                  <Gift className="h-4 w-4" />
                  {userBalanceText(user)}
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
          <div className="hero-performance-chip">
            <div className="hero-performance-label">目前集合竞价选股胜率</div>
            <div className="hero-performance-rate">{auctionPerformance.win_rate_text}</div>
            <div className="hero-performance-meta">
              <span>集合竞价强者 Top1</span>
              <span>
                持有一天收益 <strong>{auctionPerformance.recent_5_avg_return_text}</strong>
              </span>
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
            <div className="feature-marquee-viewport">
              <div className="feature-marquee-track">
                {[...features, ...features, ...features].map((feature, index) => {
                  const Icon = feature.icon;
                  const duplicate = index >= features.length;
                  return (
                    <Link
                      aria-hidden={duplicate}
                      className="feature-card feature-card--glass"
                      href={feature.href}
                      key={`${feature.title}-${index}`}
                      tabIndex={duplicate ? -1 : undefined}
                    >
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
                        {feature.points.slice(0, 2).map((point) => (
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
          </div>
        </section>

        <section className="auction-strength-section" aria-labelledby="auction-strength-proof-title">
          <div className="auction-strength-copy">
            <span className="section-kicker">集合竞价强者</span>
            <h2 id="auction-strength-proof-title">每天开盘前，先看到最强的那一个。</h2>
            <p>
              系统在集合竞价结束后，自动识别当日强势个股 Top1，并持续记录买入价格、次日收益和累计胜率。
            </p>
            <div className="auction-strength-points">
              <span>9:25 后快速定位强势个股</span>
              <span>记录买入价格与第二天盈利</span>
              <span>持续沉淀当前个股胜率</span>
            </div>
            <Link className="auction-strength-cta" href="/auction-strength">
              查看今日强者
            </Link>
          </div>
          <AuctionStrengthPerformanceTicker performance={auctionPerformance} />
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
      {showUpdateNotice && updateNotice && (
        <div className="product-guide-backdrop" role="presentation" onMouseDown={closeUpdateNotice}>
          <section className="update-notice-modal" role="dialog" aria-modal="true" aria-labelledby="update-notice-title" onMouseDown={(event) => event.stopPropagation()}>
            <button className="product-guide-close" type="button" onClick={closeUpdateNotice} aria-label="关闭更新公告">
              <X className="h-5 w-5" />
            </button>
            <div className="product-guide-kicker">
              <Megaphone className="h-4 w-4" />
              最新更新
            </div>
            <h2 id="update-notice-title">{updateNotice.title}</h2>
            <p>
              {updateNotice.version}
              {updateNotice.published_at ? ` · ${formatUpdateNoticeDate(updateNotice.published_at)}` : ""}
            </p>
            <ul className="update-notice-list">
              {updateNotice.items.map((item, index) => (
                <li key={`${item}-${index}`}>{item}</li>
              ))}
            </ul>
            <button className="update-notice-confirm" type="button" onClick={closeUpdateNotice}>
              知道了
            </button>
          </section>
        </div>
      )}
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

function formatUpdateNoticeDate(value: string) {
  return value ? value.slice(0, 16).replace("T", " ") : "";
}


