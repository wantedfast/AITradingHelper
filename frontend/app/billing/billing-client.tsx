"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { ArrowLeft, CheckCircle2, Clock3, Crown, CreditCard, Loader2, QrCode, RefreshCw, Send, ShieldCheck, Sparkles } from "lucide-react";
import { ApiError, apiFetch, getAuthToken, storeUser, type UserProfile } from "@/lib/auth-client";

export type CheckoutInfo = {
  business_hours: string;
  confirmation_eta: string;
  support_channel: string;
  policy_note: string;
};

export type MembershipPlan = {
  id: string;
  plan_name: string;
  amount_cents: number;
  duration_days: number;
  alipay_qr_url?: string;
  wechat_qr_url?: string;
  manual_checkout?: CheckoutInfo;
};

type OrderPayload = {
  id: number;
  order_no: string;
  plan_name: string;
  amount_cents: number;
  package_id?: string;
  duration_days?: number;
  status: "pending" | "submitted" | "paid" | "rejected" | string;
  payment_method?: string;
  payer_name?: string;
  payer_note?: string;
  payer_paid_at?: string;
  submitted_amount_cents?: number | null;
  admin_note?: string;
  paid_at?: string | null;
  admin_notification?: { sent?: boolean; error?: string; skipped?: boolean };
};

export type CatalogPayload = {
  plans: MembershipPlan[];
  checkout: CheckoutInfo;
  order?: OrderPayload | null;
  user?: UserProfile | null;
};

type PaymentDraft = {
  payment_method: "alipay" | "wechat";
  payer_name: string;
  payer_paid_at: string;
  submitted_amount_yuan: string;
  payer_note: string;
};

function buildAuthRedirect(planId: string, source: string, feature: string) {
  const redirect = `/billing?plan_id=${encodeURIComponent(planId)}`;
  return `/auth?mode=register&redirect=${encodeURIComponent(redirect)}&plan_id=${encodeURIComponent(planId)}&source=${encodeURIComponent(source)}&feature=${encodeURIComponent(feature)}`;
}

export default function BillingPage({ initialCatalog }: { initialCatalog: CatalogPayload | null }) {
  return (
    <Suspense fallback={<main className="billing-page" />}>
      <BillingPageContent initialCatalog={initialCatalog} />
    </Suspense>
  );
}

function BillingPageContent({ initialCatalog }: { initialCatalog: CatalogPayload | null }) {
  const router = useRouter();
  const params = useSearchParams();
  const requestedPlanId = params.get("plan_id") || "";
  const initialRequestedPlan = initialCatalog?.plans.find((plan) => plan.id === requestedPlanId);
  const initialRequestInvalid = Boolean(requestedPlanId && !initialRequestedPlan);
  const initialPreferredPlan = initialRequestInvalid
    ? undefined
    : initialRequestedPlan || initialCatalog?.plans.find(isAnnualPlan) || initialCatalog?.plans[0];
  // Keep the server render and the browser's first render identical. The
  // session token is browser-only state and is hydrated immediately below.
  const [token, setToken] = useState("");
  const [sessionReady, setSessionReady] = useState(false);
  const [plans, setPlans] = useState<MembershipPlan[]>(initialCatalog?.plans || []);
  const [checkout, setCheckout] = useState<CheckoutInfo>(initialCatalog?.checkout || {
    business_hours: "工作日 10:00-18:00",
    confirmation_eta: "提交付款信息后由运营在客服工作时间内人工核对",
    support_channel: "如长时间未处理，请联系站内反馈或运营客服。",
    policy_note: "当前为人工核款开通，退款与发票按人工客服规则处理。",
  });
  const [selectedPlanId, setSelectedPlanId] = useState(initialPreferredPlan?.id || "");
  const [invalidRequestedPlan, setInvalidRequestedPlan] = useState(initialRequestInvalid);
  const [order, setOrder] = useState<OrderPayload | null>(null);
  const [loading, setLoading] = useState(!initialCatalog?.plans?.length);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [paymentMessage, setPaymentMessage] = useState("");
  const [draft, setDraft] = useState<PaymentDraft>({
    payment_method: "alipay",
    payer_name: "",
    payer_paid_at: "",
    submitted_amount_yuan: initialPreferredPlan ? (initialPreferredPlan.amount_cents / 100).toFixed(2) : "59.00",
    payer_note: "",
  });

  const selectedPlan = useMemo(
    () => plans.find((plan) => plan.id === selectedPlanId),
    [plans, selectedPlanId],
  );

  useEffect(() => {
    if (!sessionReady) return;
    if (!token && initialCatalog) {
      setPlans(initialCatalog.plans || []);
      setCheckout(initialCatalog.checkout || checkout);
      setOrder(null);
      setSelectedPlanId(initialPreferredPlan?.id || "");
      setInvalidRequestedPlan(initialRequestInvalid);
      setDraft((current) => ({
        ...current,
        submitted_amount_yuan: initialPreferredPlan
          ? (initialPreferredPlan.amount_cents / 100).toFixed(2)
          : current.submitted_amount_yuan,
      }));
      setMessage(initialRequestInvalid ? "所选套餐已失效，请重新选择有效套餐。" : "");
      setPaymentMessage("");
      setLoading(false);
      return;
    }
    void loadCatalog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedPlanId, sessionReady, token]);

  useEffect(() => {
    function handleAuth() {
      setToken(getAuthToken());
      setSessionReady(true);
    }
    handleAuth();
    window.addEventListener("ai-trade-auth", handleAuth);
    return () => window.removeEventListener("ai-trade-auth", handleAuth);
  }, []);

  useEffect(() => {
    if (!order || order.status === "paid") return;
    const timer = window.setInterval(() => {
      void refreshOrder(order.id, true);
    }, 4000);
    return () => window.clearInterval(timer);
    // refreshOrder intentionally uses the latest component state while the
    // interval lifetime is keyed only to the current order.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [order]);

  async function loadCatalog() {
    if (!plans.length) setLoading(true);
    setMessage("");
    try {
      const payload = await apiFetch<CatalogPayload>("/api/public/membership/plans");
      setPlans(payload.plans || []);
      setCheckout(payload.checkout || checkout);
      const requestedPlan = (payload.plans || []).find((plan) => plan.id === requestedPlanId);
      const requestIsInvalid = Boolean(requestedPlanId && !requestedPlan);
      const preferredPlan = requestIsInvalid ? undefined : requestedPlan || payload.plans?.find(isAnnualPlan) || payload.plans?.[0];
      setInvalidRequestedPlan(requestIsInvalid);
      setSelectedPlanId(preferredPlan?.id || "");
      if (requestIsInvalid) setMessage("所选套餐已失效，请重新选择有效套餐。");
      if (preferredPlan) {
        setDraft((current) => ({ ...current, submitted_amount_yuan: (preferredPlan.amount_cents / 100).toFixed(2) }));
      }
      if (token) {
        const latest = await apiFetch<CatalogPayload>("/api/pay/membership/orders/latest");
        if (latest.plans?.length) setPlans(latest.plans);
        if (latest.checkout) setCheckout(latest.checkout);
        setOrder(latest.order || null);
        if (latest.order?.package_id && latest.plans?.some((plan) => plan.id === latest.order?.package_id)) {
          setSelectedPlanId(latest.order.package_id);
          setInvalidRequestedPlan(false);
        }
        if (latest.user) storeUser(latest.user);
      }
    } catch (error) {
      if (!handleExpiredSession(error)) {
        setMessage(error instanceof Error ? error.message : "读取会员套餐失败");
      }
    } finally {
      setLoading(false);
    }
  }

  function selectPlan(plan: MembershipPlan) {
    if (order) return;
    setSelectedPlanId(plan.id);
    setInvalidRequestedPlan(false);
    setDraft((current) => ({ ...current, submitted_amount_yuan: (plan.amount_cents / 100).toFixed(2) }));
    setMessage("");
  }

  async function createMembershipOrder() {
    if (!selectedPlan || creating) return;
    // Read the token at interaction time so a click immediately after
    // hydration cannot observe the server-rendered empty session state.
    if (!getAuthToken()) {
      router.push(buildAuthRedirect(selectedPlan.id, "pricing", "membership"));
      return;
    }
    setCreating(true);
    setMessage("");
    try {
      const payload = await apiFetch<CatalogPayload>("/api/pay/membership/orders", {
        method: "POST",
        body: JSON.stringify({ plan_id: selectedPlan.id }),
      });
      if (payload.plans?.length) setPlans(payload.plans);
      if (payload.checkout) setCheckout(payload.checkout);
      setOrder(payload.order || null);
      if (payload.user) storeUser(payload.user);
      setDraft((current) => ({ ...current, submitted_amount_yuan: ((payload.order?.amount_cents || selectedPlan.amount_cents) / 100).toFixed(2) }));
      setMessage("订单已创建。付款后提交付款信息，系统会通知管理员人工确认。");
    } catch (error) {
      if (!handleExpiredSession(error)) {
        setMessage(error instanceof Error ? error.message : "创建会员订单失败");
      }
    } finally {
      setCreating(false);
    }
  }

  async function submitPayment() {
    if (!order || submitting) return;
    setSubmitting(true);
    setMessage("");
    setPaymentMessage("");
    try {
      const payload = await apiFetch<CatalogPayload>(`/api/pay/membership/orders/${order.id}/submit`, {
        method: "POST",
        body: JSON.stringify({
          payment_method: draft.payment_method,
          payer_name: draft.payer_name,
          payer_paid_at: draft.payer_paid_at,
          submitted_amount_cents: Math.round(Number(draft.submitted_amount_yuan || "0") * 100),
          payer_note: draft.payer_note || order.order_no,
        }),
      });
      setOrder(payload.order || null);
      if (payload.user) storeUser(payload.user);
      const nextMessage = payload.order?.admin_notification?.sent === false
        ? `付款信息已提交，但管理员提醒发送失败：${payload.order.admin_notification.error || "未知原因"}`
        : "付款信息已提交，等待管理员人工核款开通。";
      setMessage(nextMessage);
      setPaymentMessage(nextMessage);
    } catch (error) {
      if (handleExpiredSession(error)) return;
      const nextMessage = error instanceof Error ? error.message : "提交付款信息失败";
      setMessage(nextMessage);
      setPaymentMessage(nextMessage);
    } finally {
      setSubmitting(false);
    }
  }

  async function refreshOrder(orderId: number, silent = false) {
    if (!silent) setMessage("");
    try {
      const payload = await apiFetch<{ order: OrderPayload; user?: UserProfile | null }>(`/api/orders/${orderId}`);
      setOrder(payload.order);
      if (payload.user) storeUser(payload.user);
      if (payload.order.status === "paid") {
        setMessage("会员已开通。");
      } else if (!silent) {
        setMessage(orderStatusText(payload.order.status));
      }
    } catch (error) {
      if (!handleExpiredSession(error) && !silent) {
        setMessage(error instanceof Error ? error.message : "刷新订单失败");
      }
    }
  }

  function handleExpiredSession(error: unknown) {
    if (!(error instanceof ApiError) || error.status !== 401) return false;
    setOrder(null);
    setMessage("");
    setPaymentMessage("");
    return true;
  }

  return (
    <main className="billing-page">
      <section className="billing-shell">
        <header className="billing-topbar">
          <Link href="/">
            <ArrowLeft />
            返回首页
          </Link>
          <div>
            <span>YINGHANG MEMBERSHIP</span>
            <h1>开通盈航会员</h1>
            <p>游客可先查看价格与付款方式；创建订单时再登录。会员期内五项核心功能不限次数使用。</p>
          </div>
        </header>

        {message ? <div className="billing-message">{message}</div> : null}
        {loading ? <div className="billing-message">正在读取会员套餐...</div> : null}

        <section className="billing-grid">
          <div className="billing-packages">
            <div className="billing-package-heading">
              <span><Crown />选择会员套餐</span>
              <small>{order ? "订单已创建，套餐已锁定" : "年度会员更划算，月度适合先体验"}</small>
            </div>
            <div className="billing-plan-options" role="radiogroup" aria-label="会员套餐">
              {plans.map((plan) => {
                const annual = isAnnualPlan(plan);
                const active = selectedPlan?.id === plan.id;
                const annualSavings = annual ? membershipAnnualSavings(plans, plan) : 0;
                return (
                  <button
                    key={plan.id}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    disabled={Boolean(order)}
                    className={`${active ? "active" : ""}${annual ? " is-recommended" : ""}`.trim()}
                    onClick={() => selectPlan(plan)}
                  >
                    <span className="billing-plan-icon">{annual ? <Sparkles /> : <CreditCard />}</span>
                    <span className="billing-plan-copy">
                      <span className="billing-plan-name-row">
                        <b>{plan.plan_name}</b>
                        {annual ? <em>推荐</em> : null}
                      </span>
                      <small>{plan.duration_days} 天会员权益 · 五项功能不限次数</small>
                      <i>{annualSavings > 0 ? `比连续购买月度节省 ¥${annualSavings}` : annual ? "适合长期使用" : "适合先体验一个月"}</i>
                    </span>
                    <strong><small>¥</small>{(plan.amount_cents / 100).toFixed(0)}</strong>
                  </button>
                );
              })}
            </div>
            <div className="billing-empty-qr">
              <ShieldCheck />
              <p>人工核款开通。创建订单后请按订单金额付款，再提交付款信息等待审核。</p>
            </div>
          </div>

          <aside className="billing-checkout">
            <div className="billing-card-head">
              <QrCode />
              <span>
                <b>{order ? `${order.plan_name} · 订单 ${order.order_no}` : selectedPlan?.plan_name || "会员套餐"}</b>
                <small>{order ? orderStatusText(order.status) : token ? "先创建订单，再扫码付款" : "价格公开可见，登录后创建订单"}</small>
              </span>
            </div>

            {order ? (
              <>
                <div className="billing-qr-row">
                  <QrBox title="支付宝" src={selectedPlan?.alipay_qr_url || ""} />
                  <QrBox title="微信" src={selectedPlan?.wechat_qr_url || ""} />
                </div>
                <div className="billing-order">
                  <span>订单号</span>
                  <b>{order.order_no}</b>
                  <span>状态</span>
                  <b>{orderStatusText(order.status)}</b>
                  <span>会员套餐</span>
                  <b>{order.plan_name}</b>
                </div>
                {order.status === "rejected" ? (
                  <div className="billing-inline-message" role="alert">
                    <b>付款核对未通过：{order.admin_note || "管理员未填写具体原因"}</b>
                    <span>请根据原因核对付款信息；仍有疑问请通过下方支持渠道联系客服。</span>
                  </div>
                ) : null}
                {order.status !== "paid" ? (
                  <div className="billing-payment-form">
                    {order.status === "submitted" ? <div className="billing-inline-message">付款信息已提交，等待管理员人工确认到账。</div> : null}
                    <label>
                      <span>付款方式</span>
                      <select value={draft.payment_method} onChange={(event) => setDraft((current) => ({ ...current, payment_method: event.target.value as PaymentDraft["payment_method"] }))}>
                        <option value="alipay">支付宝</option>
                        <option value="wechat">微信</option>
                      </select>
                    </label>
                    <label>
                      <span>付款人昵称或姓名</span>
                      <input value={draft.payer_name} onChange={(event) => setDraft((current) => ({ ...current, payer_name: event.target.value }))} />
                    </label>
                    <label>
                      <span>付款时间</span>
                      <input type="datetime-local" value={draft.payer_paid_at} onChange={(event) => setDraft((current) => ({ ...current, payer_paid_at: event.target.value }))} />
                    </label>
                    <label>
                      <span>实付金额</span>
                      <input value={draft.submitted_amount_yuan} readOnly aria-readonly="true" />
                    </label>
                    <label>
                      <span>付款备注</span>
                      <input value={draft.payer_note} placeholder={order.order_no} onChange={(event) => setDraft((current) => ({ ...current, payer_note: event.target.value }))} />
                    </label>
                    <button className="billing-primary" type="button" onClick={submitPayment} disabled={submitting}>
                      {submitting ? <Loader2 className="spin-icon" /> : <Send />}
                      {submitting ? "正在提交" : "我已付款，通知管理员"}
                    </button>
                    {paymentMessage ? <div className="billing-inline-message">{paymentMessage}</div> : null}
                  </div>
                ) : null}
                <button className="billing-secondary" type="button" onClick={() => refreshOrder(order.id)}>
                  <RefreshCw />
                  刷新订单状态
                </button>
                {order.status === "paid" ? (
                  <div className="billing-paid">
                    <CheckCircle2 />
                    {order.plan_name}已开通
                  </div>
                ) : null}
              </>
            ) : (
              <button className="billing-primary" type="button" onClick={createMembershipOrder} disabled={!sessionReady || !selectedPlan || invalidRequestedPlan || creating || loading}>
                {creating ? <Loader2 className="spin-icon" /> : <CreditCard />}
                {creating ? "正在创建订单" : token ? `创建${selectedPlan?.plan_name || "会员"}订单` : "登录后创建订单"}
              </button>
            )}

            <div className="billing-empty-qr">
              <Clock3 />
              <p>{checkout.confirmation_eta}</p>
              <small>{checkout.business_hours}</small>
              <small>{checkout.support_channel}</small>
              <small>{checkout.policy_note}</small>
            </div>
          </aside>
        </section>
      </section>
    </main>
  );
}

function isAnnualPlan(plan: MembershipPlan) {
  return plan.id.toLowerCase().includes("annual") || plan.duration_days >= 300;
}

function membershipAnnualSavings(plans: MembershipPlan[], annualPlan: MembershipPlan) {
  const monthlyPlan = plans.find((plan) => !isAnnualPlan(plan));
  if (!monthlyPlan) return 0;
  return Math.max(0, Math.round((monthlyPlan.amount_cents * 12 - annualPlan.amount_cents) / 100));
}

function QrBox({ title, src }: { title: string; src: string }) {
  return (
    <div className="billing-qr">
      {src ? <Image src={src} alt={`${title}收款二维码`} width={180} height={180} unoptimized /> : <span>收款码暂未配置</span>}
      <code>{title}收款码</code>
    </div>
  );
}

function orderStatusText(status: string) {
  if (status === "pending") return "待付款";
  if (status === "submitted") return "待管理员确认";
  if (status === "paid") return "已开通";
  if (status === "rejected") return "异常，请联系客服";
  return status;
}
