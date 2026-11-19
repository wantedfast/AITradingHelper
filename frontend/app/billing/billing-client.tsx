"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, CheckCircle2, Clock3, Crown, CreditCard, Loader2, QrCode, RefreshCw, Send, ShieldCheck, Sparkles, XCircle } from "lucide-react";
import "../yh-tokens.css";
import "../billing-theme.css";
import { ApiError, apiFetch, getAuthToken, storeUser, type UserProfile } from "@/lib/auth-client";
import {
  type OrderPayload, OPEN_ORDER_STATUSES, orderStatusText, confirmCancellation, cancelMembershipOrder,
  clearDraft, saveOpenOrderSnapshot, loadOpenOrderSnapshot, DRAFT_KEY_PREFIX, safeStorage,
} from "@/lib/membership-orders";

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
  wechat_qr_url?: string;
  manual_checkout?: CheckoutInfo;
};

export type CatalogPayload = {
  plans: MembershipPlan[];
  checkout: CheckoutInfo;
  order?: OrderPayload | null;
  user?: UserProfile | null;
};

type PaymentDraft = {
  payer_name: string;
  payer_paid_at: string;
  submitted_amount_yuan: string;
  payer_note: string;
};

type SubmitFailure = { retryable: boolean; message: string } | null;

// Payment calls must fail fast and visibly during an outage so the user is
// told not to pay twice, instead of watching a spinner indefinitely.
const PAYMENT_TIMEOUT_MS = 20_000;
const PAYMENT_SUBMIT_TIMEOUT_MS = 35_000;
const CREATE_KEY_PREFIX = "membership_checkout_request:";

function isOpenOrder(order: OrderPayload | null | undefined): order is OrderPayload {
  return Boolean(order && OPEN_ORDER_STATUSES.has(order.status));
}

function newRequestId() {
  const random = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  return `mco-${random}`;
}

// The same idempotency key is reused until the server confirms the order, so a
// timeout or 5xx followed by a retry can never produce a second order.
function checkoutRequestId(planId: string) {
  const storage = safeStorage("session");
  const key = `${CREATE_KEY_PREFIX}${planId}`;
  const existing = storage?.getItem(key);
  if (existing) return existing;
  const created = newRequestId();
  storage?.setItem(key, created);
  return created;
}

function clearCheckoutRequestId(planId: string) {
  safeStorage("session")?.removeItem(`${CREATE_KEY_PREFIX}${planId}`);
}

function loadDraft(orderId: number): Partial<PaymentDraft> | null {
  const raw = safeStorage("local")?.getItem(`${DRAFT_KEY_PREFIX}${orderId}`);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<PaymentDraft>;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function saveDraft(orderId: number, draft: PaymentDraft) {
  try {
    safeStorage("local")?.setItem(`${DRAFT_KEY_PREFIX}${orderId}`, JSON.stringify(draft));
  } catch {
    // Storage full or blocked: the in-memory draft still works.
  }
}


function localDateTimeValue(date: Date) {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function isRetryableError(error: unknown) {
  // status 0 = the request never reached the server (connection refused,
  // DNS, offline) - exactly the 2026-11-18 outage - and must be retryable.
  if (!(error instanceof ApiError)) return true;
  return error.status === 0 || error.status >= 500 || error.status === 408 || error.status === 429;
}

function stripEndPunctuation(text: string) {
  return text.replace(/[。.！!？?\s]+$/, "");
}

function buildAuthRedirect(planId: string, source: string, feature: string) {
  const redirect = `/billing?plan_id=${encodeURIComponent(planId)}`;
  return `/auth?mode=register&redirect=${encodeURIComponent(redirect)}&plan_id=${encodeURIComponent(planId)}&source=${encodeURIComponent(source)}&feature=${encodeURIComponent(feature)}`;
}


export default function BillingPage({ initialCatalog }: { initialCatalog: CatalogPayload | null }) {
  return (
    <Suspense fallback={<main className="billing-page yh-billing" />}>
      <BillingPageContent initialCatalog={initialCatalog} />
    </Suspense>
  );
}

function BillingPageContent({ initialCatalog }: { initialCatalog: CatalogPayload | null }) {
  const router = useRouter();
  const params = useSearchParams();
  const requestedPlanId = params.get("plan_id") || "";
  const requestedOrderId = params.get("order_id");
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
  const [cancelling, setCancelling] = useState(false);
  const [message, setMessage] = useState("");
  const [paymentMessage, setPaymentMessage] = useState("");
  const [submitFailure, setSubmitFailure] = useState<SubmitFailure>(null);
  const [account, setAccount] = useState<UserProfile | null>(null);
  const [fieldError, setFieldError] = useState<"" | "payer_name" | "payer_paid_at">("");
  const [copied, setCopied] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);

  function rememberUser(user: UserProfile) {
    storeUser(user);
    setAccount(user);
  }
  const [draft, setDraft] = useState<PaymentDraft>({
    payer_name: "",
    payer_paid_at: "",
    submitted_amount_yuan: initialPreferredPlan ? (initialPreferredPlan.amount_cents / 100).toFixed(2) : "59.00",
    payer_note: "",
  });
  // Synchronous guards: React state updates are async, so two fast clicks can
  // both observe `creating === false`.
  const creatingRef = useRef(false);
  const catalogRevision = useRef(0);
  const submittingRef = useRef(false);
  const draftOrderIdRef = useRef<number | null>(null);

  const selectedPlan = useMemo(
    () => plans.find((plan) => plan.id === selectedPlanId),
    [plans, selectedPlanId],
  );
  const checkoutOrder = isOpenOrder(order) ? order : null;

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
    return () => { catalogRevision.current += 1; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedPlanId, requestedOrderId, sessionReady, token]);

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
    // Only a submitted order changes without the user acting (admin confirms
    // or rejects it). Poll gently and not from background tabs: the
    // production host is small and many idle tabs add up.
    if (!checkoutOrder || checkoutOrder.status !== "submitted") return;
    const orderId = checkoutOrder.id;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refreshOrder(orderId, true);
    }, 10_000);
    const onVisible = () => {
      if (document.visibilityState === "visible") void refreshOrder(orderId, true);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
    // refreshOrder intentionally uses the latest component state while the
    // interval lifetime is keyed only to the current order.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkoutOrder?.id, checkoutOrder?.status]);

  // Restore the payment form for a resumed order: server data wins (it is what
  // the admin sees), otherwise fall back to what this browser saved locally.
  useEffect(() => {
    if (!checkoutOrder || draftOrderIdRef.current === checkoutOrder.id) return;
    draftOrderIdRef.current = checkoutOrder.id;
    const saved = loadDraft(checkoutOrder.id) || {};
    setDraft({
      payer_name: checkoutOrder.payer_name || saved.payer_name || "",
      // Prefill "now" so an unsupported/blank datetime picker (some in-app
      // browsers) never blocks the submit; the user can still correct it.
      payer_paid_at: checkoutOrder.payer_paid_at || saved.payer_paid_at || localDateTimeValue(new Date()),
      submitted_amount_yuan: (checkoutOrder.amount_cents / 100).toFixed(2),
      payer_note: checkoutOrder.payer_note || saved.payer_note || "",
    });
  }, [checkoutOrder]);

  useEffect(() => {
    if (!checkoutOrder || draftOrderIdRef.current !== checkoutOrder.id) return;
    saveDraft(checkoutOrder.id, draft);
  }, [checkoutOrder, draft]);

  useEffect(() => {
    if (order?.status === "paid") clearDraft(order.id);
    // Only trust server answers here; `order` is null both before loading and
    // after a confirmed paid/cancelled order, handled in loadCatalog/cancel.
    if (order) saveOpenOrderSnapshot(order);
  }, [order]);

  async function loadCatalog() {
    const revision = ++catalogRevision.current;
    if (requestedOrderId !== null) setOrder(null);
    setLoadFailed(false);
    if (!plans.length || requestedOrderId !== null) setLoading(true);
    setMessage("");
    try {
      const payload = await apiFetch<CatalogPayload>("/api/public/membership/plans");
      if (revision !== catalogRevision.current) return;
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
        const latest = await apiFetch<CatalogPayload>("/api/pay/membership/orders/latest", { timeoutMs: PAYMENT_TIMEOUT_MS });
        if (revision !== catalogRevision.current) return;
        if (latest.plans?.length) setPlans(latest.plans);
        if (latest.checkout) setCheckout(latest.checkout);
        let target = latest.order;
        if (requestedOrderId !== null) {
          if (!/^[1-9]\d*$/.test(requestedOrderId)) throw new Error("无效的会员订单号");
          const detail = await apiFetch<{order: OrderPayload}>(`/api/orders/${requestedOrderId}`, { timeoutMs: PAYMENT_TIMEOUT_MS });
          if (revision !== catalogRevision.current) return;
          if (String(detail.order?.id) !== requestedOrderId || detail.order.product_type !== "membership" || !latest.user || detail.order.user_id !== latest.user.id) {
            throw new Error("找不到这个账号的会员订单");
          }
          target = detail.order;
          if (!OPEN_ORDER_STATUSES.has(target.status)) setMessage(`订单 ${target.order_no}：${orderStatusText(target.status)}`);
        }
        const resumable = isOpenOrder(target) ? target : null;
        saveOpenOrderSnapshot(resumable);
        setOrder(resumable);
        if (resumable?.package_id && latest.plans?.some((plan) => plan.id === resumable.package_id)) {
          setSelectedPlanId(resumable.package_id);
          setInvalidRequestedPlan(false);
        }
        if (resumable?.status === "pending") {
          setMessage(`已恢复未完成订单 ${resumable.order_no}。如已付款，请直接提交付款信息，不要重复付款。`);
        }
        if (latest.user) rememberUser(latest.user);
      }
    } catch (error) {
      if (revision !== catalogRevision.current) return;
      if (!handleExpiredSession(error)) {
        setLoadFailed(true);
        const reason = stripEndPunctuation(error instanceof Error ? error.message : "读取会员套餐失败");
        const snapshot = token && requestedOrderId === null ? loadOpenOrderSnapshot() : null;
        setMessage(
          snapshot
            ? `${reason}。你有一笔未完成的${snapshot.plan_name}订单 ${snapshot.order_no}（¥${(snapshot.amount_cents / 100).toFixed(2)}）。如果已经付款，请不要重复付款，服务恢复后点击“重新加载”继续提交付款信息。`
            : `${reason}。请稍后点击“重新加载”。`,
        );
      }
    } finally {
      if (revision === catalogRevision.current) setLoading(false);
    }
  }

  function selectPlan(plan: MembershipPlan) {
    if (checkoutOrder) startAnother();
    setSelectedPlanId(plan.id);
    setInvalidRequestedPlan(false);
    setDraft((current) => ({ ...current, submitted_amount_yuan: (plan.amount_cents / 100).toFixed(2) }));
    if (!checkoutOrder) setMessage("");
  }

  function startAnother() {
    setOrder(null);
    setPaymentMessage("");
    setSubmitFailure(null);
    setMessage("原订单保留在首页账号菜单的「我的订单」。如已为原订单付款，请勿重复付款。");
  }


  async function createMembershipOrder() {
    if (!selectedPlan || creatingRef.current) return;
    // Read the token at interaction time so a click immediately after
    // hydration cannot observe the server-rendered empty session state.
    if (!getAuthToken()) {
      router.push(buildAuthRedirect(selectedPlan.id, "pricing", "membership"));
      return;
    }
    creatingRef.current = true;
    setCreating(true);
    setMessage("");
    setPaymentMessage("");
    setSubmitFailure(null);
    const planId = selectedPlan.id;
    try {
      const payload = await apiFetch<CatalogPayload>("/api/pay/membership/orders", {
        timeoutMs: PAYMENT_TIMEOUT_MS,
        method: "POST",
        body: JSON.stringify({ plan_id: planId, client_request_id: checkoutRequestId(planId) }),
      });
      if (payload.plans?.length) setPlans(payload.plans);
      if (payload.checkout) setCheckout(payload.checkout);
      const created = payload.order || null;
      if (!created?.id || !created.order_no) {
        throw new ApiError("订单未创建成功，请勿付款，稍后重试。", 502);
      }
      clearCheckoutRequestId(planId);
      setOrder(created);
      if (requestedOrderId !== null && String(created.id) !== requestedOrderId) {
        router.replace(`/billing?order_id=${created.id}`, { scroll: false });
      }
      if (payload.user) rememberUser(payload.user);
      setDraft((current) => ({ ...current, submitted_amount_yuan: ((created.amount_cents || selectedPlan.amount_cents) / 100).toFixed(2) }));
      setMessage(
        created.reused
          ? `已为你恢复未完成订单 ${created.order_no}，请勿重复付款。`
          : `订单 ${created.order_no} 已创建。请按订单金额付款，并在付款备注填写订单号，付款后提交付款信息。`,
      );
    } catch (error) {
      if (!handleExpiredSession(error)) {
        const reason = stripEndPunctuation(error instanceof Error ? error.message : "创建会员订单失败");
        // No order -> no QR code. Say so explicitly so nobody pays into the void.
        setMessage(`订单未创建成功，请不要付款。${reason}`);
      }
    } finally {
      creatingRef.current = false;
      setCreating(false);
    }
  }

  async function submitPayment() {
    if (!checkoutOrder || submittingRef.current) return;
    const target = checkoutOrder;
    // Validate locally first: point at the empty field instead of a server
    // round trip that only returns a generic message at the top of the page.
    const missing = !draft.payer_name.trim() ? "payer_name" : !draft.payer_paid_at ? "payer_paid_at" : "";
    if (missing) {
      setFieldError(missing);
      setSubmitFailure({ retryable: false, message: "" });
      setPaymentMessage(missing === "payer_name" ? "请填写付款人微信昵称或姓名，方便管理员核对到账。" : "请填写付款时间。");
      document.querySelector<HTMLInputElement>(`#billing-payment-form [name="${missing}"]`)?.focus();
      return;
    }
    setFieldError("");
    submittingRef.current = true;
    setSubmitting(true);
    setMessage("");
    setPaymentMessage("");
    setSubmitFailure(null);
    try {
      const payload = await apiFetch<CatalogPayload>(`/api/pay/membership/orders/${target.id}/submit`, {
        // The server saves first and then emails the admin (SMTP up to ~15s).
        timeoutMs: PAYMENT_SUBMIT_TIMEOUT_MS,
        method: "POST",
        body: JSON.stringify({
          payment_method: "wechat",
          payer_name: draft.payer_name.trim(),
          payer_paid_at: draft.payer_paid_at,
          // Always the order's own amount. The old page sent the amount of the
          // default/URL plan, so a restored monthly order was submitted as
          // ¥399 (or an annual one as ¥59) and the server rejected it.
          submitted_amount_cents: target.amount_cents,
          payer_note: draft.payer_note.trim() || target.order_no,
        }),
      });
      if (payload.order) setOrder(payload.order);
      if (payload.user) rememberUser(payload.user);
      const notification = payload.order?.admin_notification;
      const nextMessage = payload.order?.status === "paid"
        ? "该订单已由管理员确认开通。"
        : payload.order?.duplicate_submission
          ? "付款信息此前已提交成功，等待管理员人工核款开通，无需重复付款。"
          : notification && notification.sent === false && !notification.skipped
            ? `付款信息已保存（订单 ${target.order_no}），管理员提醒暂未发出，我们会在后台看到这笔订单，请勿重复付款。`
            : "付款信息已提交，等待管理员人工核款开通。";
      setMessage(nextMessage);
      setPaymentMessage(nextMessage);
    } catch (error) {
      if (handleExpiredSession(error)) return;
      const reason = stripEndPunctuation(error instanceof Error ? error.message : "提交付款信息失败");
      const retryable = isRetryableError(error);
      const nextMessage = retryable
        ? `付款信息暂未送达服务器（${reason}）。请不要重复付款：订单 ${target.order_no} 已保存，你填写的信息也已保存在本机，网络恢复后点击“重新提交付款信息”即可。`
        : `${reason}。请核对后重新提交；请不要重复付款，订单号 ${target.order_no}。`;
      setSubmitFailure({ retryable, message: nextMessage });
      setMessage(nextMessage);
      setPaymentMessage(nextMessage);
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  async function cancelOrder(target: OrderPayload | null) {
    if (!target || !OPEN_ORDER_STATUSES.has(target.status) || cancelling) return;
    if (!confirmCancellation(target)) return;
    setCancelling(true);
    try {
      await cancelMembershipOrder(target.id);
      if (checkoutOrder?.id === target.id) {
        saveOpenOrderSnapshot(null);
        draftOrderIdRef.current = null;
        setOrder(null);
        setPaymentMessage("");
        setSubmitFailure(null);
      }
      setMessage(`订单 ${target.order_no} 已取消。`);
    } catch (error) {
      if (!handleExpiredSession(error)) {
        setMessage(error instanceof Error ? error.message : "取消订单失败");
      }
    } finally {
      setCancelling(false);
    }
  }

  async function refreshOrder(orderId: number, silent = false) {
    if (!silent) setMessage("");
    try {
      const payload = await apiFetch<{ order?: OrderPayload | null; user?: UserProfile | null }>(`/api/orders/${orderId}`, { timeoutMs: PAYMENT_TIMEOUT_MS });
      // Never drop the checkout because of an empty/odd refresh response:
      // losing the order on screen is exactly what makes users pay twice.
      if (!payload.order?.id) return;
      const updated = payload.order;
      setOrder(current => current?.id === orderId && isOpenOrder(current) ? updated : current);
      if (payload.user) rememberUser(payload.user);
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
    setSubmitFailure(null);
    return true;
  }

  const submitLabel = submitting
    ? "正在提交"
    : submitFailure?.retryable
      ? "重新提交付款信息"
      : checkoutOrder?.status === "submitted"
        ? "更新付款信息"
        : "我已付款，通知管理员";

  return (
    <main className="billing-page yh-billing">
      <section className="billing-shell">
        <header className="billing-topbar">
          <Link href="/">
            <ArrowLeft />
            返回首页
          </Link>
          <div>
            <span>YINGHANG MEMBERSHIP</span>
            <h1>开通盈航会员</h1>
            <p>{token ? membershipSummary(account) : "游客可先查看价格与付款方式；创建订单时再登录。会员期内五项核心功能不限次数使用。"}</p>
          </div>
        </header>


        {message ? <div className="billing-message" role="status">{message}</div> : null}
        {loading ? <div className="billing-message">正在读取会员套餐...</div> : null}
        {loadFailed && !loading ? (
          <button className="billing-secondary billing-reload" type="button" onClick={() => void loadCatalog()}>
            <RefreshCw />
            重新加载
          </button>
        ) : null}

        <section className="billing-grid">
          <div className="billing-packages">
            <div className="billing-package-heading">
              <span><Crown />选择会员套餐</span>
              <small>{checkoutOrder ? "原订单保留，可另选套餐创建新订单" : "年度会员更划算，月度适合先体验"}</small>
            </div>
            {checkoutOrder ? (
              <div className="billing-inline-message billing-plan-locked">
                <span>想再买同一套餐，或改开{plans.find((plan) => plan.id !== checkoutOrder.package_id)?.plan_name || "其他套餐"}？无需取消旧订单。同一笔转账只提交一次。</span>
                <button className="billing-secondary" type="button" onClick={startAnother} disabled={cancelling || creating || submitting}>
                  再买一份
                </button>
              </div>
            ) : null}
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
                    disabled={cancelling || creating || submitting}
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
              <p>人工核款开通：先创建订单，系统生成订单号后才会显示收款码；付款时备注订单号，付款后提交付款信息等待审核。</p>
            </div>
          </div>

          <aside className="billing-checkout">
            <div className="billing-card-head">
              <QrCode />
              <span>
                <b>{checkoutOrder ? `${checkoutOrder.plan_name} · 订单 ${checkoutOrder.order_no}` : selectedPlan?.plan_name || "会员套餐"}</b>
                <small>{checkoutOrder ? orderStatusText(checkoutOrder.status) : token ? "先创建订单，再扫码付款" : "价格公开可见，登录后创建订单"}</small>
              </span>
            </div>

            {checkoutOrder ? (
              <>
                <ol className="billing-steps" aria-label="付款进度">
                  <li className="done">订单已创建</li>
                  <li className={checkoutOrder.status === "pending" ? "current" : "done"}>扫码付款</li>
                  <li className={checkoutOrder.status === "pending" ? "" : checkoutOrder.status === "rejected" ? "current" : "done"}>提交付款信息</li>
                  <li className={checkoutOrder.status === "submitted" ? "current" : ""}>管理员核款开通</li>
                </ol>
                {checkoutOrder.status !== "submitted" && <div className="billing-qr-row">
                  <QrBox title="微信" src={selectedPlan?.wechat_qr_url || ""} />
                </div>}
                <div className="billing-pay-hint" data-testid="billing-pay-hint">
                  <p>应付金额：¥{(checkoutOrder.amount_cents / 100).toFixed(2)}</p>
                  <p>{`付款备注请填写订单号：${checkoutOrder.order_no}`}</p>
                  <button
                    className="billing-secondary billing-copy-order"
                    type="button"
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(checkoutOrder.order_no);
                        setCopied(true);
                        window.setTimeout(() => setCopied(false), 2000);
                      } catch {
                        window.prompt("长按复制订单号", checkoutOrder.order_no);
                      }
                    }}
                  >
                    {copied ? "已复制订单号" : "复制订单号"}
                  </button>
                  <span className="sr-only" aria-live="polite">{copied ? "订单号已复制" : ""}</span>
                  <small>付款后务必提交下方付款信息；提交失败不要重复付款，订单会一直保留。</small>
                </div>
                {checkoutOrder.status !== "submitted" ? (
                  <button
                    className="billing-primary billing-jump-to-form"
                    type="button"
                    onClick={() => {
                      const form = document.getElementById("billing-payment-form");
                      form?.scrollIntoView({ behavior: "smooth", block: "start" });
                      form?.querySelector<HTMLInputElement>("input[data-autofocus]")?.focus({ preventScroll: true });
                    }}
                  >
                    <Send />
                    已付款？点这里提交付款信息
                  </button>
                ) : null}
                <div className="billing-order">
                  <span>订单号</span>
                  <b>{checkoutOrder.order_no}</b>
                  <span>状态</span>
                  <b>{orderStatusText(checkoutOrder.status)}</b>
                  <span>会员套餐</span>
                  <b>{checkoutOrder.plan_name}</b>
                </div>
                {checkoutOrder.status === "rejected" ? (
                  <div className="billing-inline-message" role="alert">
                    <b>付款核对未通过：{checkoutOrder.admin_note || "管理员未填写具体原因"}</b>
                    <span>请根据原因核对付款信息，更正后重新提交即可，无需重复付款；仍有疑问请通过下方支持渠道联系客服。</span>
                  </div>
                ) : null}
                <div className="billing-payment-form" id="billing-payment-form">
                  {checkoutOrder.status === "submitted" ? <div className="billing-inline-message">付款信息已提交，等待管理员人工确认到账。如信息填错可修改后更新。</div> : null}
                  <label>
                    <span>付款方式</span>
                    <input value="微信支付" readOnly aria-readonly="true" />
                  </label>
                  <label>
                    <span>付款人昵称或姓名</span>
                    <input
                      data-autofocus
                      name="payer_name"
                      autoComplete="off"
                      aria-invalid={fieldError === "payer_name" || undefined}
                      value={draft.payer_name}
                      onChange={(event) => {
                        setFieldError("");
                        setDraft((current) => ({ ...current, payer_name: event.target.value }));
                      }}
                    />
                  </label>
                  <label>
                    <span>付款时间</span>
                    <input
                      type="datetime-local"
                      name="payer_paid_at"
                      aria-invalid={fieldError === "payer_paid_at" || undefined}
                      value={draft.payer_paid_at}
                      onChange={(event) => {
                        setFieldError("");
                        setDraft((current) => ({ ...current, payer_paid_at: event.target.value }));
                      }}
                    />
                  </label>
                  <label>
                    <span>实付金额</span>
                    <input value={(checkoutOrder.amount_cents / 100).toFixed(2)} readOnly aria-readonly="true" />
                  </label>
                  <label>
                    <span>付款备注</span>
                    <input value={draft.payer_note} placeholder={checkoutOrder.order_no} onChange={(event) => setDraft((current) => ({ ...current, payer_note: event.target.value }))} />
                  </label>
                  <button className="billing-primary" type="button" onClick={submitPayment} disabled={submitting}>
                    {submitting ? <Loader2 className="spin-icon" /> : <Send />}
                    {submitLabel}
                  </button>
                  {paymentMessage ? (
                    <div className="billing-inline-message" role={submitFailure ? "alert" : "status"}>{paymentMessage}</div>
                  ) : null}
                </div>
                <button className="billing-secondary" type="button" onClick={() => refreshOrder(checkoutOrder.id)}>
                  <RefreshCw />
                  刷新订单状态
                </button>
                {OPEN_ORDER_STATUSES.has(checkoutOrder.status) ? (
                  <button className="billing-secondary" type="button" onClick={() => cancelOrder(checkoutOrder)} disabled={cancelling || submitting}>
                    <XCircle />
                    {cancelling ? "正在取消" : checkoutOrder.status === "submitted" ? "我没有付款，取消订单" : "取消此订单 / 更换套餐"}
                  </button>
                ) : null}
              </>
            ) : (
              <>
                {order?.status === "paid" ? (
                  <div className="billing-paid">
                    <CheckCircle2 />
                    {order.plan_name}已开通
                  </div>
                ) : null}
                <button className="billing-primary" type="button" onClick={createMembershipOrder} disabled={!sessionReady || !selectedPlan || invalidRequestedPlan || creating || loading || (requestedOrderId !== null && loadFailed)}>
                  {creating ? <Loader2 className="spin-icon" /> : <CreditCard />}
                  {creating ? "正在创建订单" : token ? `创建${selectedPlan?.plan_name || "会员"}订单` : "登录后创建订单"}
                </button>
              </>
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

function membershipSummary(user: UserProfile | null) {
  if (!user) return "会员期内五项核心功能不限次数使用。";
  const expires = String(user.membership_expires_at || "").slice(0, 10);
  if (user.membership_active) return `你的会员有效至 ${expires}，现在续费将从到期日顺延。`;
  if (expires) return `你的会员已于 ${expires} 到期，续费后从核款确认时起算。`;
  return "你还不是会员。会员期内五项核心功能不限次数使用。";
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
      {src ? <Image src={src} alt={`${title}收款二维码`} width={828} height={1124} sizes="(max-width: 920px) 100vw, 420px" unoptimized /> : <span>收款码暂未配置</span>}
      <code>{title}收款码</code>
    </div>
  );
}
