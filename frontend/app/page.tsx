"use client";

import Image from "next/image";
import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { BellRing, ChevronDown, Copy, CreditCard, Crown, FileSearch, FileText, Gift, Info, LogOut, Menu, MessageSquare, ShieldCheck, Sparkles, TrendingUp, Trophy, UserRound, X } from "lucide-react";
import { AuctionStrengthPerformanceTicker, useAuctionStrengthPerformance } from "@/components/auction-strength-performance-ticker";
import { GoldMagicCube } from "@/components/gold-magic-cube";
import { FinancialDisclaimer } from "@/components/financial-disclaimer";
import { apiFetch, clearAuth, getStoredUser, hasActiveMembership, inviteUrl, membershipExpiryText, refreshCurrentUser, storeUser, userAccessLabel, userBalanceText, type UserProfile } from "@/lib/auth-client";
import { copyTextToClipboard } from "@/lib/clipboard";

const features = [
  {
    href: "/auction-strength",
    title: "每日 TOP5",
    label: "DAILY TOP 5",
    icon: Trophy,
    description: "每天 9:25 集合竞价结束后，选出当天最值得关注的 5 只强势股，并提示需要回避的方向。",
    points: ["5 只强势股", "风险方向提示", "开盘观察重点", "同日只扣一次"],
  },
  {
    href: "/review",
    title: "AI 复盘",
    label: "TRADE REVIEW",
    icon: FileSearch,
    description: "上传交割单，查看每笔交易哪里做对、哪里需要改，以及下次遇到类似情况怎么处理。",
    points: ["看清做对的地方", "找到需要改的问题", "整理改进方法", "下次照着执行"],
  },
  {
    href: "/watch",
    title: "AI 盯盘",
    label: "TRADING WATCH",
    icon: BellRing,
    description: "填入持仓和计划，整理明天观察什么、什么情况买卖、什么情况先停手。",
    points: ["明天观察什么", "什么情况买卖", "什么情况停手", "按计划执行"],
  },
  {
    href: "/market-day",
    title: "AI 当日行情",
    label: "MARKET DAY",
    icon: TrendingUp,
    description: "每天 19:00（晚上 7 点）总结市场在炒什么、哪些板块强弱，并给出第二天关注重点。",
    points: ["市场在炒什么", "板块强弱", "当天行情总结", "明天关注重点"],
  },
  {
    href: "/ai-research",
    title: "AI 研报",
    label: "AI RESEARCH",
    icon: FileText,
    description: "每天 08:30（早上 8:30）汇总国内外重要消息，解释 CPI、黄金、原油和海外观点可能怎样影响 A 股。",
    points: ["国内外重要消息", "解释利好利空", "大宗商品影响", "海外观点影响"],
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
  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const [showAuctionTooltip, setShowAuctionTooltip] = useState(false);
  const [inviteCopied, setInviteCopied] = useState(false);
  const [savingEmailPreference, setSavingEmailPreference] = useState(false);
  const mobileMenuButtonRef = useRef<HTMLButtonElement>(null);
  const mobileMenuRef = useRef<HTMLElement>(null);
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
    if (!showMobileMenu) return;
    const previousOverflow = document.body.style.overflow;
    const menuTrigger = mobileMenuButtonRef.current;
    document.body.style.overflow = "hidden";
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setShowMobileMenu(false);
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        mobileMenuRef.current?.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input:not([disabled])') || [],
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    window.requestAnimationFrame(() => mobileMenuRef.current?.querySelector<HTMLElement>("button, a[href]")?.focus());
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
      menuTrigger?.focus();
    };
  }, [showMobileMenu]);

  useEffect(() => {
    if (!showProductGuide) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setShowProductGuide(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [showProductGuide]);

  async function copyInvite() {
    const url = inviteUrl(user);
    if (!url) return;
    const copied = await copyTextToClipboard(url);
    setInviteCopied(copied);
    setFeedbackMessage(
      copied
        ? "邀请链接已复制。新用户用该链接注册后，邀请方增加 5 次；被邀请方在注册赠送 5 次基础上，再额外增加 2 次。"
        : "当前浏览器限制了自动复制，请手动选择上方邀请链接复制。",
    );
    if (copied) {
      window.setTimeout(() => setInviteCopied(false), 2200);
    }
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

  function mobileLogout() {
    logout();
    setShowMobileMenu(false);
  }

  async function toggleUpdateEmails() {
    if (!user || savingEmailPreference) return;
    setSavingEmailPreference(true);
    setFeedbackMessage("");
    try {
      const payload = await apiFetch<{ user: UserProfile }>("/api/auth/email-preferences", {
        method: "POST",
        body: JSON.stringify({ update_emails_enabled: !(user.update_emails_enabled ?? true) }),
      });
      setUser(payload.user);
      storeUser(payload.user);
      setFeedbackMessage(payload.user.update_emails_enabled
        ? "已开启邮件推送，将接收产品更新、每日 TOP5、AI 研报和 AI 当日行情提醒。"
        : "已关闭产品更新与每日 AI 报告邮件，网站功能和更新弹窗仍会正常显示。");
    } catch (error) {
      setFeedbackMessage(error instanceof Error ? error.message : "邮件偏好保存失败");
    } finally {
      setSavingEmailPreference(false);
    }
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
      <div className="noise-layer" />
      <div className="site-shell">
        <header className="nav">
          <Link className="brand" href="/">
            <Image src="/brand-logo.png" width={42} height={42} alt="盈航 logo" priority />
            <span>盈航</span>
          </Link>
          <nav className="nav-links" aria-label="主导航">
            <Link href="/auction-strength">每日 TOP5</Link>
            <Link href="/review">AI 复盘</Link>
            <Link href="/watch">AI 盯盘</Link>
            <Link href="/market-day">AI当日行情</Link>
            <Link href="/ai-research">AI研报</Link>
            <button className="nav-action" type="button" onClick={scrollToFeedback}>
              反馈
            </button>
            <Link className="home-membership-nav" href="/billing">
              <Crown className="h-4 w-4" />
              {hydrated && hasActiveMembership(user) ? "会员已开通" : "开通会员"}
            </Link>
            <Link className="home-credits-nav" href="/credits">
              <CreditCard className="h-4 w-4" />
              购买次数
            </Link>
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
                    <button className="home-user-copy" type="button" onClick={toggleUpdateEmails} disabled={savingEmailPreference}>
                      <BellRing className="h-4 w-4" />
                      {savingEmailPreference
                        ? "正在保存..."
                        : `邮件推送（产品更新与每日 AI 报告）：${user.update_emails_enabled ?? true ? "已开启" : "已关闭"}`}
                    </button>
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
                      <Crown className="h-4 w-4" />
                      {hasActiveMembership(user) ? `会员有效至 ${membershipExpiryText(user) || "当前周期"}` : "开通会员"}
                    </Link>
                    <Link className="home-user-copy" href="/credits" onClick={() => setShowUserMenu(false)}>
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
          <div className="home-mobile-actions">
            {hydrated && !user ? (
              <>
                <Link className="home-mobile-membership" href="/billing">
                  <Crown aria-hidden="true" />
                  会员
                </Link>
                <Link className="home-mobile-register" href="/auth?mode=register">
                  免费注册
                </Link>
              </>
            ) : hydrated && user ? (
              <Link className={`home-mobile-membership${hasActiveMembership(user) ? " is-active" : ""}`} href="/billing">
                <Crown aria-hidden="true" />
                {hasActiveMembership(user) ? "会员已开通" : "开通会员"}
              </Link>
            ) : null}
            <button
              aria-controls="home-mobile-menu"
              aria-expanded={showMobileMenu}
              aria-label={showMobileMenu ? "关闭导航菜单" : "打开导航菜单"}
              className="home-mobile-menu-button"
              onClick={() => setShowMobileMenu((value) => !value)}
              ref={mobileMenuButtonRef}
              type="button"
            >
              {showMobileMenu ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
            </button>
          </div>
        </header>

        {showMobileMenu ? (
          <div className="home-mobile-menu-backdrop" role="presentation" onMouseDown={() => setShowMobileMenu(false)}>
            <nav
              aria-label="手机导航"
              className="home-mobile-menu"
              id="home-mobile-menu"
              onMouseDown={(event) => event.stopPropagation()}
              ref={mobileMenuRef}
            >
              <div className="home-mobile-menu-head">
                <span>导航与账户</span>
                <button aria-label="关闭导航菜单" onClick={() => setShowMobileMenu(false)} type="button">
                  <X aria-hidden="true" />
                </button>
              </div>
              <div className="home-mobile-feature-links">
                {features.map((feature) => {
                  const Icon = feature.icon;
                  return (
                    <Link href={feature.href} key={feature.href} onClick={() => setShowMobileMenu(false)}>
                      <Icon aria-hidden="true" />
                      <span>{feature.title}</span>
                    </Link>
                  );
                })}
              </div>
              <Link className="home-mobile-membership-card" href="/billing" onClick={() => { setShowMobileMenu(false); }}>
                <span className="home-mobile-membership-card__icon"><Crown aria-hidden="true" /></span>
                <span>
                  <small>盈航会员 · 全功能不限次数</small>
                  <b>{hasActiveMembership(user) ? "会员权益已生效" : "月度 ¥59 · 年度 ¥399"}</b>
                  <em>{hasActiveMembership(user) ? `有效至 ${membershipExpiryText(user) || "当前周期结束"}` : "年度会员更划算，开通后会员期内无限使用"}</em>
                </span>
                <strong>{hasActiveMembership(user) ? "查看" : "开通"}</strong>
              </Link>
              <Link className="home-mobile-membership-card home-mobile-credits-card" href="/credits" onClick={() => { setShowMobileMenu(false); }}>
                <span className="home-mobile-membership-card__icon"><CreditCard aria-hidden="true" /></span>
                <span>
                  <small>单次购买 · 次数余额</small>
                  <b>固定 1 元 / 次</b>
                  <em>会员期内先累加不消耗，会员过期后继续用余额。</em>
                </span>
                <strong>购买</strong>
              </Link>
              {hydrated && user?.role === "admin" ? (
                <div className="home-mobile-menu-secondary">
                  <Link href="/admin" onClick={() => setShowMobileMenu(false)}>
                    <ShieldCheck aria-hidden="true" />
                    管理台
                  </Link>
                </div>
              ) : null}
              {hydrated && user ? (
                <div className="home-mobile-account">
                  <div>
                    <UserRound aria-hidden="true" />
                    <span>
                      <small>当前账号</small>
                      <b>{user.username || user.email || user.phone}</b>
                    </span>
                  </div>
                  <p>{userBalanceText(user)}</p>
                  <Link href="/billing" onClick={() => setShowMobileMenu(false)}>
                    <Crown aria-hidden="true" />
                    {hasActiveMembership(user) ? "查看会员权益" : "开通会员"}
                  </Link>
                  <Link href="/credits" onClick={() => setShowMobileMenu(false)}>
                    <CreditCard aria-hidden="true" />
                    购买次数
                  </Link>
                  <button type="button" onClick={mobileLogout}>
                    <LogOut aria-hidden="true" />
                    退出登录
                  </button>
                </div>
              ) : (
                <div className="home-mobile-guest-actions">
                  <Link className="home-mobile-account-register" href="/auth?mode=register" onClick={() => { setShowMobileMenu(false); }}>免费注册，领取 5 次</Link>
                  <Link className="home-mobile-account-login" href="/auth" onClick={() => setShowMobileMenu(false)}>已有账号登录</Link>
                </div>
              )}
              <div className="home-mobile-menu-secondary">
                <button type="button" onClick={() => { setShowMobileMenu(false); scrollToFeedback(); }}>
                  <MessageSquare aria-hidden="true" />
                  反馈建议
                </button>
              </div>
            </nav>
          </div>
        ) : null}

        <FinancialDisclaimer />

        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow">
              <Sparkles className="h-4 w-4" />
              AI 交易决策助手
            </div>
            <h1>
              <span className="home-title-desktop">AI Trading for Beginners</span>
              <span className="home-title-mobile">每天看懂市场，交易更有计划</span>
            </h1>
            <p className="headline-sub">Stop Guessing. Start Trading With Your Best Strategy.</p>
            <p className="cn-slogan">摆脱盲从，依托优策。</p>
            <p className="description">
              从交割单开始，AI 自动还原你的交易现场：市场情绪、板块方向、个股强度、产业链位置和下一步执行方案一目了然。
            </p>
            <div className="actions">
              <Link className="primary home-start-primary" href={user ? "/auction-strength" : "/auth"}>
                {user ? <Trophy className="h-5 w-5" /> : <Sparkles className="h-5 w-5" />}
                现在开始
              </Link>
            </div>
            <div
              className={`hero-performance-chip${showAuctionTooltip ? " is-tooltip-open" : ""}`}
              tabIndex={0}
              aria-label="查看最近五个交易日每日 TOP5 第1名"
              onMouseEnter={() => setShowAuctionTooltip(true)}
              onMouseLeave={() => setShowAuctionTooltip(false)}
              onFocus={() => setShowAuctionTooltip(true)}
              onBlur={() => setShowAuctionTooltip(false)}
              onClick={() => setShowAuctionTooltip((value) => !value)}
            >
              <div className="hero-performance-label">每日 TOP5 第1名胜率</div>
              <div className="hero-performance-rate">{auctionPerformance.win_rate_text}</div>
              <div className="hero-performance-meta">
                <span>每日 TOP5 第1名</span>
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
              <span>每日 TOP5 第1名</span>
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
            <span className="section-kicker">每日 TOP5</span>
            <h2 id="auction-strength-proof-title">每天开盘前，先看最值得关注的 5 只股票。</h2>
            <p>
              每天 9:25 集合竞价结束后，选出 5 只强势股，并提示需要回避的方向；第1名的历史表现会持续记录。
            </p>
            <div className="auction-strength-points">
              <span>9:25 后查看 5 只强势股</span>
              <span>记录买入价格与第二天盈利</span>
              <span>持续沉淀当前个股胜率</span>
            </div>
            <Link className="auction-strength-cta" href="/auction-strength">
              查看今日 TOP5
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
        <footer className="home-operations-footer">
          <span>© 盈航 AI TRADING</span>
          <Link href="/admin/login">运营登录</Link>
        </footer>
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
            <h2 id="product-guide-title">五个功能，帮你把每天的交易想清楚。</h2>
            <p>
              开盘前看每日 TOP5 和 AI 研报，收盘后看 AI 当日行情；自己的交易可以用 AI 复盘检查，再用 AI 盯盘整理明天的计划。
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


