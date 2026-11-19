"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, getAuthToken } from "@/lib/auth-client";
import { OPEN_ORDER_STATUSES, type OrderPayload, orderStatusText, cancelMembershipOrder, confirmCancellation } from "@/lib/membership-orders";
import "../../yh-tokens.css";
import "../../billing-theme.css";

export default function AccountOrdersPage() {
  const [token, setToken] = useState<string | null>(null);
  useEffect(() => {
    const sync = () => setToken(getAuthToken());
    sync();
    window.addEventListener("ai-trade-auth", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("ai-trade-auth", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return <main className="billing-page yh-billing"><div className="billing-shell">
    <header className="billing-topbar"><Link href="/">返回首页</Link><div>
      <span>我的账户</span><h1>我的订单</h1><p>查看会员订单和核款进度。</p>
    </div></header>
    {token === null ? <p role="status">正在读取账号…</p> : token
      ? <MembershipHistory key={token} />
      : <Link className="billing-secondary" href="/auth?mode=login&redirect=%2Faccount%2Forders">登录查看我的订单</Link>}
  </div></main>;
}

function MembershipHistory() {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  async function onCancel(order: OrderPayload) {
    if (busy || !confirmCancellation(order)) return;
    setBusy(true);
    try {
      await cancelMembershipOrder(order.id);
      setNotice(`订单 ${order.order_no} 已取消。`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "取消订单失败");
    } finally { setRetry(v => v + 1); setBusy(false); }
  }
  const [cursors, setCursors] = useState([0]);
  const [result, setResult] = useState<{ orders: OrderPayload[]; next_before: number | null } | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const before = cursors[cursors.length - 1];
  useEffect(() => {
    let active = true;
    setResult(null);
    setError("");
    apiFetch<{ orders: OrderPayload[]; next_before: number | null }>(`/api/pay/membership/orders?before=${before}`, {timeoutMs: 20_000})
      .then(data => { if (active) setResult(data); })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : "读取订单失败"); });
    return () => { active = false; };
  }, [before, retry]);
  return <section className="billing-packages billing-history" aria-label="我的会员订单">
    <h2>会员订单</h2>
    {notice && <p role="status">{notice}</p>}
    {error ? <p role="alert">{error} <button className="billing-secondary" onClick={() => setRetry(v => v+1)}>重试</button></p>
      : !result ? <p role="status">正在读取订单…</p>
      : !result.orders.length ? <p>还没有会员订单。</p> : result.orders.map(item =>
        <article className="billing-inline-message" key={item.id}>
          <strong>{item.plan_name} · ¥{(item.amount_cents / 100).toFixed(2)} · {orderStatusText(item.status)}</strong>
          <span>{item.order_no} · {item.created_at?.slice(0, 16).replace("T", " ")}</span>
          {OPEN_ORDER_STATUSES.has(item.status) && <>
            <Link className="billing-secondary" href={`/billing?order_id=${item.id}`}>查看并处理</Link>
            <button className="billing-secondary" disabled={busy} onClick={() => onCancel(item)}>{item.status === "submitted" ? "我没有付款，取消订单" : "取消这笔订单"}</button>
          </>}
        </article>)}
    {cursors.length > 1 && <button className="billing-secondary" disabled={busy} onClick={() => setCursors(v => v.slice(0,-1))}>上一页</button>}
    {result?.next_before && <button className="billing-secondary" disabled={busy} onClick={() => setCursors([...cursors, result.next_before!])}>下一页</button>}
  </section>;
}
