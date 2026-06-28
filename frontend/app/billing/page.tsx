"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, CheckCircle2, CreditCard, ExternalLink, Loader2, RefreshCw, ShieldCheck } from "lucide-react";
import { apiFetch, getAuthToken, storeUser, type UserProfile } from "@/lib/auth-client";

type CreditPackage = {
  id: string;
  plan_name: string;
  credits: number;
  amount_cents: number;
};

type OrderPayload = {
  id: number;
  order_no: string;
  plan_name: string;
  credits: number;
  amount_cents: number;
  status: "pending" | "paid" | string;
  paid_at?: string | null;
  payment_provider?: string | null;
};

type CheckoutPayload = {
  order: OrderPayload;
  checkout_url: string;
  provider: "jinshuju" | string;
};

type OrderStatusPayload = {
  order: OrderPayload;
  user?: UserProfile | null;
};

export default function BillingPage() {
  const router = useRouter();
  const [packages, setPackages] = useState<CreditPackage[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [order, setOrder] = useState<OrderPayload | null>(null);
  const [checkoutUrl, setCheckoutUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState("");

  const selectedPackage = useMemo(
    () => packages.find((item) => item.id === selectedId) || packages[0],
    [packages, selectedId],
  );

  useEffect(() => {
    if (!getAuthToken()) {
      router.push("/auth?redirect=/billing");
      return;
    }
    void loadPackages();
  }, [router]);

  useEffect(() => {
    if (!order || order.status === "paid") return;
    const timer = window.setInterval(() => {
      void refreshOrder(order.id, true);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [order]);

  async function loadPackages() {
    setLoading(true);
    setMessage("");
    try {
      const payload = await apiFetch<{ packages: CreditPackage[] }>("/api/pay/packages");
      setPackages(payload.packages || []);
      setSelectedId(payload.packages?.[0]?.id || "");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取次数包失败");
    } finally {
      setLoading(false);
    }
  }

  async function createPayment() {
    if (!selectedPackage || creating) return;
    setCreating(true);
    setMessage("");
    setCheckoutUrl("");
    const payWindow = window.open("about:blank", "_blank");
    try {
      const payload = await apiFetch<CheckoutPayload>("/api/pay/jinshuju/checkout", {
        method: "POST",
        body: JSON.stringify({ package_id: selectedPackage.id }),
      });
      setOrder(payload.order);
      setCheckoutUrl(payload.checkout_url);
      if (payWindow) {
        payWindow.location.href = payload.checkout_url;
      } else {
        window.location.href = payload.checkout_url;
      }
      setMessage("已打开金数据收款表单。支付完成后，次数会自动到账，本页会自动刷新订单状态。");
    } catch (error) {
      if (payWindow) payWindow.close();
      setMessage(error instanceof Error ? error.message : "创建金数据收款订单失败");
    } finally {
      setCreating(false);
    }
  }

  async function refreshOrder(orderId: number, silent = false) {
    if (!silent) setMessage("");
    try {
      const payload = await apiFetch<OrderStatusPayload>(`/api/orders/${orderId}`);
      setOrder(payload.order);
      if (payload.user) storeUser(payload.user);
      if (payload.order.status === "paid") {
        setMessage(`支付成功，${payload.order.credits} 次使用机会已到账。`);
      } else if (!silent) {
        setMessage("订单仍在等待支付，请确认金数据表单是否已经完成付款。");
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
            <span>JINSHUJU CHECKOUT</span>
            <h1>购买使用次数</h1>
            <p>选择次数包后跳转金数据收款表单；支付成功后次数自动到账，并通过邮件提醒。</p>
          </div>
        </header>

        {message && <div className="billing-message">{message}</div>}
        {loading && <div className="billing-message">正在读取次数包...</div>}

        <section className="billing-grid">
          <div className="billing-packages">
            {packages.map((item) => (
              <button className={selectedPackage?.id === item.id ? "active" : ""} type="button" key={item.id} onClick={() => setSelectedId(item.id)}>
                <CreditCard />
                <span>
                  <b>{item.plan_name}</b>
                  <small>{item.credits} 次使用机会</small>
                </span>
                <strong>¥{(item.amount_cents / 100).toFixed(2)}</strong>
              </button>
            ))}
          </div>

          <aside className="billing-checkout">
            <div className="billing-card-head">
              <ShieldCheck />
              <span>
                <b>{selectedPackage?.plan_name || "选择次数包"}</b>
                <small>金数据收款表单</small>
              </span>
            </div>
            <div className="billing-empty-qr">
              <ExternalLink />
              <p>点击下方按钮后，会打开金数据收款表单。表单会自动带上订单号和你的账号邮箱。</p>
            </div>
            {order && (
              <div className="billing-order">
                <span>订单号</span>
                <b>{order.order_no}</b>
                <span>状态</span>
                <b>{order.status === "paid" ? "已支付" : "待支付"}</b>
              </div>
            )}
            <button className="billing-primary" type="button" onClick={createPayment} disabled={!selectedPackage || creating || loading}>
              {creating ? <Loader2 className="spin-icon" /> : <ExternalLink />}
              {creating ? "正在创建订单" : "打开金数据收款表单"}
            </button>
            {checkoutUrl && order?.status !== "paid" && (
              <a className="billing-secondary" href={checkoutUrl} target="_blank" rel="noreferrer">
                <ExternalLink />
                重新打开收款表单
              </a>
            )}
            {order && order.status !== "paid" && (
              <button className="billing-secondary" type="button" onClick={() => refreshOrder(order.id)}>
                <RefreshCw />
                刷新支付状态
              </button>
            )}
            {order?.status === "paid" && (
              <div className="billing-paid">
                <CheckCircle2 />
                次数已到账
              </div>
            )}
          </aside>
        </section>
      </section>
    </main>
  );
}
