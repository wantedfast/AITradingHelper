"use client";

import Image from "next/image";
import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { ArrowRight, ArrowUpRight, BellRing, ChevronDown, Copy, CreditCard, Crown, ImagePlus, LogOut, Menu, MessageSquare, ReceiptText, ShieldCheck, UserRound, X } from "lucide-react";
import { useAuctionStrengthPerformance } from "@/components/auction-strength-performance-ticker";
import { FinancialDisclaimer } from "@/components/financial-disclaimer";
import { TradingDayClock } from "@/components/home/trading-day-clock";
import { WAYPOINTS, beijingNow, dayPhase } from "@/components/home/trading-day";
import { ApiError, apiFetch, clearAuth, getStoredUser, hasActiveMembership, inviteUrl, membershipExpiryText, refreshCurrentUser, storeUser, userBalanceText, type UserProfile } from "@/lib/auth-client";
import { copyTextToClipboard } from "@/lib/clipboard";
import "./yh-tokens.css";
import "./home.css";

type PublicPlan = { id: string; plan_name: string; amount_cents: number; duration_days: number };

const FALLBACK_PLANS: PublicPlan[] = [
  { id: "monthly_membership", plan_name: "月度会员", amount_cents: 5900, duration_days: 31 },
  { id: "annual_membership", plan_name: "年度会员", amount_cents: 39900, duration_days: 365 },
];

const NAV_LINKS = [
  { href: "/auction-strength", label: "每日 TOP5" },
  { href: "/ai-research", label: "AI 研报" },
  { href: "/market-breadth", label: "市场强弱" },
  { href: "/market-day", label: "当日行情" },
  { href: "/review", label: "AI 复盘" },
  { href: "/watch", label: "AI 盯盘" },
  { href: "/stock-research", label: "价值投资" },
];

function yuan(cents: number) {
  return (cents / 100).toFixed(cents % 100 ? 2 : 0);
}

/** Adds `is-visible` to [data-reveal] elements as they scroll in. */
function useReveal() {
  useEffect(() => {
    const root = document.documentElement;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const nodes = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]"));
    if (reduce || !("IntersectionObserver" in window)) {
      nodes.forEach((node) => node.classList.add("is-visible"));
      return;
    }
    root.classList.add("yh-motion");
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.12 },
    );
    nodes.forEach((node) => observer.observe(node));
    return () => {
      observer.disconnect();
      root.classList.remove("yh-motion");
    };
  }, []);
}

export default function Page() {
  const [hydrated, setHydrated] = useState(false);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [feedback, setFeedback] = useState("");
  const [feedbackCategory, setFeedbackCategory] = useState("产品建议");
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [feedbackImage, setFeedbackImage] = useState<File | null>(null);
  const [authUnavailable, setAuthUnavailable] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const [inviteCopied, setInviteCopied] = useState(false);
  const [savingEmailPreference, setSavingEmailPreference] = useState(false);
  const [plans, setPlans] = useState<PublicPlan[]>(FALLBACK_PLANS);
  const [focusIds, setFocusIds] = useState<string[]>([]);
  const mobileMenuButtonRef = useRef<HTMLButtonElement>(null);
  const mobileMenuRef = useRef<HTMLElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const feedbackImageRef = useRef<HTMLInputElement>(null);
  const performance = useAuctionStrengthPerformance();
  const ledgerRows = performance.rows.slice(-6).reverse();
  useReveal();

  useEffect(() => {
    setHydrated(true);
    const storedUser = getStoredUser();
    setUser(storedUser);
    refreshCurrentUser().then((currentUser) => {
      setAuthUnavailable(false);
      setUser(currentUser);
    }).catch((error) => {
      if (error instanceof ApiError && error.status === 401) {
        setAuthUnavailable(false);
        setUser(null);
      } else if (storedUser) {
        setAuthUnavailable(true);
      } else {
        setUser(null);
      }
    });
    function handleAuth(event: Event) {
      setAuthUnavailable(false);
      setUser((event as CustomEvent<UserProfile | null>).detail || null);
    }
    window.addEventListener("ai-trade-auth", handleAuth);
    return () => window.removeEventListener("ai-trade-auth", handleAuth);
  }, []);

  useEffect(() => {
    let cancelled = false;
    apiFetch<{ plans?: PublicPlan[] }>("/api/public/membership/plans")
      .then((payload) => {
        if (!cancelled && payload.plans?.length) setPlans(payload.plans);
      })
      .catch(() => undefined);
    const syncFocus = () => setFocusIds(dayPhase(beijingNow()).focus);
    syncFocus();
    const timer = window.setInterval(syncFocus, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
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
    if (!showUserMenu) return;
    function close(event: MouseEvent | KeyboardEvent) {
      if (event instanceof KeyboardEvent) {
        if (event.key === "Escape") setShowUserMenu(false);
        return;
      }
      if (!userMenuRef.current?.contains(event.target as Node)) setShowUserMenu(false);
    }
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", close);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", close);
    };
  }, [showUserMenu]);

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

  function logout() {
    clearAuth();
    setAuthUnavailable(false);
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

  async function submitFeedback(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFeedbackMessage("");
    if (!user) {
      setFeedbackMessage("请先登录后提交反馈。");
      return;
    }
    if (feedbackImage && feedbackImage.size > 5 * 1024 * 1024) {
      setFeedbackMessage("截图不能超过 5MB。");
      return;
    }
    try {
      const form = new FormData();
      form.set("category", feedbackCategory);
      form.set("content", feedback);
      if (feedbackImage) form.set("file", feedbackImage);
      await apiFetch("/api/feedback", {
        method: "POST",
        body: form,
      });
      setFeedback("");
      setFeedbackImage(null);
      if (feedbackImageRef.current) feedbackImageRef.current.value = "";
      setFeedbackMessage("反馈已提交。若被采纳，管理员会为你发放 10 次免费机会。");
    } catch (error) {
      setFeedbackMessage(error instanceof Error ? error.message : "提交失败，请稍后重试");
    }
  }

  const currentInviteUrl = hydrated && user ? inviteUrl(user) : "";
  const accountDisplay = user?.username || user?.email || user?.phone || "";
  const member = hydrated && hasActiveMembership(user);
  const monthly = plans.find((plan) => plan.duration_days < 300) || FALLBACK_PLANS[0];
  const annual = plans.find((plan) => plan.duration_days >= 300) || FALLBACK_PLANS[1];
  const annualSaving = Math.max(0, Math.round((monthly.amount_cents * 12 - annual.amount_cents) / 100));
  const sampleCount = performance.sample_count || performance.rows.length;

  return (
    <main className="yh">
      <a className="yh-skip" href="#yh-main">跳到正文</a>
      <header className="yh-bar">
        <Link className="yh-brand" href="/" aria-label="盈航 首页">
          <Image src="/brand-logo-transparent.png" width={36} height={36} alt="" priority />
          <span>盈航</span>
          <small>AI TRADING</small>
        </Link>
        <nav className="yh-nav-links" aria-label="主导航">
          {NAV_LINKS.map((link) => (
            <Link key={link.href} href={link.href}>{link.label}</Link>
          ))}
        </nav>
        <div className="yh-bar__end">
          <Link className={`yh-pill yh-pill--brass${member ? " is-member" : ""}`} href="/billing">
            <Crown aria-hidden="true" />
            {member ? "会员已开通" : "开通会员"}
          </Link>
          <Link className="yh-pill yh-pill--ghost yh-desktop-only" href="/credits">
            <CreditCard aria-hidden="true" />
            购买次数
          </Link>
          {hydrated && user?.role === "admin" ? <Link className="yh-pill yh-pill--ghost yh-desktop-only" href="/admin">管理台</Link> : null}
          {hydrated && user ? (
            <div className="yh-user yh-desktop-only" ref={userMenuRef}>
              <button className="yh-user-pill" type="button" onClick={() => setShowUserMenu((value) => !value)} aria-expanded={showUserMenu} aria-haspopup="true">
                <UserRound aria-hidden="true" />
                <span>{authUnavailable ? "账号已保留" : "已登录"} · {accountDisplay}</span>
                <ChevronDown aria-hidden="true" />
              </button>
              {showUserMenu ? (
                <div className="yh-popover">
                  {authUnavailable ? <p className="yh-popover__warn">服务器暂时不可用，登录信息已保留，无需重复登录。</p> : null}
                  <dl>
                    <div><dt>当前账号</dt><dd>{accountDisplay}</dd></div>
                    <div><dt>邮箱</dt><dd>{user.email || "暂未绑定邮箱"}</dd></div>
                    <div><dt>剩余次数</dt><dd>{userBalanceText(user)}</dd></div>
                    <div><dt>会员</dt><dd>{hasActiveMembership(user) ? `有效至 ${membershipExpiryText(user) || "当前周期"}` : "未开通"}</dd></div>
                    <div><dt>邀请码</dt><dd>{user.invite_code}</dd></div>
                  </dl>
                  {currentInviteUrl ? <code className="yh-popover__invite" title={currentInviteUrl}>{currentInviteUrl}</code> : null}
                  <Link href="/account/orders" onClick={() => setShowUserMenu(false)}>
                    <ReceiptText aria-hidden="true" />我的订单
                  </Link>
                  <button type="button" onClick={copyInvite}>
                    <Copy aria-hidden="true" />
                    {inviteCopied ? "已复制邀请链接" : "复制邀请链接"}
                  </button>
                  <button type="button" onClick={toggleUpdateEmails} disabled={savingEmailPreference}>
                    <BellRing aria-hidden="true" />
                    {savingEmailPreference ? "正在保存..." : `邮件推送：${user.update_emails_enabled ?? true ? "已开启" : "已关闭"}`}
                  </button>
                  <button type="button" onClick={scrollToFeedback}>
                    <MessageSquare aria-hidden="true" />
                    反馈建议
                  </button>
                  <button className="is-danger" type="button" onClick={logout}>
                    <LogOut aria-hidden="true" />
                    退出登录
                  </button>
                </div>
              ) : null}
            </div>
          ) : hydrated ? (
            <Link className="yh-pill yh-pill--ghost yh-desktop-only" href="/auth">登录</Link>
          ) : null}
        </div>
        <div className="yh-mobile-actions">
          {hydrated && !user ? (
            <>
              <Link className="yh-mobile-membership" href="/billing">
                <Crown aria-hidden="true" />
                会员
              </Link>
              <Link className="yh-mobile-register" href="/auth?mode=register">免费注册</Link>
            </>
          ) : hydrated && user ? (
            // Links to checkout, so on phones it must say what it does.
            <Link className={`yh-mobile-membership${hasActiveMembership(user) ? " is-active" : ""}`} href="/billing">
              {hasActiveMembership(user) ? <Crown aria-hidden="true" /> : <UserRound aria-hidden="true" />}
              {authUnavailable ? "账号已保留" : hasActiveMembership(user) ? "会员已开通" : "开通会员"}
            </Link>
          ) : null}
          <button
            aria-controls="yh-mobile-menu"
            aria-expanded={showMobileMenu}
            aria-label={showMobileMenu ? "关闭导航菜单" : "打开导航菜单"}
            className="yh-mobile-menu-button"
            onClick={() => setShowMobileMenu((value) => !value)}
            ref={mobileMenuButtonRef}
            type="button"
          >
            {showMobileMenu ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          </button>
        </div>
      </header>

      {showMobileMenu ? (
        <div className="yh-sheet-backdrop" role="presentation" onMouseDown={() => setShowMobileMenu(false)}>
          <nav aria-label="手机导航" className="yh-sheet" id="yh-mobile-menu" onMouseDown={(event) => event.stopPropagation()} ref={mobileMenuRef}>
            <div className="yh-sheet-head">
              <span>导航与账户</span>
              <button aria-label="关闭导航菜单" onClick={() => setShowMobileMenu(false)} type="button">
                <X aria-hidden="true" />
              </button>
            </div>
            <ol className="yh-sheet-route">
              {WAYPOINTS.map((waypoint) => {
                const Icon = waypoint.icon;
                return (
                  <li key={waypoint.id}>
                    <Link href={waypoint.href} onClick={() => setShowMobileMenu(false)}>
                      <time>{waypoint.time}</time>
                      <Icon aria-hidden="true" />
                      <span>{waypoint.title}</span>
                    </Link>
                  </li>
                );
              })}
            </ol>
            <div className="yh-sheet-cards">
              <Link href="/billing" onClick={() => setShowMobileMenu(false)}>
                <Crown aria-hidden="true" />
                <span>
                  <b>{hasActiveMembership(user) ? "会员权益已生效" : `月度 ¥${yuan(monthly.amount_cents)} · 年度 ¥${yuan(annual.amount_cents)}`}</b>
                  <small>{hasActiveMembership(user) ? `有效至 ${membershipExpiryText(user) || "当前周期结束"}` : "会员期内核心功能不限次数"}</small>
                </span>
              </Link>
              <Link href="/credits" onClick={() => setShowMobileMenu(false)}>
                <CreditCard aria-hidden="true" />
                <span>
                  <b>购买次数 · 1 元 / 次</b>
                  <small>会员期内不消耗，过期后继续可用</small>
                </span>
              </Link>
            </div>
            {hydrated && user ? (
              <div className="yh-sheet-account">
                <p>
                  <UserRound aria-hidden="true" />
                  <span>{accountDisplay}</span>
                  <small>{userBalanceText(user)}</small>
                </p>
                {user.role === "admin" ? (
                  <Link href="/admin" onClick={() => setShowMobileMenu(false)}>
                    <ShieldCheck aria-hidden="true" />
                    管理台
                  </Link>
                ) : null}
                <Link href="/account/orders" onClick={() => setShowMobileMenu(false)}>
                  <ReceiptText aria-hidden="true" />我的订单
                </Link>
                <button type="button" onClick={copyInvite}>
                  <Copy aria-hidden="true" />
                  {inviteCopied ? "已复制邀请链接" : "复制邀请链接"}
                </button>
                <button type="button" onClick={mobileLogout}>
                  <LogOut aria-hidden="true" />
                  退出登录
                </button>
              </div>
            ) : (
              <div className="yh-sheet-guest">
                <Link className="yh-sheet-register" href="/auth?mode=register" onClick={() => setShowMobileMenu(false)}>免费注册，领取 5 次</Link>
                <Link className="yh-mobile-account-login" href="/auth" onClick={() => setShowMobileMenu(false)}>已有账号登录</Link>
              </div>
            )}
            <button className="yh-sheet-feedback" type="button" onClick={() => { setShowMobileMenu(false); scrollToFeedback(); }}>
              <MessageSquare aria-hidden="true" />
              反馈建议
            </button>
          </nav>
        </div>
      ) : null}

      <div id="yh-main">
        <section className="yh-hero" aria-labelledby="yh-hero-title">
          <div className="yh-hero__copy">
            <p className="yh-eyebrow">
              <span className="yh-eyebrow__dot" aria-hidden="true" />
              AI 交易决策助手 · 为新手设计
            </p>
            <h1 id="yh-hero-title">
              <span>先看懂市场，</span>
              <span>再决定交易。</span>
            </h1>
            <p className="yh-hero__lede">
              从开盘前的研报到收盘后的复盘，七个工具按交易日的节奏排好。打开盈航，它会告诉你<em>此刻</em>最该看什么。
            </p>
            <div className="yh-hero-actions">
              <Link className="yh-cta" href={user ? "/auction-strength" : "/auth"}>
                现在开始
                <ArrowRight aria-hidden="true" />
              </Link>
              <a className="yh-cta yh-cta--quiet" href="#pricing">
                看看价格
              </a>
            </div>
            <ul className="yh-hero__facts" aria-label="使用方式">
              <li><b>5 次</b><span>注册即送</span></li>
              <li><b>¥1</b><span>按次使用</span></li>
              <li><b>¥{yuan(monthly.amount_cents)}</b><span>月度会员不限次</span></li>
            </ul>
            {hydrated && user && user.role !== "admin" ? (
              <div className="yh-hero__account">
                <span>{userBalanceText(user)}</span>
                <button type="button" onClick={copyInvite}>
                  <Copy aria-hidden="true" />
                  {inviteCopied ? "已复制邀请链接" : "邀请好友，各得次数"}
                </button>
              </div>
            ) : null}
          </div>
          <div className="yh-hero__clock">
            <TradingDayClock />
          </div>
        </section>

        <div className="yh-disclaimer">
          <FinancialDisclaimer compact />
        </div>

        <section className="yh-route" aria-labelledby="yh-route-title">
          <header className="yh-section-head" data-reveal>
            <span className="yh-kicker">01 · 一个交易日</span>
            <h2 id="yh-route-title"><span>七个工具，</span><span>沿着交易日排好。</span></h2>
            <p>不用记住每个功能在哪。按时间走：早上看消息，开盘看强势股，盘中看真实强弱，收盘后复盘、做计划。</p>
          </header>
          <ol className="yh-route__list">
            {WAYPOINTS.map((waypoint, index) => {
              const Icon = waypoint.icon;
              const now = focusIds.includes(waypoint.id);
              return (
                <li key={waypoint.id} className={now ? "is-now" : undefined} data-reveal style={{ transitionDelay: `${index * 60}ms` }}>
                  <Link href={waypoint.href} aria-describedby={`yh-wp-${waypoint.id}`}>
                    <div className="yh-route__time">
                      <time>{waypoint.time}</time>
                      {now ? <span className="yh-route__now">现在</span> : null}
                    </div>
                    <div className="yh-route__body">
                      <span className="yh-route__label">{waypoint.label}</span>
                      <h3>
                        <Icon aria-hidden="true" />
                        {waypoint.title}
                      </h3>
                      <p id={`yh-wp-${waypoint.id}`}>{waypoint.summary}</p>
                      <ul>
                        {waypoint.points.map((point) => <li key={point}>{point}</li>)}
                      </ul>
                    </div>
                    <ArrowUpRight className="yh-route__go" aria-hidden="true" />
                  </Link>
                </li>
              );
            })}
          </ol>
        </section>

        <section className="yh-record" aria-labelledby="yh-record-title">
          <div className="yh-record__copy" data-reveal>
            <span className="yh-kicker">02 · 公开记录</span>
            <h2 id="yh-record-title"><span>TOP5 第 1 名，</span><span>每天公开记账。</span></h2>
            <p>09:25 选出后按开盘价记录买入，次日记录结果。不挑好的说，也不删差的。</p>
            <dl className="yh-record__stats">
              <div><dt>样本</dt><dd>{sampleCount}<small> 个交易日</small></dd></div>
              <div><dt>胜率</dt><dd>{performance.win_rate_text}</dd></div>
              <div><dt>近 5 日平均</dt><dd className={performance.recent_5_avg_return >= 0 ? "yh-up" : "yh-down"}>{performance.recent_5_avg_return_text}</dd></div>
            </dl>
            <p className="yh-record__note">样本量有限，历史表现不代表未来收益；仅供学习研究，不构成投资建议。</p>
            <Link className="yh-link" href="/auction-strength">
              查看今日 TOP5
              <ArrowRight aria-hidden="true" />
            </Link>
          </div>
          <div className="yh-ledger" data-reveal>
            <table>
              <caption>最近 {ledgerRows.length} 个交易日 · 第 1 名（红涨绿跌）</caption>
              <thead>
                <tr>
                  <th scope="col">日期</th>
                  <th scope="col">股票</th>
                  <th scope="col">次日收益</th>
                </tr>
              </thead>
              <tbody>
                {ledgerRows.map((row) => (
                  <tr key={`${row.trade_date}-${row.code || row.name}`}>
                    <td>{row.trade_date.slice(5)}</td>
                    <td>{row.name}<small>{row.code}</small></td>
                    <td className={row.return_pct >= 0 ? "yh-up" : "yh-down"}>{row.return_text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="yh-pricing" id="pricing" aria-labelledby="yh-pricing-title">
          <header className="yh-section-head" data-reveal>
            <span className="yh-kicker">03 · 价格</span>
            <h2 id="yh-pricing-title"><span>先免费试，</span><span>再决定怎么付。</span></h2>
            <p>注册送 5 次。偶尔用就按次付；每天都用，会员更省。</p>
          </header>
          <div className="yh-plans">
            <article className="yh-plan" data-reveal>
              <h3>按次</h3>
              <p className="yh-plan__price"><small>¥</small>1<span>/ 次</span></p>
              <p>余额不过期。会员期内不消耗，会员到期后继续可用。</p>
              <Link className="yh-cta yh-cta--quiet" href="/credits">购买次数</Link>
            </article>
            <article className="yh-plan" data-reveal>
              <h3>{monthly.plan_name}</h3>
              <p className="yh-plan__price"><small>¥</small>{yuan(monthly.amount_cents)}<span>/ {monthly.duration_days} 天</span></p>
              <p>会员期内核心功能不限次数（价值投资研究每月含 10 次），适合先体验一个月。</p>
              <Link className="yh-cta yh-cta--quiet" href={`/billing?plan_id=${encodeURIComponent(monthly.id)}`}>开通{monthly.plan_name}</Link>
            </article>
            <article className="yh-plan is-featured" data-reveal>
              <span className="yh-plan__flag">推荐</span>
              <h3>{annual.plan_name}</h3>
              <p className="yh-plan__price"><small>¥</small>{yuan(annual.amount_cents)}<span>/ {annual.duration_days} 天</span></p>
              <p>{annualSaving > 0 ? `比连续买 12 个月省 ¥${annualSaving}。` : ""}一年里每个交易日都在。</p>
              <Link className="yh-cta" href={`/billing?plan_id=${encodeURIComponent(annual.id)}`}>开通{annual.plan_name}</Link>
            </article>
          </div>
          <p className="yh-pricing__note">微信扫码付款，人工核款开通。付款时请备注订单号；如遇问题请勿重复付款，联系客服处理。</p>
        </section>

        <section id="feedback" className="yh-feedback" aria-labelledby="yh-feedback-title">
          <div className="yh-feedback__copy" data-reveal>
            <span className="yh-kicker">04 · 一起改进</span>
            <h2 id="yh-feedback-title"><span>建议被采纳，</span><span>送 10 次。</span></h2>
            <p>告诉我们报告哪里不准、计划缺了什么、页面哪里别扭。越具体越容易被采纳，管理员会直接把次数加到你的账号。</p>
          </div>
          <form className="yh-feedback__form" onSubmit={submitFeedback} data-reveal>
            <label>
              <span>类别</span>
              <select value={feedbackCategory} onChange={(event) => setFeedbackCategory(event.target.value)}>
                <option>产品建议</option>
                <option>报告准确性</option>
                <option>页面体验</option>
                <option>付费与次数</option>
              </select>
            </label>
            <label>
              <span>你的建议</span>
              <textarea
                value={feedback}
                onChange={(event) => setFeedback(event.target.value)}
                placeholder="写下你的建议。越具体，越容易被采纳。"
                rows={5}
              />
            </label>
            <label className="yh-upload">
              <ImagePlus aria-hidden="true" />
              <span>{feedbackImage ? feedbackImage.name : "添加截图（可选，最大 5MB）"}</span>
              <input
                accept="image/jpeg,image/png,image/webp,image/gif"
                onChange={(event) => setFeedbackImage(event.target.files?.[0] || null)}
                ref={feedbackImageRef}
                type="file"
              />
            </label>
            <button className="yh-cta" type="submit">
              <MessageSquare aria-hidden="true" />
              提交反馈
            </button>
            {feedbackMessage ? <p role="status">{feedbackMessage}</p> : null}
          </form>
        </section>
      </div>

      <footer className="yh-footer">
        <div>
          <b>盈航</b>
          <span>AI 交易决策助手 · 仅供学习研究，不构成投资建议</span>
        </div>
        <nav aria-label="页脚">
          <Link href="/billing">会员</Link>
          <Link href="/credits">次数</Link>
          <a href="#feedback">反馈</a>
          <Link href="/admin/login">运营登录</Link>
        </nav>
      </footer>
    </main>
  );
}
