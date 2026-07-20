"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { ArrowLeft, CheckCircle2, Clock3, CreditCard, Loader2, QrCode, RefreshCw, Send, ShieldCheck } from "lucide-react";
import { ApiError, apiFetch, getAuthToken, storeUser, type UserProfile } from "@/lib/auth-client";

type CheckoutInfo = {
  business_hours: string;
  confirmation_eta: string;
  support_channel: string;
  policy_note: string;
};

type CreditOrder = {
  id: number;
  order_no: string;
  plan_name: string;
  credits: number;
  amount_cents: number;
  status: "pending" | "submitted" | "paid" | "rejected" | string;
  payment_method?: string;
  payer_name?: string;
  payer_note?: string;
  payer_paid_at?: string;
  submitted_amount_cents?: number | null;
  admin_note?: string;
  admin_notification?: { sent?: boolean; error?: string; skipped?: boolean };
};

type CreditRules = {
  min_credits: number;
  max_credits: number;
  price_text: string;
  support_text: string;
};

type CreditPricing = {
  unit_price_cents: number;
  currency: string;
};

export type CreditCatalogPayload = {
  checkout: CheckoutInfo;
  pricing: CreditPricing;
  rules: CreditRules;
  order?: CreditOrder | null;
  user?: UserProfile | null;
};

type PaymentDraft = {
  payment_method: "alipay" | "wechat";
  payer_name: string;
  payer_paid_at: string;
  payer_note: string;
};

function buildAuthRedirect(credits: string) {
  const redirect = `/credits?credits=${encodeURIComponent(credits)}`;
  return `/auth?mode=register&redirect=${encodeURIComponent(redirect)}&credits=${encodeURIComponent(credits)}&source=${encodeURIComponent("pricing")}&feature=${encodeURIComponent("credits")}`;
}

export default function CreditsPage({ initialCatalog }: { initialCatalog: CreditCatalogPayload | null }) {
  return (
    <Suspense fallback={<main className="billing-page" />}>
      <CreditsPageContent initialCatalog={initialCatalog} />
    </Suspense>
  );
}

function CreditsPageContent({ initialCatalog }: { initialCatalog: CreditCatalogPayload | null }) {
  const router = useRouter();
  const params = useSearchParams();
  const requestedCredits = params.get("credits") || "";
  const [token, setToken] = useState("");
  const [sessionReady, setSessionReady] = useState(false);
  const [checkout, setCheckout] = useState<CheckoutInfo>(initialCatalog?.checkout || {
    business_hours: "工作日 10:00-18:00",
    confirmation_eta: "提交付款信息后由运营在客服工作时间内人工核对",
    support_channel: "如长时间未处理，请联系站内反馈或运营客服。",
    policy_note: "当前为人工核款开通，退款与发票按人工客服规则处理。",
  });
  const [pricing, setPricing] = useState<CreditPricing>(initialCatalog?.pricing || { unit_price_cents: 100, currency: "CNY" });
  const [rules, setRules] = useState<CreditRules>(initialCatalog?.rules || { min_credits: 1, max_credits: 10000, price_text: "1 元 / 次", support_text: "人工核款，确认后到账；退款、发票请联系人工客服处理。" });
  const [creditsInput, setCreditsInput] = useState(normalizeCreditsInput(requestedCredits, initialCatalog?.rules?.min_credits || 5));
  const [invalidRequestedCredits, setInvalidRequestedCredits] = useState(Boolean(requestedCredits) && !isPositiveInteger(requestedCredits));
  const [order, setOrder] = useState<CreditOrder | null>(null);
  const [loading, setLoading] = useState(!initialCatalog);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [paymentMessage, setPaymentMessage] = useState("");
  const [draft, setDraft] = useState<PaymentDraft>({
    payment_method: "alipay",
    payer_name: "",
    payer_paid_at: "",
    payer_note: "",
  });

  const parsedCredits = useMemo(() => parsePositiveInteger(creditsInput), [creditsInput]);
  const selectedAmountCents = parsedCredits ? parsedCredits * pricing.unit_price_cents : 0;
  const activeOrder = order && order.status !== "paid" ? order : null;

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
    if (!sessionReady) return;
    void loadCatalog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedCredits, sessionReady, token]);

  useEffect(() => {
    if (!activeOrder || activeOrder.status === "paid") return;
    const timer = window.setInterval(() => {
      void refreshOrder(activeOrder.id, true);
    }, 4000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeOrder?.id, activeOrder?.status]);

  async function loadCatalog() {
    if (!initialCatalog) setLoading(true);
    setMessage("");
    try {
      const payload = await apiFetch<CreditCatalogPayload>("/api/public/credits/catalog");
      setCheckout(payload.checkout);
      setPricing(payload.pricing);
      setRules(payload.rules);
      const invalidCredits = Boolean(requestedCredits) && !isPositiveInteger(requestedCredits);
      setInvalidRequestedCredits(invalidCredits);
      if (invalidCredits) setMessage("购买次数必须是正整数，请重新输入。");
      if (token) {
        const latest = await apiFetch<CreditCatalogPayload>("/api/pay/credits/orders/latest");
        setCheckout(latest.checkout);
        setPricing(latest.pricing);
        setRules(latest.rules);
        setOrder(latest.order || null);
        if (latest.user) storeUser(latest.user);
      } else {
        setOrder(null);
      }
    } catch (error) {
      if (!handleExpiredSession(error)) {
        setMessage(error instanceof Error ? error.message : "读取次数购买信息失败");
      }
    } finally {
      setLoading(false);
    }
  }

  async function createOrder() {
    if (!parsedCredits || creating) return;
    if (!getAuthToken()) {
      router.push(buildAuthRedirect(String(parsedCredits)));
      return;
    }
    setCreating(true);
    setMessage("");
    try {
      const payload = await apiFetch<CreditCatalogPayload>("/api/pay/credits/orders", {
        method: "POST",
        body: JSON.stringify({ credits: parsedCredits }),
      });
      setOrder(payload.order || null);
      setCheckout(payload.checkout);
      setPricing(payload.pricing);
      setRules(payload.rules);
      if (payload.user) storeUser(payload.user);
      setMessage("订单已创建。付款后提交付款信息，系统会通知管理员人工核款。");
    } catch (error) {
      if (!handleExpiredSession(error)) {
        setMessage(error instanceof Error ? error.message : "创建次数订单失败");
      }
    } finally {
      setCreating(false);
    }
  }

  async function submitPayment() {
    if (!activeOrder || submitting) return;
    setSubmitting(true);
    setMessage("");
    setPaymentMessage("");
    try {
      const payload = await apiFetch<{ order: CreditOrder; user?: UserProfile | null }>(`/api/pay/credits/orders/${activeOrder.id}/submit`, {
        method: "POST",
        body: JSON.stringify({
          payment_method: draft.payment_method,
          payer_name: draft.payer_name,
          payer_paid_at: draft.payer_paid_at,
          submitted_amount_cents: activeOrder.amount_cents,
          payer_note: draft.payer_note || activeOrder.order_no,
        }),
      });
      setOrder(payload.order || null);
      if (payload.user) storeUser(payload.user);
      const nextMessage = payload.order?.admin_notification?.sent === false
        ? `付款信息已提交，但管理员提醒发送失败：${payload.order.admin_notification.error || "未知原因"}`
        : "付款信息已提交，等待管理员人工核款到账。";
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
      const payload = await apiFetch<{ order: CreditOrder; user?: UserProfile | null }>(`/api/orders/${orderId}`);
      setOrder(payload.order || null);
      if (payload.user) storeUser(payload.user);
      if ((payload.order?.status || "") === "paid") {
        setMessage("次数已到账。");
      } else if (!silent && payload.order) {
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
    <main className="billing-page credits-page">
      <section className="billing-shell">
        <header className="billing-topbar">
          <Link href="/">
            <ArrowLeft />
            返回首页
          </Link>
          <div>
            <span>YINGHANG CREDITS</span>
            <h1>购买次数</h1>
            <p>游客可先查看规则；创建订单时再登录。固定按 1 元 / 次计费，金额始终由服务端按次数计算。</p>
          </div>
        </header>

        {message ? <div className="billing-message">{message}</div> : null}
        {loading ? <div className="billing-message">正在读取购买规则...</div> : null}

        <section className="billing-grid">
          <div className="billing-packages credits-config-panel">
            <div className="billing-package-heading">
              <span><CreditCard />输入购买次数</span>
              <small>会员有效期内购买的次数只累加不消耗；会员过期后余额继续可用。</small>
            </div>
            <label className="credits-quantity-row">
              <span>购买数量</span>
              <input
                type="number"
                min={rules.min_credits}
                max={rules.max_credits}
                step="1"
                value={creditsInput}
                onChange={(event) => setCreditsInput(event.target.value)}
                disabled={Boolean(activeOrder)}
              />
            </label>
            <div className="credits-summary">
              <article>
                <span>单价</span>
                <b>{rules.price_text}</b>
              </article>
              <article>
                <span>应付金额</span>
                <b>¥{(selectedAmountCents / 100).toFixed(2)}</b>
              </article>
              <article>
                <span>支持范围</span>
                <b>{rules.min_credits}-{rules.max_credits} 次</b>
              </article>
            </div>
            <div className="billing-empty-qr credits-rule-list">
              <ShieldCheck />
              <p>{rules.support_text}</p>
              <small>创建订单后，提交付款人昵称、付款时间和付款备注即可进入人工核款队列。</small>
              <small>若订单被驳回，会展示管理员原因，修正后可在原订单上重新提交。</small>
            </div>
          </div>

          <aside className="billing-checkout">
            <div className="billing-card-head">
              <QrCode />
              <span>
                <b>{activeOrder ? `${activeOrder.plan_name} · 订单 ${activeOrder.order_no}` : "次数购买订单"}</b>
                <small>{activeOrder ? orderStatusText(activeOrder.status) : token ? "先创建订单，再按订单金额付款" : "规则公开可见，登录后创建订单"}</small>
              </span>
            </div>

            {activeOrder ? (
              <>
                <div className="billing-order">
                  <span>订单号</span>
                  <b>{activeOrder.order_no}</b>
                  <span>购买次数</span>
                  <b>{activeOrder.credits} 次</b>
                  <span>应付金额</span>
                  <b>¥{(activeOrder.amount_cents / 100).toFixed(2)}</b>
                  <span>状态</span>
                  <b>{orderStatusText(activeOrder.status)}</b>
                </div>
                {activeOrder.status === "rejected" ? (
                  <div className="billing-inline-message" role="alert">
                    <b>付款核对未通过：{activeOrder.admin_note || "管理员未填写具体原因"}</b>
                    <span>请根据原因修正后重新提交付款信息；如需退款或发票，请联系人工客服。</span>
                  </div>
                ) : null}
                {activeOrder.status !== "submitted" ? (
                  <div className="billing-payment-form">
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
                      <input value={`¥${(activeOrder.amount_cents / 100).toFixed(2)}`} readOnly aria-readonly="true" />
                    </label>
                    <label>
                      <span>付款备注</span>
                      <input value={draft.payer_note} placeholder={activeOrder.order_no} onChange={(event) => setDraft((current) => ({ ...current, payer_note: event.target.value }))} />
                    </label>
                    <button className="billing-primary" type="button" onClick={submitPayment} disabled={submitting}>
                      {submitting ? <Loader2 className="spin-icon" /> : <Send />}
                      {submitting ? "正在提交" : "我已付款，通知管理员"}
                    </button>
                    {paymentMessage ? <div className="billing-inline-message">{paymentMessage}</div> : null}
                  </div>
                ) : <div className="billing-inline-message">付款信息已提交，等待管理员人工确认到账。</div>}
                <button className="billing-secondary" type="button" onClick={() => refreshOrder(activeOrder.id)}>
                  <RefreshCw />
                  刷新订单状态
                </button>
              </>
            ) : (
              <button className="billing-primary" type="button" onClick={createOrder} disabled={!sessionReady || !parsedCredits || invalidRequestedCredits || creating || loading}>
                {creating ? <Loader2 className="spin-icon" /> : <CreditCard />}
                {creating ? "正在创建订单" : token ? "创建次数订单" : "登录后创建订单"}
              </button>
            )}

            {order?.status === "paid" ? (
              <>
                <div className="billing-paid">
                  <CheckCircle2 />
                  最近一笔订单已到账：{order.credits} 次
                </div>
                <button className="billing-secondary" type="button" onClick={createOrder} disabled={!parsedCredits || creating}>
                  <CreditCard />
                  再购买一单
                </button>
              </>
            ) : null}

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

function normalizeCreditsInput(raw: string, fallback: number) {
  return isPositiveInteger(raw) ? raw : String(fallback);
}

function isPositiveInteger(raw: string) {
  return /^[1-9]\d*$/.test(raw.trim());
}

function parsePositiveInteger(raw: string) {
  if (!isPositiveInteger(raw)) return 0;
  return Number(raw);
}

function orderStatusText(status: string) {
  if (status === "pending") return "待付款";
  if (status === "submitted") return "待管理员确认";
  if (status === "paid") return "已到账";
  if (status === "rejected") return "异常，请修正后重提";
  return status;
}
