import { apiFetch } from "@/lib/auth-client";

export type OrderPayload = {
  id: number;
  order_no: string;
  plan_name: string;
  amount_cents: number;
  package_id?: string;
  product_type?: string;
  user_id?: number;
  duration_days?: number;
  status: "pending" | "submitted" | "paid" | "rejected" | "cancelled" | string;
  payment_method?: string;
  payer_name?: string;
  payer_note?: string;
  payer_paid_at?: string;
  submitted_amount_cents?: number | null;
  submitted_at?: string;
  admin_note?: string;
  paid_at?: string | null;
  created_at?: string;
  reused?: boolean;
  duplicate_submission?: boolean;
  admin_notification?: { sent?: boolean; error?: string; skipped?: boolean; duplicate?: boolean };
};

export const OPEN_ORDER_STATUSES = new Set(["pending", "submitted", "rejected"]);
export const DRAFT_KEY_PREFIX = "membership_payment_draft:";
export function safeStorage(kind: "local" | "session"): Storage | null {
  try {
    return kind === "local" ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
}

// Last open order, kept locally so that if the API is unreachable the page can
// still tell a user who already paid which order to resume - and not to pay
// again - instead of showing an empty checkout.
const OPEN_ORDER_KEY = "membership_open_order";
type OpenOrderSnapshot = { id: number; order_no: string; plan_name: string; amount_cents: number; status: string };

export function saveOpenOrderSnapshot(order: OrderPayload | null) {
  const storage = safeStorage("local");
  if (!storage) return;
  try {
    if (order && OPEN_ORDER_STATUSES.has(order.status)) {
      const snapshot: OpenOrderSnapshot = { id: order.id, order_no: order.order_no, plan_name: order.plan_name, amount_cents: order.amount_cents, status: order.status };
      storage.setItem(OPEN_ORDER_KEY, JSON.stringify(snapshot));
    } else {
      storage.removeItem(OPEN_ORDER_KEY);
    }
  } catch {
    // ignore storage failures
  }
}

export function loadOpenOrderSnapshot(): OpenOrderSnapshot | null {
  try {
    const raw = safeStorage("local")?.getItem(OPEN_ORDER_KEY);
    return raw ? (JSON.parse(raw) as OpenOrderSnapshot) : null;
  } catch {
    return null;
  }
}

export function clearDraft(orderId: number) {
  try { safeStorage("local")?.removeItem(`${DRAFT_KEY_PREFIX}${orderId}`); }
  catch { /* Local storage may be blocked; the server is authoritative. */ }
}

export function orderStatusText(status: string) {
  if (status === "pending") return "待付款（尚未提交付款信息）";
  if (status === "submitted") return "付款信息已提交，待管理员确认";
  if (status === "paid") return "已开通";
  if (status === "rejected") return "核款未通过，请更正后重新提交";
  if (status === "cancelled") return "已取消";
  return status;
}

export function confirmCancellation(order: OrderPayload) {
  return window.confirm(`确认没有付款并取消订单 ${order.order_no}？取消不是退款；如果已经转账，请保留订单等待核款。`);
}

export async function cancelMembershipOrder(id: number) {
  await apiFetch(`/api/pay/membership/orders/${id}/cancel`, { method: "POST", timeoutMs: 20_000 });
  clearDraft(id);
  if (loadOpenOrderSnapshot()?.id === id) saveOpenOrderSnapshot(null);
}
