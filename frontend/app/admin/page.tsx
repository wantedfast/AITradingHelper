"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { BarChart3, CheckCircle2, CreditCard, Gift, LogOut, Megaphone, MessageSquare, RefreshCw, Users } from "lucide-react";
import { apiFetch, clearAuth, getStoredUser, refreshCurrentUser, type UserProfile } from "@/lib/auth-client";
import { useModalAccessibility } from "@/lib/modal-accessibility";

type DashboardPayload = {
  totals: {
    users: number;
    credits: number;
    feedback_pending: number;
    orders_paid: number;
  };
  usage_by_day: Array<{ day: string; feature: string; count: number; credits: number }>;
  new_users_by_day: Array<{ day: string; count: number }>;
  feedback: Array<{
    id: number;
    phone: string;
    category: string;
    content: string;
    contact: string;
    status: string;
    reward_credits: number;
    created_at: string;
  }>;
  orders: Array<{
    id: number;
    phone: string;
    username?: string;
    email?: string;
    order_no: string;
    plan_name: string;
    credits: number;
    amount_cents: number;
    status: string;
    product_type?: string;
    payment_method?: string;
    payer_name?: string;
    payer_note?: string;
    payer_paid_at?: string;
    submitted_amount_cents?: number | null;
    admin_note?: string;
    created_at: string;
  }>;
  top_users: Array<{ id: number; phone: string; username?: string; email?: string; role: string; used_count: number; credits: number; created_at: string }>;
  credit_grant_campaigns: CreditGrantCampaign[];
  update_notices: UpdateNotice[];
};

type CreditGrantCampaign = {
  id: number;
  request_id: string;
  credits: number;
  reason: string;
  status: "completed";
  eligible_count: number;
  granted_count: number;
  created_at: string;
  completed_at: string;
};

type GrantDraft = {
  credits: string;
  reason: string;
};

type UpdateNotice = {
  id: number;
  title: string;
  version: string;
  items: string[];
  status: "draft" | "published";
  created_at: string;
  updated_at: string;
  published_at?: string | null;
  email_campaign?: EmailCampaign | null;
};

type EmailCampaign = {
  id: number;
  status: "pending" | "sending" | "completed" | "partial_failed" | "failed";
  total: number;
  pending: number;
  sending: number;
  sent: number;
  failed: number;
  skipped: number;
};

type PublishIntent = { source: "form"; noticeId: number | null } | { source: "list"; noticeId: number };

type NoticeDraft = {
  title: string;
  version: string;
  itemsText: string;
};

const emptyNoticeDraft: NoticeDraft = {
  title: "",
  version: todayDateInputValue(),
  itemsText: "",
};

export default function AdminPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserProfile | null>(() => getStoredUser());
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [grantDrafts, setGrantDrafts] = useState<Record<number, GrantDraft>>({});
  const [bulkGrantDraft, setBulkGrantDraft] = useState<GrantDraft>({ credits: "10", reason: "" });
  const [bulkGrantIntent, setBulkGrantIntent] = useState(false);
  const [bulkGrantRequestId, setBulkGrantRequestId] = useState("");
  const [bulkGrantSubmitting, setBulkGrantSubmitting] = useState(false);
  const [noticeDraft, setNoticeDraft] = useState<NoticeDraft>(emptyNoticeDraft);
  const [editingNoticeId, setEditingNoticeId] = useState<number | null>(null);
  const [publishIntent, setPublishIntent] = useState<PublishIntent | null>(null);
  const [publishing, setPublishing] = useState(false);
  const activeDialogRef = useRef<HTMLElement>(null);

  useModalAccessibility(
    Boolean(publishIntent) || bulkGrantIntent,
    () => {
      if (!publishing) setPublishIntent(null);
      if (!bulkGrantSubmitting) setBulkGrantIntent(false);
    },
    activeDialogRef,
    !publishing && !bulkGrantSubmitting,
  );

  useEffect(() => {
    refreshCurrentUser()
      .then((nextUser) => {
        setUser(nextUser);
        if (nextUser?.role === "admin") return loadDashboard();
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  async function loadDashboard() {
    setLoading(true);
    setMessage("");
    try {
      const payload = await apiFetch<DashboardPayload>("/api/admin/dashboard?days=14");
      setData(payload);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取统计失败");
    } finally {
      setLoading(false);
    }
  }

  async function acceptFeedback(id: number) {
    await apiFetch(`/api/admin/feedback/${id}`, {
      method: "POST",
      body: JSON.stringify({ status: "accepted", admin_note: "反馈已采纳，奖励 10 次免费机会" }),
    });
    await loadDashboard();
  }

  async function markPaid(id: number) {
    await apiFetch(`/api/admin/orders/${id}/paid`, { method: "POST" });
    await loadDashboard();
  }

  async function confirmMembership(id: number) {
    await apiFetch(`/api/admin/orders/${id}/confirm-membership`, {
      method: "POST",
      body: JSON.stringify({ admin_note: "已人工核对到账，开通会员" }),
    });
    await loadDashboard();
  }

  async function rejectMembership(id: number) {
    const reason = window.prompt("请输入异常或驳回原因");
    if (!reason) return;
    await apiFetch(`/api/admin/orders/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ admin_note: reason }),
    });
    await loadDashboard();
  }

  function updateGrantDraft(userId: number, patch: Partial<GrantDraft>) {
    setGrantDrafts((current) => ({
      ...current,
      [userId]: { ...(current[userId] || { credits: "", reason: "" }), ...patch },
    }));
  }

  async function grantCredits(userId: number) {
    const draft = grantDrafts[userId] || { credits: "", reason: "" };
    setMessage("");
    try {
      const result = await apiFetch<{ email_notification?: { sent?: boolean; error?: string; skipped?: boolean } }>(`/api/admin/users/${userId}/credits`, {
        method: "POST",
        body: JSON.stringify({ credits: Number(draft.credits), reason: draft.reason }),
      });
      const notice = result.email_notification;
      setGrantDrafts((current) => ({ ...current, [userId]: { credits: "", reason: "" } }));
      await loadDashboard();
      setMessage(notice?.sent ? "次数已增加，并已发送邮件提醒。" : `次数已增加，但邮件提醒未发送：${notice?.error || "未知原因"}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "增加次数失败");
    }
  }

  function requestBulkGrantConfirmation() {
    const credits = Number(bulkGrantDraft.credits);
    if (!Number.isInteger(credits) || credits <= 0) {
      setMessage("增加次数必须是正整数");
      return;
    }
    if (bulkGrantDraft.reason.trim().length < 2) {
      setMessage("请填写增加次数的原因");
      return;
    }
    setMessage("");
    setBulkGrantRequestId(createCreditGrantRequestId());
    setBulkGrantIntent(true);
  }

  async function confirmBulkGrant() {
    if (!bulkGrantIntent || bulkGrantSubmitting || !bulkGrantRequestId) return;
    setBulkGrantSubmitting(true);
    setMessage("");
    try {
      const result = await apiFetch<{ campaign: CreditGrantCampaign; idempotent: boolean }>("/api/admin/credits/grant-all", {
        method: "POST",
        body: JSON.stringify({
          credits: Number(bulkGrantDraft.credits),
          reason: bulkGrantDraft.reason.trim(),
          request_id: bulkGrantRequestId,
        }),
      });
      setBulkGrantIntent(false);
      setBulkGrantRequestId("");
      setBulkGrantDraft({ credits: "10", reason: "" });
      await loadDashboard();
      setMessage(`批量发放完成：${result.campaign.granted_count} 位现有用户各增加 ${result.campaign.credits} 次。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "批量增加次数失败");
    } finally {
      setBulkGrantSubmitting(false);
    }
  }

  async function saveUpdateNotice() {
    setMessage("");
    try {
      const body = JSON.stringify({
        title: noticeDraft.title,
        version: noticeDraft.version,
        items_text: noticeDraft.itemsText,
        status: "draft",
      });
      if (editingNoticeId) {
        await apiFetch(`/api/admin/update-notices/${editingNoticeId}`, { method: "POST", body });
      } else {
        await apiFetch("/api/admin/update-notices", { method: "POST", body });
      }
      setNoticeDraft(emptyNoticeDraft);
      setEditingNoticeId(null);
      await loadDashboard();
      setMessage("更新公告已保存");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存更新公告失败");
    }
  }

  async function confirmPublish(sendEmail: boolean) {
    if (!publishIntent || publishing) return;
    setPublishing(true);
    setMessage("");
    try {
      const requestId = createPublishRequestId();
      let result: { email_campaign?: EmailCampaign | null } = {};
      if (publishIntent.source === "form") {
        const body = JSON.stringify({
          title: noticeDraft.title,
          version: noticeDraft.version,
          items_text: noticeDraft.itemsText,
          status: publishIntent.noticeId ? "draft" : "published",
          send_email: sendEmail,
          request_id: requestId,
        });
        if (publishIntent.noticeId) {
          await apiFetch(`/api/admin/update-notices/${publishIntent.noticeId}`, { method: "POST", body });
          result = await apiFetch(`/api/admin/update-notices/${publishIntent.noticeId}/publish`, {
            method: "POST",
            body: JSON.stringify({ send_email: sendEmail, request_id: requestId }),
          });
        } else {
          result = await apiFetch("/api/admin/update-notices", { method: "POST", body });
        }
        setNoticeDraft(emptyNoticeDraft);
        setEditingNoticeId(null);
      } else {
        result = await apiFetch(`/api/admin/update-notices/${publishIntent.noticeId}/publish`, {
          method: "POST",
          body: JSON.stringify({ send_email: sendEmail, request_id: requestId }),
        });
      }
      setPublishIntent(null);
      await loadDashboard();
      setMessage(sendEmail
        ? `公告已发布，邮件任务已创建${result.email_campaign ? `（待发送 ${result.email_campaign.pending}，跳过 ${result.email_campaign.skipped}）` : ""}。`
        : "公告已发布，本次未发送邮件。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "发布更新公告失败");
    } finally {
      setPublishing(false);
    }
  }

  function editUpdateNotice(notice: UpdateNotice) {
    setEditingNoticeId(notice.id);
    setNoticeDraft({
      title: notice.title,
      version: notice.version,
      itemsText: notice.items.join("\n"),
    });
  }

  async function publishUpdateNotice(id: number) {
    setPublishIntent({ source: "list", noticeId: id });
  }

  async function retryEmailCampaign(id: number) {
    await apiFetch(`/api/admin/update-email-campaigns/${id}/retry`, { method: "POST" });
    await loadDashboard();
    setMessage("失败邮件已重新加入发送队列。");
  }

  async function unpublishUpdateNotice(id: number) {
    await apiFetch(`/api/admin/update-notices/${id}/unpublish`, { method: "POST" });
    await loadDashboard();
  }

  const chartMax = useMemo(() => {
    const values = data?.usage_by_day.map((item) => item.count) || [];
    return Math.max(1, ...values);
  }, [data]);

  if (!loading && user?.role !== "admin") {
    return (
      <main className="admin-page">
        <section className="admin-locked">
          <h1>管理员面板</h1>
          <p>需要管理员账号登录后查看。</p>
          <Link href="/auth?redirect=/admin">登录管理员账号</Link>
        </section>
      </main>
    );
  }

  return (
    <main className="admin-page">
      <section className="admin-shell">
        <header className="admin-topbar">
          <div>
            <Link href="/">盈航</Link>
            <h1>运营管理台</h1>
            <p>查看用户增长、功能使用、反馈奖励和订单状态。</p>
          </div>
          <div className="admin-actions">
            <button type="button" onClick={loadDashboard}>
              <RefreshCw />
              刷新
            </button>
            <button
              type="button"
              onClick={() => {
                clearAuth();
                setUser(null);
                router.push("/auth");
              }}
            >
              <LogOut />
              退出
            </button>
          </div>
        </header>

        {message && <div className="admin-alert">{message}</div>}
        {loading && <div className="admin-alert">正在读取统计数据...</div>}

        {data && (
          <>
            <section className="admin-metrics">
              <Metric icon={Users} label="普通用户" value={data.totals.users} />
              <Metric icon={Gift} label="系统剩余次数" value={data.totals.credits} />
              <Metric icon={MessageSquare} label="待审核反馈" value={data.totals.feedback_pending} />
              <Metric icon={CreditCard} label="已支付订单" value={data.totals.orders_paid} />
            </section>

            <section className="admin-panel admin-bulk-credit-panel">
              <div className="admin-panel-head">
                <Gift />
                <h2>给所有现有用户增加次数</h2>
              </div>
              <p>仅包含确认发放时已经注册的账号。整批在一个事务中完成，失败不会只发给部分用户。</p>
              <div className="admin-bulk-credit-form">
                <label>
                  每人增加次数
                  <input
                    type="number"
                    min="1"
                    max="10000"
                    step="1"
                    value={bulkGrantDraft.credits}
                    onChange={(event) => setBulkGrantDraft((current) => ({ ...current, credits: event.target.value }))}
                  />
                </label>
                <label>
                  发放原因
                  <input
                    maxLength={300}
                    value={bulkGrantDraft.reason}
                    onChange={(event) => setBulkGrantDraft((current) => ({ ...current, reason: event.target.value }))}
                    placeholder="例如：平台更新福利"
                  />
                </label>
                <button type="button" onClick={requestBulkGrantConfirmation}>确认发放范围</button>
              </div>
              {!!data.credit_grant_campaigns?.length && (
                <div className="admin-bulk-credit-history">
                  <b>最近发放记录</b>
                  {data.credit_grant_campaigns.slice(0, 5).map((campaign) => (
                    <span key={campaign.id}>
                      {formatDate(campaign.completed_at || campaign.created_at)} · {campaign.granted_count} 人 × {campaign.credits} 次 · {campaign.reason}
                    </span>
                  ))}
                </div>
              )}
            </section>

            <section className="admin-grid">
              <article className="admin-panel admin-chart-panel">
                <div className="admin-panel-head">
                  <BarChart3 />
                  <h2>近 14 日功能使用</h2>
                </div>
                <div className="admin-chart">
                  {data.usage_by_day.length ? (
                    data.usage_by_day.map((item) => (
                      <div key={`${item.day}-${item.feature}`}>
                        <span>{item.day.slice(5)} · {featureLabel(item.feature)}</span>
                        <i style={{ width: `${Math.max(8, (item.count / chartMax) * 100)}%` }} />
                        <b>{item.count}</b>
                      </div>
                    ))
                  ) : (
                    <p>暂无使用记录。</p>
                  )}
                </div>
              </article>

              <article className="admin-panel">
                <div className="admin-panel-head">
                  <Users />
                  <h2>高频用户</h2>
                </div>
                <div className="admin-table">
                  {data.top_users.map((item) => (
                    <div key={item.id}>
                      <span>{item.username || item.email || item.phone}</span>
                      <b>{item.used_count} 次使用</b>
                      <em>{item.role === "admin" ? "无限免扣" : `${item.credits} 次余额`}</em>
                      {item.role !== "admin" && (
                        <div className="admin-credit-grant">
                          <input
                            type="number"
                            min="1"
                            step="1"
                            value={grantDrafts[item.id]?.credits || ""}
                            onChange={(event) => updateGrantDraft(item.id, { credits: event.target.value })}
                            placeholder="增加次数"
                          />
                          <input
                            value={grantDrafts[item.id]?.reason || ""}
                            onChange={(event) => updateGrantDraft(item.id, { reason: event.target.value })}
                            placeholder="增加原因，会写入邮件"
                          />
                          <button type="button" onClick={() => grantCredits(item.id)}>
                            增加并邮件提醒
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </article>
            </section>

            <section className="admin-grid">
              <article className="admin-panel">
                <div className="admin-panel-head">
                  <MessageSquare />
                  <h2>反馈建议</h2>
                </div>
                <div className="admin-list">
                  {data.feedback.map((item) => (
                    <div className="admin-list-item" key={item.id}>
                      <header>
                        <b>{item.category}</b>
                        <span>{item.status}</span>
                      </header>
                      <p>{item.content}</p>
                      <small>{item.phone} · {formatDate(item.created_at)}</small>
                      {item.status === "pending" && (
                        <button type="button" onClick={() => acceptFeedback(item.id)}>
                          <CheckCircle2 />
                          采纳并奖励 10 次
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </article>

              <article className="admin-panel">
                <div className="admin-panel-head">
                  <CreditCard />
                  <h2>订单系统</h2>
                </div>
                <div className="admin-list">
                  {data.orders.map((item) => (
                    <div className="admin-list-item" key={item.id}>
                      <header>
                        <b>{item.plan_name}</b>
                        <span>{orderStatusLabel(item.status)}</span>
                      </header>
                      <p>{item.product_type === "membership" ? `会员订阅 · ${item.plan_name}` : `${item.credits} 次`} · ¥{(item.amount_cents / 100).toFixed(2)}</p>
                      <small>{item.username || item.email || item.phone} · {item.order_no}</small>
                      {item.product_type === "membership" && (
                        <p>
                          {paymentMethodLabel(item.payment_method || "")}
                          {item.payer_name ? ` · ${item.payer_name}` : ""}
                          {item.payer_paid_at ? ` · ${item.payer_paid_at}` : ""}
                          {item.submitted_amount_cents ? ` · ¥${(item.submitted_amount_cents / 100).toFixed(2)}` : ""}
                          {item.payer_note ? ` · ${item.payer_note}` : ""}
                        </p>
                      )}
                      {item.admin_note ? <small>备注：{item.admin_note}</small> : null}
                      {item.product_type === "membership" && item.status === "submitted" && (
                        <>
                          <button type="button" onClick={() => confirmMembership(item.id)}>
                            <CheckCircle2 />
                            确认到账并开通会员
                          </button>
                          <button type="button" onClick={() => rejectMembership(item.id)}>
                            标记异常
                          </button>
                        </>
                      )}
                      {item.product_type !== "membership" && item.status !== "paid" && (
                        <button type="button" onClick={() => markPaid(item.id)}>
                          <CheckCircle2 />
                          标记已支付
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </article>
            </section>

            <section className="admin-grid">
              <article className="admin-panel">
                <div className="admin-panel-head">
                  <Megaphone />
                  <h2>更新公告</h2>
                </div>
                <div className="admin-notice-form">
                  <input
                    value={noticeDraft.title}
                    onChange={(event) => setNoticeDraft((current) => ({ ...current, title: event.target.value }))}
                    placeholder="公告标题，例如：本周更新"
                  />
                  <input
                    type="date"
                    value={noticeDraft.version}
                    onChange={(event) => setNoticeDraft((current) => ({ ...current, version: event.target.value }))}
                    aria-label="公告日期"
                  />
                  <textarea
                    value={noticeDraft.itemsText}
                    onChange={(event) => setNoticeDraft((current) => ({ ...current, itemsText: event.target.value }))}
                    placeholder="每行一条更新内容"
                    rows={5}
                  />
                  <div className="admin-notice-actions">
                    <button type="button" onClick={saveUpdateNotice}>
                      {editingNoticeId ? "保存修改" : "保存草稿"}
                    </button>
                    <button type="button" onClick={() => setPublishIntent({ source: "form", noticeId: editingNoticeId })}>
                      保存并发布
                    </button>
                    {editingNoticeId && (
                      <button
                        type="button"
                        onClick={() => {
                          setEditingNoticeId(null);
                          setNoticeDraft(emptyNoticeDraft);
                        }}
                      >
                        取消编辑
                      </button>
                    )}
                  </div>
                </div>
              </article>

              <article className="admin-panel">
                <div className="admin-panel-head">
                  <Megaphone />
                  <h2>公告列表</h2>
                </div>
                <div className="admin-list">
                  {(data.update_notices || []).map((notice) => (
                    <div className="admin-list-item" key={notice.id}>
                      <header>
                        <b>{notice.title}</b>
                        <span>{notice.status === "published" ? "已发布" : "草稿"}</span>
                      </header>
                      <p>{notice.version} · {formatDate(notice.published_at || notice.updated_at)}</p>
                      <small>{notice.items.join(" / ")}</small>
                      {notice.email_campaign && (
                        <div className="admin-email-campaign">
                          <b>邮件：{emailCampaignLabel(notice.email_campaign.status)}</b>
                          <span>成功 {notice.email_campaign.sent} · 待发送 {notice.email_campaign.pending + notice.email_campaign.sending} · 失败 {notice.email_campaign.failed} · 跳过 {notice.email_campaign.skipped}</span>
                          {notice.email_campaign.failed > 0 && (
                            <button type="button" onClick={() => retryEmailCampaign(notice.email_campaign!.id)}>重试失败邮件</button>
                          )}
                        </div>
                      )}
                      <button type="button" onClick={() => editUpdateNotice(notice)}>
                        编辑
                      </button>
                      {notice.status === "published" ? (
                        <button type="button" onClick={() => unpublishUpdateNotice(notice.id)}>
                          下线
                        </button>
                      ) : (
                        <button type="button" onClick={() => publishUpdateNotice(notice.id)}>
                          发布
                        </button>
                      )}
                    </div>
                  ))}
                  {!(data.update_notices || []).length && <p>暂无更新公告。</p>}
                </div>
              </article>
            </section>
          </>
        )}
      </section>
      {publishIntent && (
        <div className="admin-publish-backdrop" role="presentation" onMouseDown={() => !publishing && setPublishIntent(null)}>
          <section className="admin-publish-dialog" role="dialog" aria-modal="true" aria-labelledby="publish-dialog-title" ref={activeDialogRef} tabIndex={-1} onMouseDown={(event) => event.stopPropagation()}>
            <Megaphone />
            <h2 id="publish-dialog-title">如何发布本次更新？</h2>
            <p>网站更新弹窗会立即发布。邮件任务在后台发送，失败不会阻止公告上线。</p>
            <div>
              <button type="button" onClick={() => confirmPublish(false)} disabled={publishing}>仅发布网站弹窗</button>
              <button type="button" onClick={() => confirmPublish(true)} disabled={publishing}>网站弹窗 + 邮件推送</button>
              <button type="button" onClick={() => setPublishIntent(null)} disabled={publishing}>取消</button>
            </div>
          </section>
        </div>
      )}
      {bulkGrantIntent && (
        <div className="admin-publish-backdrop" role="presentation" onMouseDown={() => !bulkGrantSubmitting && setBulkGrantIntent(false)}>
          <section className="admin-publish-dialog" role="dialog" aria-modal="true" aria-labelledby="bulk-grant-dialog-title" ref={activeDialogRef} tabIndex={-1} onMouseDown={(event) => event.stopPropagation()}>
            <Gift />
            <h2 id="bulk-grant-dialog-title">确认给所有现有用户发放？</h2>
            <p>每位现有用户将增加 {bulkGrantDraft.credits} 次使用机会。原因：{bulkGrantDraft.reason.trim()}</p>
            <p>本操作会一次性写入全部账号，提交后不能在此处撤销。</p>
            <div>
              <button type="button" onClick={confirmBulkGrant} disabled={bulkGrantSubmitting}>
                {bulkGrantSubmitting ? "正在发放..." : "确认发放"}
              </button>
              <button type="button" onClick={() => setBulkGrantIntent(false)} disabled={bulkGrantSubmitting}>取消</button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}

function Metric({ icon: Icon, label, value }: { icon: typeof Users; label: string; value: number }) {
  return (
    <article>
      <Icon />
      <span>{label}</span>
      <b>{value}</b>
    </article>
  );
}

function featureLabel(value: string) {
  if (value === "review_report") return "AI 复盘";
  if (value === "watch_plan") return "AI 盯盘";
  if (value === "membership_free") return "会员免扣";
  return value;
}

function emailCampaignLabel(value: EmailCampaign["status"]) {
  if (value === "pending") return "等待发送";
  if (value === "sending") return "发送中";
  if (value === "completed") return "已完成";
  if (value === "partial_failed") return "部分失败";
  return "发送失败";
}

function orderStatusLabel(value: string) {
  if (value === "pending") return "待付款";
  if (value === "submitted") return "待确认";
  if (value === "paid") return "已支付";
  if (value === "rejected") return "异常";
  return value;
}

function paymentMethodLabel(value: string) {
  if (value === "alipay") return "支付宝";
  if (value === "wechat") return "微信";
  return "未提交付款方式";
}

function formatDate(value: string) {
  return value ? value.slice(0, 16).replace("T", " ") : "";
}

function todayDateInputValue() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function createPublishRequestId() {
  const randomUuid = globalThis.crypto?.randomUUID;
  if (typeof randomUuid === "function") return randomUuid.call(globalThis.crypto);
  return `notice-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
}

function createCreditGrantRequestId() {
  const randomUuid = globalThis.crypto?.randomUUID;
  if (typeof randomUuid === "function") return `credit-${randomUuid.call(globalThis.crypto)}`;
  return `credit-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
}

