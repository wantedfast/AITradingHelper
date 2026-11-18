"use client";

import { Search, ShieldCheck, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/auth-client";
import { AdminConfirmDialog, type AdminConfirmIntent } from "@/components/admin/admin-confirm-dialog";

export type ManualGrantPrefill = {
  userId: number;
  userLabel: string;
  orderId?: number;
  orderNo?: string;
  planId?: string;
  payerName?: string;
  payerPaidAt?: string;
};

type PlanOption = { id: string; plan_name: string; amount_cents: number; duration_days: number };
type UserCandidate = { id: number; username?: string; email?: string; phone: string; membership_status?: string; membership_expires_at?: string; membership_active?: boolean };

type GrantResult = {
  order: { order_no: string; status: string };
  user: { membership_expires_at?: string };
  idempotent: boolean;
};

function newGrantRequestId() {
  const random = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  return `admin-grant-${random}`;
}

function candidateLabel(user: UserCandidate) {
  return user.username || user.email || user.phone || `用户 #${user.id}`;
}

function membershipLabel(user: UserCandidate) {
  if (user.membership_active) return `会员有效至 ${String(user.membership_expires_at || "").slice(0, 10)}`;
  if (user.membership_status === "expired") return `会员已过期（${String(user.membership_expires_at || "").slice(0, 10)}）`;
  return "非会员";
}

/**
 * Formal back-office entry for a payment the admin has verified in the WeChat
 * account but that has no submitted order. The request id is generated once
 * per form and reused across retries so a timeout can never open twice.
 */
export function AdminManualGrantPanel({
  prefill,
  onClose,
  onDone,
}: {
  prefill: ManualGrantPrefill | null;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [plans, setPlans] = useState<PlanOption[]>([]);
  const [userQuery, setUserQuery] = useState("");
  const [candidates, setCandidates] = useState<UserCandidate[]>([]);
  const [selectedUser, setSelectedUser] = useState<{ id: number; label: string } | null>(
    prefill ? { id: prefill.userId, label: prefill.userLabel } : null,
  );
  const [planId, setPlanId] = useState(prefill?.planId || "monthly_membership");
  const [paymentMethod, setPaymentMethod] = useState("wechat");
  const [payerName, setPayerName] = useState(prefill?.payerName || "");
  const [payerPaidAt, setPayerPaidAt] = useState(prefill?.payerPaidAt || "");
  const [reason, setReason] = useState("");
  const [requestId, setRequestId] = useState(newGrantRequestId);
  const [error, setError] = useState("");
  const [searching, setSearching] = useState(false);
  const [intent, setIntent] = useState<AdminConfirmIntent | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiFetch<{ plans: PlanOption[] }>("/api/public/membership/plans")
      .then((payload) => {
        if (!cancelled) setPlans(payload.plans || []);
      })
      .catch(() => {
        if (!cancelled) setError("读取会员套餐失败，请刷新后重试。");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const plan = useMemo(() => plans.find((item) => item.id === planId), [plans, planId]);
  const orderId = prefill?.orderId;

  async function searchUsers() {
    const query = userQuery.trim();
    if (!query) return;
    setSearching(true);
    setError("");
    try {
      const payload = await apiFetch<{ items: UserCandidate[] }>(`/api/admin/users?q=${encodeURIComponent(query)}&page_size=5`);
      setCandidates(payload.items || []);
      if (!payload.items?.length) setError("没有找到匹配的普通用户。");
    } catch (searchError) {
      setError(searchError instanceof Error ? searchError.message : "查找用户失败");
    } finally {
      setSearching(false);
    }
  }

  function validationError() {
    if (!selectedUser) return "请选择用户";
    if (!plan) return "请选择套餐";
    if (!payerName.trim()) return "请填写付款人（微信昵称）";
    if (!payerPaidAt) return "请填写付款时间";
    if (reason.trim().length < 2) return "请填写补录原因";
    return "";
  }

  function requestGrant() {
    const invalid = validationError();
    if (invalid) {
      setError(invalid);
      return;
    }
    if (!selectedUser || !plan) return;
    setError("");
    const body = {
      user_id: selectedUser.id,
      order_id: orderId ?? null,
      plan_id: plan.id,
      payment_method: paymentMethod,
      amount_cents: plan.amount_cents,
      payer_name: payerName.trim(),
      payer_paid_at: payerPaidAt,
      reason: reason.trim(),
      request_id: requestId,
    };
    setIntent({
      actionLabel: "确认人工补录并开通会员？",
      confirmLabel: "确认补录开通",
      busyLabel: "正在开通...",
      description: "请确认已在微信收款记录中核实到账。系统会创建/关联会员订单并写入一条会员流水，重复提交不会重复开通。",
      details: [
        `用户：${selectedUser.label}（ID ${selectedUser.id}）`,
        orderId ? `关联订单：${prefill?.orderNo || orderId}` : "新建补录订单",
        `套餐：${plan.plan_name}（${plan.duration_days} 天）`,
        `金额：¥${(plan.amount_cents / 100).toFixed(2)} · ${paymentMethod === "wechat" ? "微信" : "支付宝"}`,
        `付款人：${body.payer_name} · ${body.payer_paid_at}`,
        `原因：${body.reason}`,
      ],
      danger: true,
      onConfirm: async () => {
        setSubmitting(true);
        try {
          const result = await apiFetch<GrantResult>("/api/admin/memberships/manual-grant", {
            method: "POST",
            body: JSON.stringify(body),
          });
          setIntent(null);
          setRequestId(newGrantRequestId());
          onDone(
            `${result.idempotent ? "该补录已处理过，未重复开通。" : "人工补录完成。"}订单 ${result.order.order_no}，会员有效期至 ${String(result.user.membership_expires_at || "").slice(0, 16).replace("T", " ")}。`,
          );
        } catch (grantError) {
          // Keep the same request id: a retry after a timeout must be idempotent.
          setIntent(null);
          setError(grantError instanceof Error ? grantError.message : "人工补录失败");
        } finally {
          setSubmitting(false);
        }
      },
    });
  }

  return (
    <section className="admin-panel admin-manual-grant" aria-label="人工补录会员">
      <div className="admin-panel-head">
        <ShieldCheck aria-hidden="true" />
        <h2>人工补录会员{orderId ? ` · 关联订单 ${prefill?.orderNo || orderId}` : ""}</h2>
        <button type="button" className="admin-secondary-button" onClick={onClose} disabled={submitting} aria-label="关闭人工补录">
          <X aria-hidden="true" />
        </button>
      </div>
      <p className="admin-manual-grant-hint">仅在核实微信到账、但用户未能提交付款信息时使用。不会接受口头声称已付款。</p>
      {error ? <div className="admin-alert" role="alert">{error}</div> : null}
      <div className="admin-manual-grant-grid">
        {prefill ? (
          <label>
            <span>用户</span>
            <input value={`${prefill.userLabel}（ID ${prefill.userId}）`} readOnly aria-readonly="true" />
          </label>
        ) : (
          <div className="admin-manual-grant-user">
            <label>
              <span>查找用户（用户名 / 手机号 / 邮箱 / ID）</span>
              <input
                value={userQuery}
                onChange={(event) => setUserQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    void searchUsers();
                  }
                }}
              />
            </label>
            <button type="button" onClick={searchUsers} disabled={searching}>
              <Search aria-hidden="true" />
              {searching ? "查找中" : "查找"}
            </button>
            {candidates.length ? (
              <div className="admin-manual-grant-candidates" role="radiogroup" aria-label="选择用户">
                {candidates.map((user) => (
                  <button
                    key={user.id}
                    type="button"
                    role="radio"
                    aria-checked={selectedUser?.id === user.id}
                    className={selectedUser?.id === user.id ? "active" : ""}
                    onClick={() => setSelectedUser({ id: user.id, label: candidateLabel(user) })}
                  >
                    <b>{candidateLabel(user)}</b>
                    <small>ID {user.id} · {user.phone} · {membershipLabel(user)}</small>
                  </button>
                ))}
              </div>
            ) : null}
            {selectedUser ? <small>已选择：{selectedUser.label}（ID {selectedUser.id}）</small> : null}
          </div>
        )}
        <label>
          <span>套餐</span>
          <select value={planId} onChange={(event) => setPlanId(event.target.value)} disabled={Boolean(prefill?.planId)}>
            {plans.map((item) => (
              <option key={item.id} value={item.id}>{item.plan_name} · ¥{(item.amount_cents / 100).toFixed(2)} · {item.duration_days} 天</option>
            ))}
          </select>
        </label>
        <label>
          <span>付款方式</span>
          <select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value)}>
            <option value="wechat">微信</option>
            <option value="alipay">支付宝（历史）</option>
          </select>
        </label>
        <label>
          <span>金额</span>
          <input value={plan ? `¥${(plan.amount_cents / 100).toFixed(2)}` : ""} readOnly aria-readonly="true" />
        </label>
        <label>
          <span>付款人（微信昵称）</span>
          <input value={payerName} onChange={(event) => setPayerName(event.target.value)} />
        </label>
        <label>
          <span>付款时间</span>
          <input type="datetime-local" value={payerPaidAt} onChange={(event) => setPayerPaidAt(event.target.value)} />
        </label>
        <label className="admin-manual-grant-reason">
          <span>补录原因（必填）</span>
          <textarea rows={3} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="例如：用户付款时服务器不可用，已核对微信到账记录" />
        </label>
      </div>
      <div className="admin-order-actions">
        <button type="button" onClick={requestGrant} disabled={submitting}>
          <ShieldCheck aria-hidden="true" />
          核实到账，补录并开通
        </button>
      </div>
      <AdminConfirmDialog intent={intent} submitting={submitting} onClose={() => !submitting && setIntent(null)} />
    </section>
  );
}
