"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, CheckCircle2, CreditCard, Loader2, QrCode, RefreshCw, Send, ShieldCheck } from "lucide-react";
import { apiFetch, getAuthToken, storeUser, type UserProfile } from "@/lib/auth-client";

type MembershipPlan = {
  id: string;
  plan_name: string;
  amount_cents: number;
  duration_days: number;
  alipay_qr_url?: string;
  wechat_qr_url?: string;
};

type OrderPayload = {
  id: number;
  order_no: string;
  plan_name: string;
  amount_cents: number;
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

type PaymentDraft = {
  payment_method: "alipay" | "wechat";
  payer_name: string;
  payer_paid_at: string;
  submitted_amount_yuan: string;
  payer_note: string;
};

export default function BillingPage() {
  const router = useRouter();
  const [plans, setPlans] = useState<MembershipPlan[]>([]);
  const [order, setOrder] = useState<OrderPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [paymentMessage, setPaymentMessage] = useState("");
  const [draft, setDraft] = useState<PaymentDraft>({
    payment_method: "alipay",
    payer_name: "",
    payer_paid_at: "",
    submitted_amount_yuan: "59.00",
    payer_note: "",
  });

  const selectedPlan = useMemo(() => plans[0], [plans]);

  useEffect(() => {
    if (!getAuthToken()) {
      router.push("/auth?redirect=/billing");
      return;
    }
    void loadPlans();
  }, [router]);

  useEffect(() => {
    if (!order || order.status === "paid") return;
    const timer = window.setInterval(() => {
      void refreshOrder(order.id, true);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [order]);

  async function loadPlans() {
    setLoading(true);
    setMessage("");
    try {
      const payload = await apiFetch<{ plans: MembershipPlan[] }>("/api/pay/membership/plans");
      setPlans(payload.plans || []);
      const plan = payload.plans?.[0];
      if (plan) setDraft((current) => ({ ...current, submitted_amount_yuan: (plan.amount_cents / 100).toFixed(2) }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取会员套餐失败");
    } finally {
      setLoading(false);
    }
  }

  async function createMembershipOrder() {
    if (!selectedPlan || creating) return;
    setCreating(true);
    setMessage("");
    try {
      const payload = await apiFetch<{ order: OrderPayload; user?: UserProfile | null }>("/api/pay/membership/orders", {
        method: "POST",
        body: JSON.stringify({ plan_id: selectedPlan.id }),
      });
      setOrder(payload.order);
      if (payload.user) storeUser(payload.user);
      setMessage("订单已创建。扫码付款后，请点击“我已付款”提交信息，系统会邮件通知管理员。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "创建会员订单失败");
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
      const amount = Math.round(Number(draft.submitted_amount_yuan || "0") * 100);
      const payload = await apiFetch<{ order: OrderPayload; user?: UserProfile | null }>(`/api/pay/membership/orders/${order.id}/submit`, {
        method: "POST",
        body: JSON.stringify({
          payment_method: draft.payment_method,
          payer_name: draft.payer_name,
          payer_paid_at: draft.payer_paid_at,
          submitted_amount_cents: amount,
          payer_note: draft.payer_note || order.order_no,
        }),
      });
      setOrder(payload.order);
      if (payload.user) storeUser(payload.user);
      const notice = payload.order.admin_notification;
      const nextMessage = notice?.sent === false ? `付款信息已提交，但邮件提醒未发送：${notice.error || "未知原因"}` : "付款信息已提交，已邮件通知管理员核对到账。";
      setMessage(nextMessage);
      setPaymentMessage(nextMessage);
    } catch (error) {
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
      if (!silent) setMessage(error instanceof Error ? error.message : "刷新订单失败");
    }
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
            <span>MONTHLY MEMBERSHIP</span>
            <h1>开通 59 元/月会员</h1>
            <p>扫码付款后点击“我已付款”，系统会邮件通知管理员；管理员确认到账后开通。</p>
          </div>
        </header>

        {message && <div className="billing-message">{message}</div>}
        {loading && <div className="billing-message">正在读取会员套餐...</div>}

        <section className="billing-grid">
          <div className="billing-packages">
            {selectedPlan && (
              <button className="active" type="button">
                <CreditCard />
                <span>
                  <b>{selectedPlan.plan_name}</b>
                  <small>{selectedPlan.duration_days} 天会员权益</small>
                </span>
                <strong>¥{(selectedPlan.amount_cents / 100).toFixed(2)}</strong>
              </button>
            )}
            <div className="billing-empty-qr">
              <ShieldCheck />
              <p>付款时请备注订单号或账号，未备注会延迟开通。管理员只在确认到账后开通会员。</p>
            </div>
          </div>

          <aside className="billing-checkout">
            <div className="billing-card-head">
              <QrCode />
              <span>
                <b>{order ? `订单 ${order.order_no}` : selectedPlan?.plan_name || "月度会员"}</b>
                <small>{order ? orderStatusText(order.status) : "先创建订单，再扫码付款"}</small>
              </span>
            </div>

            {order ? (
              <>
                <div className="billing-qr-row">
                  <QrBox title="支付宝" src={selectedPlan?.alipay_qr_url || "/pay/alipay-qr.jpg"} />
                  <QrBox title="微信" src={selectedPlan?.wechat_qr_url || "/pay/wechat-qr.jpg"} />
                </div>
                <div className="billing-order">
                  <span>订单号</span>
                  <b>{order.order_no}</b>
                  <span>状态</span>
                  <b>{orderStatusText(order.status)}</b>
                </div>
                {order.status !== "paid" && (
                  <div className="billing-payment-form">
                    {order.status === "submitted" ? <div className="billing-inline-message">付款信息已提交，正在等待管理员确认到账。</div> : null}
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
                      <input value={draft.submitted_amount_yuan} onChange={(event) => setDraft((current) => ({ ...current, submitted_amount_yuan: event.target.value }))} />
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
                )}
                <button className="billing-secondary" type="button" onClick={() => refreshOrder(order.id)}>
                  <RefreshCw />
                  刷新订单状态
                </button>
                {order.status === "paid" && (
                  <div className="billing-paid">
                    <CheckCircle2 />
                    会员已开通
                  </div>
                )}
              </>
            ) : (
              <button className="billing-primary" type="button" onClick={createMembershipOrder} disabled={!selectedPlan || creating || loading}>
                {creating ? <Loader2 className="spin-icon" /> : <CreditCard />}
                {creating ? "正在创建订单" : "创建会员订单"}
              </button>
            )}
          </aside>
        </section>
      </section>
    </main>
  );
}

function QrBox({ title, src }: { title: string; src: string }) {
  return (
    <div className="billing-qr">
      <Image src={src} alt={`${title}收款二维码`} width={180} height={180} />
      <code>{title}收款码</code>
    </div>
  );
}

function orderStatusText(status: string) {
  if (status === "pending") return "待付款";
  if (status === "submitted") return "待管理员确认";
  if (status === "paid") return "已开通";
  if (status === "rejected") return "异常/已驳回";
  return status || "--";
}
