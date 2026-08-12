"use client";

import { CheckCircle2, CreditCard, Gift, Mail, Megaphone, MessageSquare, PauseCircle, PlayCircle, RefreshCw, Search, Users, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { apiFetch, type ApiError } from "@/lib/auth-client";
import type { AdminAnalytics, FeatureUsagePoint, FeatureUsageTotal, RecentUsageEvent, UserGrowthPoint } from "@/components/admin/admin-analytics-types";
import { AdminConfirmDialog, type AdminConfirmIntent } from "@/components/admin/admin-confirm-dialog";
import { AdminStatusFilters, adminSectionPath, type AdminSection } from "@/components/admin/admin-navigation";
import { AdminOverviewSection } from "@/components/admin/admin-overview-section";

type PagedResult<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  filters?: Record<string, string>;
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

type AdminUser = {
  id: number;
  phone: string;
  username?: string;
  email?: string;
  role: string;
  status: "active" | "disabled" | string;
  used_count: number;
  credits: number;
  created_at?: string;
  last_login_at?: string | null;
};

type UsersResponse = PagedResult<AdminUser> & {
  campaigns: CreditGrantCampaign[];
};

type FeedbackItem = {
  id: number;
  user_id: number;
  phone: string;
  category: string;
  content: string;
  contact: string;
  status: string;
  reward_credits: number;
  admin_note?: string;
  created_at: string;
  reviewed_at?: string | null;
};

type OrderItem = {
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

type UpdateNotice = {
  id: number;
  title: string;
  version: string;
  items: string[];
  summary?: string;
  content_markdown?: string;
  audience?: "registered_users";
  expires_at?: string | null;
  status: "draft" | "published" | "archived";
  created_at: string;
  updated_at: string;
  published_at?: string | null;
  email_campaign?: EmailCampaign | null;
};

type DashboardPayload = {
  totals: {
    users: number;
    credits: number;
    feedback_pending: number;
    orders_paid: number;
  };
  usage_by_day: Array<{ day: string; feature: string; count: number; credits: number }>;
  new_users_by_day: Array<{ day: string; count: number }>;
  analytics?: AdminAnalytics;
  feedback: Array<{ status: string }>;
  orders: Array<{ status: string }>;
  update_notices: UpdateNotice[];
  daily_top5_email_failed_count?: number;
  daily_top5_close_email_failed_count?: number;
  ai_report_email_failed_count?: number;
};

type NoticeDraft = {
  title: string;
  version: string;
  summary: string;
  contentMarkdown: string;
};

type AdminEmailKind = "update_notice" | "daily_top5" | "daily_top5_close" | "market_day" | "ai_research";
type AdminEmailRetryType = "update_notice" | "daily_top5" | "daily_top5_close" | "ai_report";

const adminEmailRetryPathByType: Record<AdminEmailRetryType, (campaignId: number) => string> = {
  update_notice: (campaignId) => `/api/admin/update-email-campaigns/${campaignId}/retry`,
  daily_top5: (campaignId) => `/api/admin/daily-top5-email-campaigns/${campaignId}/retry`,
  daily_top5_close: (campaignId) => `/api/admin/daily-top5-close-email-campaigns/${campaignId}/retry`,
  ai_report: (campaignId) => `/api/admin/ai-report-email-campaigns/${campaignId}/retry`,
};

type AdminEmailItem = {
  id: number;
  kind: AdminEmailKind;
  retry_type: AdminEmailRetryType;
  title: string;
  summary: string;
  status: EmailCampaign["status"];
  total: number;
  pending: number;
  sending: number;
  sent: number;
  failed: number;
  skipped: number;
  created_at: string;
  next_retry_at?: string | null;
  full?: number;
  teaser?: number;
};

type AdminEmailCampaignsResponse = PagedResult<AdminEmailItem> & {
  delivery_totals: Pick<AdminEmailItem, "sent" | "pending" | "sending" | "failed" | "skipped">;
};

type AdminEmailFailureDetail = {
  kind: AdminEmailItem["kind"];
  campaign: EmailCampaign & { created_at?: string; finished_at?: string | null };
  failed_deliveries: Array<{
    email: string;
    status: string;
    attempt_count: number;
    last_error: string;
    next_attempt_at?: string | null;
    updated_at?: string | null;
  }>;
};

type AdminEmailProviderStatus = {
  provider: "smtp" | "outlook_graph" | "log";
  worker_count?: number;
  smtp: {
    configured: boolean;
    from_masked: string;
  };
  outlook: {
    configured: boolean;
    connected: boolean;
    account_masked: string;
    connected_at?: string;
    updated_at?: string;
    reconnect_required: boolean;
    last_error?: string;
  };
};

type OutlookDeviceConnection = {
  mode: "device_code";
  verification_uri: string;
  user_code: string;
  expires_at: string;
  interval_seconds: string;
};

type GrantDraft = {
  credits: string;
  reason: string;
};

const defaultNoticeDraft: NoticeDraft = {
  title: "",
  version: todayDateInputValue(),
  summary: "",
  contentMarkdown: "",
};

export function AdminOverviewPage() {
  const router = useRouter();
  const { params, replaceQuery } = useAdminQuery();
  const days = parseAnalyticsDays(params.get("days"));
  const dashboard = useAdminData<DashboardPayload>(`/api/admin/dashboard?days=${days}`);

  const analytics = useMemo(() => (dashboard.data ? normalizeDashboardAnalytics(dashboard.data) : null), [dashboard.data]);
  const pendingOrders = (dashboard.data?.orders || []).filter((item) => item.status === "submitted").length;
  const pendingFeedback = (dashboard.data?.feedback || []).filter((item) => item.status === "pending").length;
  const failedAnnouncementEmails = (dashboard.data?.update_notices || []).filter((item) => (item.email_campaign?.failed || 0) > 0).length;
  const failedDailyTop5Emails = dashboard.data?.daily_top5_email_failed_count || 0;
  const failedDailyTop5CloseEmails = dashboard.data?.daily_top5_close_email_failed_count || 0;
  const failedAiReportEmails = dashboard.data?.ai_report_email_failed_count || 0;

  function handleNavigate(section: AdminSection, emailKind?: "daily_top5" | "daily_top5_close") {
    const target = new URL(adminSectionPath(section), window.location.origin);
    if (section === "orders") target.searchParams.set("status", "submitted");
    if (section === "feedback") target.searchParams.set("status", "pending");
    if (section === "updates") target.searchParams.set("status", "published");
    if (section === "emails") {
      target.searchParams.set("status", "failed");
      if (emailKind) target.searchParams.set("kind", emailKind);
      target.hash = "email-tasks";
    }
    router.push(`${target.pathname}${target.search}${target.hash}`);
  }

  return (
    <section className="admin-section-stack">
      <PageToolbar
        title="总览"
        actions={(
          <>
            <div className="admin-analytics-window" aria-label="数据统计周期">
              <span>统计周期</span>
              {[7, 30, 90].map((value) => (
                <button
                  key={value}
                  type="button"
                  className={days === value ? "active" : ""}
                  onClick={() => replaceQuery({ days: String(value) })}
                  disabled={dashboard.loading}
                >
                  {value} 天
                </button>
              ))}
            </div>
            <button type="button" onClick={dashboard.reload} disabled={dashboard.loading}>
              <RefreshCw aria-hidden="true" />
              刷新
            </button>
          </>
        )}
      />
      <PageState
        loading={dashboard.loading}
        error={dashboard.error}
        hasData={Boolean(dashboard.data && analytics)}
        onRetry={dashboard.reload}
      >
        {dashboard.data && analytics ? (
          <AdminOverviewSection
            active
            totals={dashboard.data.totals}
            featureUsage={analytics.featureUsage}
            userGrowth={analytics.userGrowth}
            days={days}
            pendingOrders={pendingOrders}
            pendingFeedback={pendingFeedback}
            failedAnnouncementEmails={failedAnnouncementEmails}
            failedDailyTop5Emails={failedDailyTop5Emails}
            failedDailyTop5CloseEmails={failedDailyTop5CloseEmails}
            failedAiReportEmails={failedAiReportEmails}
            onNavigate={handleNavigate}
            featureLabel={featureLabel}
            recentUsageEvents={analytics.recentUsageEvents}
          />
        ) : null}
      </PageState>
    </section>
  );
}

export function AdminUsersPage() {
  const { params, replaceQuery } = useAdminQuery();
  const query = params.get("q") || "";
  const status = params.get("status") || "all";
  const page = parsePage(params.get("page"));
  const users = useAdminData<UsersResponse>(`/api/admin/users?${buildQuery({ q: query, status, page, page_size: 25 })}`);
  const [searchDraft, setSearchDraft] = useState(query);
  const [grantDrafts, setGrantDrafts] = useState<Record<number, GrantDraft>>({});
  const [bulkDraft, setBulkDraft] = useState<GrantDraft>({ credits: "10", reason: "" });
  const [message, setMessage] = useState("");
  const [expandedUserId, setExpandedUserId] = useState<number | null>(null);
  const [confirmIntent, setConfirmIntent] = useState<AdminConfirmIntent | null>(null);
  const [confirmSubmitting, setConfirmSubmitting] = useState(false);

  useEffect(() => setSearchDraft(query), [query]);

  const selectedUser = useMemo(
    () => users.data?.items.find((item) => item.id === expandedUserId) || null,
    [expandedUserId, users.data?.items],
  );

  function updateGrantDraft(userId: number, patch: Partial<GrantDraft>) {
    setGrantDrafts((current) => ({
      ...current,
      [userId]: { ...(current[userId] || { credits: "", reason: "" }), ...patch },
    }));
  }

  async function grantCredits(userId: number) {
    const draft = grantDrafts[userId] || { credits: "", reason: "" };
    const delta = Number(draft.credits);
    try {
      setMessage("");
      const result = await apiFetch<{ email_notification?: { sent?: boolean; error?: string } }>(`/api/admin/users/${userId}/credits`, {
        method: "POST",
        body: JSON.stringify({
          credits: delta,
          reason: draft.reason,
          request_id: createCreditAdjustmentRequestId(),
        }),
      });
      setGrantDrafts((current) => ({ ...current, [userId]: { credits: "", reason: "" } }));
      await users.reload();
      setMessage(delta > 0 && result.email_notification?.sent ? "次数已调整，并已发送邮件提醒。" : "次数已调整。");
    } catch (error) {
      setMessage(errorMessage(error, "调整次数失败"));
    }
  }

  function requestToggleUserStatus(user: AdminUser) {
    const nextStatus = user.status === "disabled" ? "active" : "disabled";
    const targetName = displayUserName(user);
    setConfirmIntent({
      actionLabel: nextStatus === "disabled" ? "确认暂停账号？" : "确认恢复账号？",
      confirmLabel: nextStatus === "disabled" ? "确认暂停" : "确认恢复",
      busyLabel: nextStatus === "disabled" ? "正在暂停..." : "正在恢复...",
      description: nextStatus === "disabled" ? "提交后会立即让该账号现有 session 失效。" : "恢复后该账号可重新登录并继续使用原有余额。",
      details: [`对象：${targetName}`, `用户 ID：${user.id}`, `当前余额：${user.credits} 次`, `累计使用：${user.used_count} 次`],
      danger: nextStatus === "disabled",
      onConfirm: async () => {
        setConfirmSubmitting(true);
        try {
          const result = await apiFetch<{ user: { id: number; display_name?: string; status: string } }>(`/api/admin/users/${user.id}/status`, {
            method: "POST",
            body: JSON.stringify({ status: nextStatus, expected_identity: targetName }),
          });
          await users.reload();
          setMessage(
            nextStatus === "disabled"
              ? `账号“${result.user.display_name || targetName}”（用户 ID：${user.id}）已暂停，现有 session 已失效。`
              : `账号“${result.user.display_name || targetName}”（用户 ID：${user.id}）已恢复，可重新登录。`,
          );
          setConfirmIntent(null);
        } finally {
          setConfirmSubmitting(false);
        }
      },
    });
  }

  function requestBulkGrant() {
    const credits = Number(bulkDraft.credits);
    if (!Number.isInteger(credits) || credits <= 0) {
      setMessage("增加次数必须是正整数");
      return;
    }
    if (bulkDraft.reason.trim().length < 2) {
      setMessage("请填写增加次数的原因");
      return;
    }
    setConfirmIntent({
      actionLabel: "确认给所有现有用户发放？",
      confirmLabel: "确认发放",
      busyLabel: "正在发放...",
      description: "本操作会一次性写入发放时已存在的全部普通用户账号，提交后不能在这里撤销。",
      details: [`范围：所有现有普通用户`, `每人增加：${bulkDraft.credits} 次`, `原因：${bulkDraft.reason.trim()}`],
      danger: true,
      onConfirm: async () => {
        setConfirmSubmitting(true);
        try {
          const result = await apiFetch<{ campaign: CreditGrantCampaign }>("/api/admin/credits/grant-all", {
            method: "POST",
            body: JSON.stringify({
              credits,
              reason: bulkDraft.reason.trim(),
              request_id: createCreditGrantRequestId(),
            }),
          });
          setBulkDraft({ credits: "10", reason: "" });
          await users.reload();
          setMessage(`批量发放完成：${result.campaign.granted_count} 位现有用户各增加 ${result.campaign.credits} 次。`);
          setConfirmIntent(null);
        } finally {
          setConfirmSubmitting(false);
        }
      },
    });
  }

  return (
    <section className="admin-section-stack">
      <PageToolbar
        title="用户与次数"
        actions={(
          <>
            <SearchForm
              value={searchDraft}
              onChange={setSearchDraft}
              onSubmit={() => replaceQuery({ q: searchDraft || null, status, page: "1" })}
              onClear={() => replaceQuery({ q: null, page: "1" })}
              placeholder="搜索用户名、邮箱、手机号或用户 ID"
              meta={users.data ? `共 ${users.data.total} 位用户` : ""}
            />
            <button type="button" onClick={users.reload} disabled={users.loading}>
              <RefreshCw aria-hidden="true" />
              刷新
            </button>
          </>
        )}
      />
      <AdminStatusFilters value={status} onChange={(value) => replaceQuery({ status: value, page: "1" })} options={["all", "active", "disabled"]} />
      {message ? <div className="admin-alert">{message}</div> : null}
      <PageState loading={users.loading} error={users.error} hasData={Boolean(users.data)} onRetry={users.reload}>
        {users.data ? (
          <>
            <section className="admin-panel admin-bulk-credit-panel">
              <div className="admin-panel-head">
                <Gift aria-hidden="true" />
                <h2>给所有现有用户增加次数</h2>
              </div>
              <p>整批操作在同一事务里完成，不会只发到部分账号。</p>
              <div className="admin-bulk-credit-form">
                <label>
                  每人增加次数
                  <input type="number" min="1" step="1" value={bulkDraft.credits} onChange={(event) => setBulkDraft((current) => ({ ...current, credits: event.target.value }))} />
                </label>
                <label>
                  发放原因
                  <input value={bulkDraft.reason} maxLength={300} onChange={(event) => setBulkDraft((current) => ({ ...current, reason: event.target.value }))} />
                </label>
                <button type="button" onClick={requestBulkGrant}>确认发放范围</button>
              </div>
              {users.data.campaigns.length ? (
                <div className="admin-bulk-credit-history">
                  <b>最近发放记录</b>
                  {users.data.campaigns.map((campaign) => (
                    <span key={campaign.id}>
                      {formatDate(campaign.completed_at || campaign.created_at)} · {campaign.granted_count} 人 × {campaign.credits} 次 · {campaign.reason}
                    </span>
                  ))}
                </div>
              ) : null}
            </section>
            <section className="admin-panel">
              <div className="admin-panel-head">
                <Users aria-hidden="true" />
                <h2>用户摘要</h2>
              </div>
              <div className="admin-list admin-list-stack">
                {users.data.items.map((item) => {
                  const nextStatus = item.status === "disabled" ? "active" : "disabled";
                  const draft = grantDrafts[item.id] || { credits: "", reason: "" };
                  const expanded = expandedUserId === item.id;
                  return (
                    <article className="admin-list-item admin-user-card" key={item.id}>
                      <div className="admin-user-main">
                        <header>
                          <b>{displayUserName(item)}</b>
                          <span>{item.status === "disabled" ? "已暂停" : "正常"}</span>
                        </header>
                        <div className="admin-user-meta">
                          <b>{item.used_count} 次使用</b>
                          <em>{item.credits} 次余额</em>
                          <strong className={`admin-user-status admin-user-status--${item.status === "disabled" ? "disabled" : "active"}`}>
                            {item.status === "disabled" ? "已暂停" : "正常"}
                          </strong>
                        </div>
                        <small>
                          用户 ID {item.id} · {item.phone}
                          {item.created_at ? ` · 注册 ${formatDate(item.created_at)}` : ""}
                          {item.last_login_at ? ` · 最近登录 ${formatDate(item.last_login_at)}` : ""}
                        </small>
                      </div>
                      <div className="admin-inline-actions">
                        <button type="button" className="admin-secondary-button" onClick={() => setExpandedUserId(expanded ? null : item.id)}>
                          {expanded ? "收起详情" : "查看详情"}
                        </button>
                      </div>
                      {expanded ? (
                        <div className="admin-detail-card">
                          <div className="admin-credit-grant">
                            <input
                              type="number"
                              step="1"
                              value={draft.credits}
                              onChange={(event) => updateGrantDraft(item.id, { credits: event.target.value })}
                              placeholder="正数增加，负数扣减"
                              aria-label={`调整 ${displayUserName(item)} 次数`}
                            />
                            <input
                              value={draft.reason}
                              onChange={(event) => updateGrantDraft(item.id, { reason: event.target.value })}
                              placeholder="填写调整原因，会写入台账"
                              aria-label={`填写 ${displayUserName(item)} 次数调整原因`}
                            />
                            <div className="admin-credit-actions">
                              <button type="button" onClick={() => void grantCredits(item.id)}>调整次数</button>
                              <button type="button" className="admin-secondary-button" onClick={() => requestToggleUserStatus(item)}>
                                {nextStatus === "disabled" ? <PauseCircle aria-hidden="true" /> : <PlayCircle aria-hidden="true" />}
                                {nextStatus === "disabled" ? "暂停账号" : "恢复账号"}
                              </button>
                            </div>
                          </div>
                        </div>
                      ) : null}
                    </article>
                  );
                })}
                {!users.data.items.length ? <EmptyState message="当前筛选条件下暂无用户。" /> : null}
              </div>
              <AdminPagination page={users.data.page} totalPages={users.data.total_pages} onChange={(nextPage) => replaceQuery({ page: String(nextPage) })} />
            </section>
          </>
        ) : null}
      </PageState>
      <AdminConfirmDialog intent={confirmIntent} submitting={confirmSubmitting} onClose={() => !confirmSubmitting && setConfirmIntent(null)} />
    </section>
  );
}

export function AdminOrdersPage() {
  const { params, replaceQuery } = useAdminQuery();
  const query = params.get("q") || "";
  const status = params.get("status") || "all";
  const page = parsePage(params.get("page"));
  const orders = useAdminData<PagedResult<OrderItem>>(`/api/admin/orders?${buildQuery({ q: query, status, page, page_size: 20 })}`);
  const [searchDraft, setSearchDraft] = useState(query);
  const [message, setMessage] = useState("");
  const [confirmIntent, setConfirmIntent] = useState<AdminConfirmIntent | null>(null);
  const [confirmSubmitting, setConfirmSubmitting] = useState(false);

  useEffect(() => setSearchDraft(query), [query]);

  function requestOrderAction(item: OrderItem, action: "paid" | "confirm-membership" | "confirm-credits" | "reject-membership" | "reject-credits") {
    const config = buildOrderConfirmIntent(item, action, async (reason) => {
      setConfirmSubmitting(true);
      try {
        const path = `/api/admin/orders/${item.id}/${mapOrderAction(action)}`;
        const body = reason ? JSON.stringify({ admin_note: reason }) : action === "confirm-membership"
          ? JSON.stringify({ admin_note: "已人工核对到账，开通会员" })
          : action === "confirm-credits"
            ? JSON.stringify({ admin_note: "已人工核对到账，增加次数" })
            : undefined;
        await apiFetch(path, { method: "POST", body });
        await orders.reload();
        setMessage("订单已更新。");
        setConfirmIntent(null);
      } finally {
        setConfirmSubmitting(false);
      }
    });
    setConfirmIntent(config);
  }

  return (
    <section className="admin-section-stack">
      <PageToolbar
        title="订单处理"
        actions={(
          <>
            <SearchForm
              value={searchDraft}
              onChange={setSearchDraft}
              onSubmit={() => replaceQuery({ q: searchDraft || null, status, page: "1" })}
              onClear={() => replaceQuery({ q: null, page: "1" })}
              placeholder="搜索订单号、用户、邮箱或手机号"
              meta={orders.data ? `共 ${orders.data.total} 条订单` : ""}
            />
            <button type="button" onClick={orders.reload} disabled={orders.loading}>
              <RefreshCw aria-hidden="true" />
              刷新
            </button>
          </>
        )}
      />
      <AdminStatusFilters value={status} onChange={(value) => replaceQuery({ status: value, page: "1" })} options={["all", "pending", "submitted", "paid", "rejected"]} />
      {message ? <div className="admin-alert">{message}</div> : null}
      <PageState loading={orders.loading} error={orders.error} hasData={Boolean(orders.data)} onRetry={orders.reload}>
        {orders.data ? (
          <section className="admin-panel">
            <div className="admin-panel-head">
              <CreditCard aria-hidden="true" />
              <h2>订单列表</h2>
            </div>
            <div className="admin-list admin-order-table">
              {orders.data.items.map((item) => (
                <article className="admin-list-item" key={item.id}>
                  <header>
                    <b>{item.plan_name}</b>
                    <span>{orderStatusLabel(item.status)}</span>
                  </header>
                  <p>{describeOrder(item)}</p>
                  <small>{displayOrderUser(item)} · {item.order_no}</small>
                  <p>{paymentSummary(item)}</p>
                  {item.admin_note ? <small>备注：{item.admin_note}</small> : null}
                  <div className="admin-order-actions">
                    {item.product_type === "membership" && item.status === "submitted" ? (
                      <>
                        <button type="button" onClick={() => requestOrderAction(item, "confirm-membership")}>
                          <CheckCircle2 aria-hidden="true" />
                          确认到账并开通会员
                        </button>
                        <button type="button" className="admin-secondary-button" onClick={() => requestOrderAction(item, "reject-membership")}>
                          标记异常
                        </button>
                      </>
                    ) : null}
                    {item.product_type === "credits" && item.status === "submitted" ? (
                      <>
                        <button type="button" onClick={() => requestOrderAction(item, "confirm-credits")}>
                          <CheckCircle2 aria-hidden="true" />
                          确认到账并增加次数
                        </button>
                        <button type="button" className="admin-secondary-button" onClick={() => requestOrderAction(item, "reject-credits")}>
                          驳回本次提交
                        </button>
                      </>
                    ) : null}
                    {item.product_type !== "membership" && item.product_type !== "credits" && item.status !== "paid" ? (
                      <button type="button" onClick={() => requestOrderAction(item, "paid")}>
                        <CheckCircle2 aria-hidden="true" />
                        标记已支付
                      </button>
                    ) : null}
                  </div>
                </article>
              ))}
              {!orders.data.items.length ? <EmptyState message="当前筛选条件下暂无订单。" /> : null}
            </div>
            <AdminPagination page={orders.data.page} totalPages={orders.data.total_pages} onChange={(nextPage) => replaceQuery({ page: String(nextPage) })} />
          </section>
        ) : null}
      </PageState>
      <AdminConfirmDialog intent={confirmIntent} submitting={confirmSubmitting} onClose={() => !confirmSubmitting && setConfirmIntent(null)} />
    </section>
  );
}

export function AdminFeedbackPage() {
  const { params, replaceQuery } = useAdminQuery();
  const query = params.get("q") || "";
  const status = params.get("status") || "all";
  const page = parsePage(params.get("page"));
  const feedback = useAdminData<PagedResult<FeedbackItem>>(`/api/admin/feedback?${buildQuery({ q: query, status, page, page_size: 20 })}`);
  const [searchDraft, setSearchDraft] = useState(query);
  const [message, setMessage] = useState("");
  const [confirmIntent, setConfirmIntent] = useState<AdminConfirmIntent | null>(null);
  const [confirmSubmitting, setConfirmSubmitting] = useState(false);

  useEffect(() => setSearchDraft(query), [query]);

  function rewardFeedback(item: FeedbackItem) {
    setConfirmIntent({
      actionLabel: "确认采纳反馈并奖励？",
      confirmLabel: "确认采纳并奖励",
      busyLabel: "正在提交...",
      description: "提交后会把该反馈标记为已采纳，并给对应用户增加 10 次使用机会。",
      details: [`反馈分类：${item.category}`, `用户：${item.phone}`, `提交时间：${formatDate(item.created_at)}`],
      danger: true,
      onConfirm: async () => {
        setConfirmSubmitting(true);
        try {
          await apiFetch(`/api/admin/feedback/${item.id}`, {
            method: "POST",
            body: JSON.stringify({ status: "accepted", admin_note: "反馈已采纳，奖励 10 次免费机会" }),
          });
          await feedback.reload();
          setMessage("反馈已采纳，并已发放奖励。");
          setConfirmIntent(null);
        } finally {
          setConfirmSubmitting(false);
        }
      },
    });
  }

  return (
    <section className="admin-section-stack">
      <PageToolbar
        title="反馈建议"
        actions={(
          <>
            <SearchForm
              value={searchDraft}
              onChange={setSearchDraft}
              onSubmit={() => replaceQuery({ q: searchDraft || null, status, page: "1" })}
              onClear={() => replaceQuery({ q: null, page: "1" })}
              placeholder="搜索分类、反馈内容或手机号"
              meta={feedback.data ? `共 ${feedback.data.total} 条反馈` : ""}
            />
            <button type="button" onClick={feedback.reload} disabled={feedback.loading}>
              <RefreshCw aria-hidden="true" />
              刷新
            </button>
          </>
        )}
      />
      <AdminStatusFilters value={status} onChange={(value) => replaceQuery({ status: value, page: "1" })} options={["all", "pending", "accepted", "rejected"]} />
      {message ? <div className="admin-alert">{message}</div> : null}
      <PageState loading={feedback.loading} error={feedback.error} hasData={Boolean(feedback.data)} onRetry={feedback.reload}>
        {feedback.data ? (
          <section className="admin-panel">
            <div className="admin-panel-head">
              <MessageSquare aria-hidden="true" />
              <h2>反馈列表</h2>
            </div>
            <div className="admin-list">
              {feedback.data.items.map((item) => (
                <article className="admin-list-item" key={item.id}>
                  <header>
                    <b>{item.category}</b>
                    <span>{item.status === "accepted" ? "已采纳" : item.status === "rejected" ? "已拒绝" : "待处理"}</span>
                  </header>
                  <p>{item.content}</p>
                  <small>{item.phone} · {formatDate(item.created_at)}</small>
                  {item.contact ? <small>联系方式：{item.contact}</small> : null}
                  {item.admin_note ? <small>处理说明：{item.admin_note}</small> : null}
                  {item.status === "pending" ? (
                    <button type="button" onClick={() => rewardFeedback(item)}>
                      <CheckCircle2 aria-hidden="true" />
                      采纳并奖励 10 次
                    </button>
                  ) : null}
                </article>
              ))}
              {!feedback.data.items.length ? <EmptyState message="当前筛选条件下暂无反馈。" /> : null}
            </div>
            <AdminPagination page={feedback.data.page} totalPages={feedback.data.total_pages} onChange={(nextPage) => replaceQuery({ page: String(nextPage) })} />
          </section>
        ) : null}
      </PageState>
      <AdminConfirmDialog intent={confirmIntent} submitting={confirmSubmitting} onClose={() => !confirmSubmitting && setConfirmIntent(null)} />
    </section>
  );
}

export function AdminUpdatesPage() {
  const { params, replaceQuery } = useAdminQuery();
  const status = params.get("status") || "all";
  const page = parsePage(params.get("page"));
  const notices = useAdminData<PagedResult<UpdateNotice>>(`/api/admin/update-notices?${buildQuery({ status, page, page_size: 12 })}`);
  const [draft, setDraft] = useState<NoticeDraft>(defaultNoticeDraft);
  const [editingNoticeId, setEditingNoticeId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [confirmIntent, setConfirmIntent] = useState<AdminConfirmIntent | null>(null);
  const [confirmSubmitting, setConfirmSubmitting] = useState(false);

  function resetDraft() {
    setDraft(defaultNoticeDraft);
    setEditingNoticeId(null);
  }

  async function saveDraft() {
    try {
      const body = JSON.stringify({
        title: draft.title,
        version: draft.version,
        summary: draft.summary,
        content_markdown: draft.contentMarkdown,
        status: "draft",
      });
      if (editingNoticeId) {
        await apiFetch(`/api/admin/update-notices/${editingNoticeId}`, { method: "POST", body });
      } else {
        await apiFetch("/api/admin/update-notices", { method: "POST", body });
      }
      resetDraft();
      await notices.reload();
      setMessage("更新公告已保存。");
    } catch (error) {
      setMessage(errorMessage(error, "保存更新公告失败"));
    }
  }

  function publish(sendEmail: boolean) {
    if (!draft.title.trim() || !draft.version.trim() || !draft.contentMarkdown.trim()) {
      setMessage("请完整填写公告标题、日期和更新内容。");
      return;
    }
    setConfirmIntent({
      actionLabel: sendEmail ? "确认发布并推送邮件？" : "确认仅发布网站弹窗？",
      confirmLabel: sendEmail ? "发布并推送" : "仅发布网站弹窗",
      busyLabel: "正在发布...",
      description: sendEmail ? "网站更新弹窗会立即发布，邮件任务将在后台异步发送。" : "本次只会上线网站更新弹窗，不会创建邮件任务。",
      details: [`标题：${draft.title.trim()}`, `日期：${draft.version.trim()}`, `邮件推送：${sendEmail ? "是" : "否"}`],
      danger: true,
      onConfirm: async () => {
        setConfirmSubmitting(true);
        try {
          const requestId = createPublishRequestId();
          if (editingNoticeId) {
            await apiFetch(`/api/admin/update-notices/${editingNoticeId}`, {
              method: "POST",
              body: JSON.stringify({
                title: draft.title,
                version: draft.version,
                summary: draft.summary,
                content_markdown: draft.contentMarkdown,
              }),
            });
            await apiFetch(`/api/admin/update-notices/${editingNoticeId}/publish`, {
              method: "POST",
              body: JSON.stringify({ send_email: sendEmail, request_id: requestId }),
            });
          } else {
            await apiFetch("/api/admin/update-notices", {
              method: "POST",
              body: JSON.stringify({
                title: draft.title,
                version: draft.version,
                summary: draft.summary,
                content_markdown: draft.contentMarkdown,
                status: "published",
                send_email: sendEmail,
                request_id: requestId,
              }),
            });
          }
          resetDraft();
          await notices.reload();
          setMessage(sendEmail ? "公告已发布，邮件任务已创建。" : "公告已发布，本次未发送邮件。");
          setConfirmIntent(null);
        } finally {
          setConfirmSubmitting(false);
        }
      },
    });
  }

  function editNotice(notice: UpdateNotice) {
    setEditingNoticeId(notice.id);
    setDraft({
      title: notice.title,
      version: notice.version,
      summary: notice.summary || "",
      contentMarkdown: notice.content_markdown || notice.items.map((item) => `- ${item}`).join("\n"),
    });
  }

  function requestNoticeAction(notice: UpdateNotice, action: "publish" | "unpublish" | "retry-email") {
    if (action === "publish") {
      setConfirmIntent({
        actionLabel: "确认发布该公告？",
        confirmLabel: "确认发布",
        busyLabel: "正在发布...",
        description: "发布后网站弹窗会立即可见，可按需选择是否重试历史失败邮件。",
        details: [`标题：${notice.title}`, `日期：${notice.version}`],
        danger: true,
        onConfirm: async () => {
          setConfirmSubmitting(true);
          try {
            await apiFetch(`/api/admin/update-notices/${notice.id}/publish`, {
              method: "POST",
              body: JSON.stringify({ send_email: false, request_id: createPublishRequestId() }),
            });
            await notices.reload();
            setMessage("公告已发布。");
            setConfirmIntent(null);
          } finally {
            setConfirmSubmitting(false);
          }
        },
      });
      return;
    }
    if (action === "unpublish") {
      setConfirmIntent({
        actionLabel: "确认下线该公告？",
        confirmLabel: "确认下线",
        busyLabel: "正在下线...",
        description: "下线后新的站内弹窗将不再展示该公告。",
        details: [`标题：${notice.title}`, `日期：${notice.version}`],
        danger: true,
        onConfirm: async () => {
          setConfirmSubmitting(true);
          try {
            await apiFetch(`/api/admin/update-notices/${notice.id}/unpublish`, { method: "POST" });
            await notices.reload();
            setMessage("公告已下线。");
            setConfirmIntent(null);
          } finally {
            setConfirmSubmitting(false);
          }
        },
      });
      return;
    }
    if (!notice.email_campaign) return;
    setConfirmIntent({
      actionLabel: "确认重试失败公告邮件？",
      confirmLabel: "重试失败邮件",
      busyLabel: "正在重试...",
      description: "只会重试当前公告中状态为失败的收件人，不会重复发送给已成功用户。",
      details: [`公告：${notice.title}`, `失败收件人：${notice.email_campaign.failed}`],
      danger: true,
      onConfirm: async () => {
        setConfirmSubmitting(true);
        try {
          await apiFetch(`/api/admin/update-email-campaigns/${notice.email_campaign!.id}/retry`, { method: "POST" });
          await notices.reload();
          setMessage("失败邮件已重新加入发送队列。");
          setConfirmIntent(null);
        } finally {
          setConfirmSubmitting(false);
        }
      },
    });
  }

  return (
    <section className="admin-section-stack">
      <PageToolbar
        title="更新公告"
        actions={(
          <>
            <AdminStatusFilters value={status} onChange={(value) => replaceQuery({ status: value, page: "1" })} options={["all", "draft", "published", "archived"]} />
            <button type="button" onClick={notices.reload} disabled={notices.loading}>
              <RefreshCw aria-hidden="true" />
              刷新
            </button>
          </>
        )}
      />
      {message ? <div className="admin-alert">{message}</div> : null}
      <section className="admin-grid">
        <article className="admin-panel">
          <div className="admin-panel-head">
            <Megaphone aria-hidden="true" />
            <h2>{editingNoticeId ? "编辑公告" : "新建公告"}</h2>
          </div>
          <div className="admin-notice-form">
            <input value={draft.title} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} placeholder="公告标题，例如：本周更新" />
            <input type="date" value={draft.version} onChange={(event) => setDraft((current) => ({ ...current, version: event.target.value }))} aria-label="公告日期" />
            <input value={draft.summary} onChange={(event) => setDraft((current) => ({ ...current, summary: event.target.value }))} placeholder="公告摘要（可选，会显示在正文前）" />
            <textarea
              value={draft.contentMarkdown}
              onChange={(event) => setDraft((current) => ({ ...current, contentMarkdown: event.target.value }))}
              placeholder={"Markdown 正文（必填）\n\n## 本次更新\n- 支持 **重点内容**\n- 查看 [使用说明](https://example.com)"}
              rows={12}
            />
            <small>支持标题、列表、引用、粗体/斜体、代码和 http(s) 链接；正文过长时会明确提示，不会静默截断。</small>
            <div className="admin-notice-actions">
              <button type="button" onClick={() => void saveDraft()}>{editingNoticeId ? "保存修改" : "保存草稿"}</button>
              <button type="button" onClick={() => publish(true)}>保存并发布</button>
              <button type="button" className="admin-secondary-button" onClick={() => publish(false)}>仅发布网站弹窗</button>
              {editingNoticeId ? <button type="button" className="admin-secondary-button" onClick={resetDraft}>取消编辑</button> : null}
            </div>
          </div>
        </article>
        <PageState loading={notices.loading} error={notices.error} hasData={Boolean(notices.data)} onRetry={notices.reload}>
          {notices.data ? (
            <article className="admin-panel">
              <div className="admin-panel-head">
                <Megaphone aria-hidden="true" />
                <h2>公告列表</h2>
              </div>
              <div className="admin-list">
                {notices.data.items.map((notice) => (
                  <article className="admin-list-item" key={notice.id}>
                    <header>
                      <b>{notice.title}</b>
                      <span>{notice.status === "published" ? "已发布" : notice.status === "archived" ? "已归档" : "草稿"}</span>
                    </header>
                    <p>{notice.version} · {formatDate(notice.published_at || notice.updated_at)}</p>
                    {notice.summary ? <p>{notice.summary}</p> : null}
                    <small>{notice.items.join(" / ")}</small>
                    {notice.email_campaign ? (
                      <div className="admin-email-campaign">
                        <b>邮件：{emailCampaignLabel(notice.email_campaign.status)}</b>
                        <span>{campaignDeliverySummary(notice.email_campaign)}</span>
                        {notice.email_campaign.failed > 0 ? (
                          <button type="button" onClick={() => requestNoticeAction(notice, "retry-email")}>重试失败邮件</button>
                        ) : null}
                      </div>
                    ) : null}
                    <div className="admin-notice-item-actions">
                      <button type="button" onClick={() => editNotice(notice)}>编辑</button>
                      {notice.status === "published" ? (
                        <button type="button" onClick={() => requestNoticeAction(notice, "unpublish")}>下线</button>
                      ) : notice.status === "draft" ? (
                        <button type="button" onClick={() => requestNoticeAction(notice, "publish")}>发布</button>
                      ) : null}
                    </div>
                  </article>
                ))}
                {!notices.data.items.length ? <EmptyState message="当前筛选条件下暂无公告。" /> : null}
              </div>
              <AdminPagination page={notices.data.page} totalPages={notices.data.total_pages} onChange={(nextPage) => replaceQuery({ page: String(nextPage) })} />
            </article>
          ) : null}
        </PageState>
      </section>
      <AdminConfirmDialog intent={confirmIntent} submitting={confirmSubmitting} onClose={() => !confirmSubmitting && setConfirmIntent(null)} />
    </section>
  );
}

export function AdminEmailsPage() {
  const { params, replaceQuery } = useAdminQuery();
  const kind = params.get("kind") || "all";
  const status = params.get("status") || "all";
  const dateFrom = params.get("date_from") || "";
  const dateTo = params.get("date_to") || "";
  const outlookResult = params.get("outlook") || "";
  const page = parsePage(params.get("page"));
  const emails = useAdminData<AdminEmailCampaignsResponse>(`/api/admin/emails?${buildQuery({ kind, status, date_from: dateFrom, date_to: dateTo, page, page_size: 20 })}`);
  const emailProvider = useAdminData<AdminEmailProviderStatus>("/api/admin/email-provider");
  const [message, setMessage] = useState("");
  const [providerAction, setProviderAction] = useState("");
  const [testEmail, setTestEmail] = useState("");
  const [outlookDevice, setOutlookDevice] = useState<OutlookDeviceConnection | null>(null);
  const [confirmIntent, setConfirmIntent] = useState<AdminConfirmIntent | null>(null);
  const [confirmSubmitting, setConfirmSubmitting] = useState(false);
  const [detail, setDetail] = useState<AdminEmailFailureDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");

  useEffect(() => {
    if (outlookResult === "connected") {
      setMessage("Outlook 已连接并设为当前发件通道。");
      void emailProvider.reload();
    } else if (outlookResult === "cancelled") {
      setMessage("已取消 Outlook 授权，当前发件通道未改变。");
    } else if (outlookResult === "error") {
      setMessage("Outlook 授权失败或已过期，请重新连接。");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outlookResult]);

  useEffect(() => {
    if (!emails.data || window.location.hash !== "#email-tasks") return;
    const frame = window.requestAnimationFrame(() => {
      document.getElementById("email-tasks")?.scrollIntoView({ block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [emails.data]);

  async function connectOutlook() {
    setProviderAction("connect");
    setMessage("");
    try {
      const result = await apiFetch<({ mode: "authorization_code"; authorization_url: string } | OutlookDeviceConnection)>("/api/admin/email-provider/outlook/connect", { method: "POST" });
      if (result.mode === "device_code") {
        setOutlookDevice(result);
        setMessage("请打开微软授权页并输入设备代码，完成后点击“检查授权结果”。");
        setProviderAction("");
      } else {
        window.location.assign(result.authorization_url);
      }
    } catch (error) {
      setMessage(errorMessage(error, "创建 Outlook 授权链接失败"));
      setProviderAction("");
    }
  }

  async function pollOutlookConnection() {
    setProviderAction("poll");
    setMessage("");
    try {
      const result = await apiFetch<{ status: string; connected: boolean }>("/api/admin/email-provider/outlook/poll", { method: "POST" });
      if (result.connected) {
        setOutlookDevice(null);
        await emailProvider.reload();
        setMessage("Outlook 已连接并设为当前发件通道。");
      } else if (result.status === "pending") {
        setMessage("微软授权尚未完成，请完成登录同意后再检查。");
      } else {
        setOutlookDevice(null);
        setMessage("设备授权已失效或被取消，请重新连接 Outlook。");
      }
    } catch (error) {
      setMessage(errorMessage(error, "检查 Outlook 授权失败"));
    } finally {
      setProviderAction("");
    }
  }

  async function selectEmailProvider(provider: "smtp" | "outlook_graph") {
    setProviderAction(`select-${provider}`);
    setMessage("");
    try {
      await apiFetch("/api/admin/email-provider/select", {
        method: "POST",
        body: JSON.stringify({ provider }),
      });
      await emailProvider.reload();
      setMessage(provider === "outlook_graph" ? "已切换为 Outlook Graph 发件。" : "已切换为 SMTP 发件。");
    } catch (error) {
      setMessage(errorMessage(error, "切换邮件通道失败"));
    } finally {
      setProviderAction("");
    }
  }

  async function sendProviderTest() {
    setProviderAction("test");
    setMessage("");
    try {
      const result = await apiFetch<{ provider: string; email: string }>("/api/admin/email-provider/test", {
        method: "POST",
        body: JSON.stringify({ email: testEmail }),
      });
      setMessage(`测试邮件已通过 ${result.provider} 发送至 ${result.email}。`);
    } catch (error) {
      setMessage(errorMessage(error, "测试邮件发送失败"));
    } finally {
      setProviderAction("");
    }
  }

  function confirmDisconnectOutlook() {
    setConfirmIntent({
      actionLabel: "断开 Outlook 连接？",
      confirmLabel: "确认断开",
      busyLabel: "正在断开...",
      description: "服务器保存的加密授权令牌将被删除；如果当前使用 Outlook，会自动回退到 SMTP。",
      details: [emailProvider.data?.outlook.account_masked || "当前 Outlook 账号"],
      danger: true,
      onConfirm: async () => {
        setConfirmSubmitting(true);
        try {
          await apiFetch("/api/admin/email-provider/outlook/disconnect", { method: "POST" });
          await emailProvider.reload();
          setMessage("Outlook 已断开，授权令牌已从服务器删除。");
          setConfirmIntent(null);
        } finally {
          setConfirmSubmitting(false);
        }
      },
    });
  }

  async function openFailureDetail(item: AdminEmailItem) {
    setDetail(null);
    setDetailError("");
    setDetailLoading(true);
    try {
      setDetail(await apiFetch<AdminEmailFailureDetail>(`/api/admin/emails/${item.kind}/${item.id}`));
    } catch (error) {
      setDetailError(errorMessage(error, "读取失败详情失败"));
    } finally {
      setDetailLoading(false);
    }
  }

  function retryCampaign(item: AdminEmailItem) {
    const path = adminEmailRetryPathByType[item.retry_type](item.id);
    setConfirmIntent({
      actionLabel: "确认重试失败邮件？",
      confirmLabel: "重试失败邮件",
      busyLabel: "正在重试...",
      description: "只会重试当前任务中状态为失败的收件人，不会重复发送给已成功用户。",
      details: [`任务：${item.title}`, `失败收件人：${item.failed}`, `等待中：${item.pending + item.sending}`],
      danger: true,
      onConfirm: async () => {
        setConfirmSubmitting(true);
        try {
          await apiFetch(path, { method: "POST" });
          await emails.reload();
          setMessage("失败邮件已重新加入发送队列。");
          setConfirmIntent(null);
        } finally {
          setConfirmSubmitting(false);
        }
      },
    });
  }

  return (
    <section className="admin-section-stack">
      <PageToolbar
        title="邮件推送"
        actions={(
          <>
            <label className="admin-toolbar-field">
              <span>任务类型</span>
              <select value={kind} onChange={(event) => replaceQuery({ kind: event.target.value, page: "1" })}>
                <option value="all">全部任务</option>
                <option value="update_notice">公告邮件</option>
                <option value="daily_top5">每日 TOP5</option>
                <option value="daily_top5_close">每日 TOP5 收盘表现</option>
                <option value="market_day">市场日报</option>
                <option value="ai_research">AI 复盘</option>
              </select>
            </label>
            <label className="admin-toolbar-field">
              <span>状态</span>
              <select value={status} onChange={(event) => replaceQuery({ status: event.target.value, page: "1" })}>
                <option value="all">全部状态</option>
                <option value="pending">等待发送</option>
                <option value="sending">发送中</option>
                <option value="completed">已完成</option>
                <option value="partial_failed">部分失败</option>
                <option value="failed">发送失败</option>
              </select>
            </label>
            <label className="admin-toolbar-field">
              <span>开始日期</span>
              <input type="date" value={dateFrom} onChange={(event) => replaceQuery({ date_from: event.target.value || null, page: "1" })} />
            </label>
            <label className="admin-toolbar-field">
              <span>结束日期</span>
              <input type="date" value={dateTo} onChange={(event) => replaceQuery({ date_to: event.target.value || null, page: "1" })} />
            </label>
            <button type="button" onClick={emails.reload} disabled={emails.loading}>
              <RefreshCw aria-hidden="true" />
              刷新
            </button>
          </>
        )}
      />
      {message ? <div className="admin-alert">{message}</div> : null}
      <PageState loading={emailProvider.loading} error={emailProvider.error} hasData={Boolean(emailProvider.data)} onRetry={emailProvider.reload}>
        {emailProvider.data ? (
          <section className="admin-panel">
            <div className="admin-panel-head">
              <Mail aria-hidden="true" />
              <h2>发件通道</h2>
            </div>
            <div className="admin-list">
              <article className="admin-list-item">
                <header><b>当前通道</b><span>{emailProvider.data.provider === "outlook_graph" ? "Outlook Graph" : emailProvider.data.provider === "smtp" ? "SMTP" : "仅日志"}</span></header>
                <p>邮件 worker：{emailProvider.data.worker_count ?? "-"} · SMTP：{emailProvider.data.smtp.configured ? emailProvider.data.smtp.from_masked || "已配置" : "未配置"}</p>
                <div className="admin-email-campaign">
                  <button type="button" disabled={!emailProvider.data.smtp.configured || Boolean(providerAction) || emailProvider.data.provider === "smtp"} onClick={() => selectEmailProvider("smtp")}>使用 SMTP</button>
                  <button type="button" disabled={!emailProvider.data.outlook.connected || Boolean(providerAction) || emailProvider.data.provider === "outlook_graph"} onClick={() => selectEmailProvider("outlook_graph")}>使用 Outlook</button>
                </div>
              </article>
              <article className="admin-list-item">
                <header><b>Outlook / Hotmail</b><span>{emailProvider.data.outlook.connected ? "已连接" : emailProvider.data.outlook.reconnect_required ? "需要重新连接" : emailProvider.data.outlook.configured ? "等待授权" : "等待服务器配置"}</span></header>
                <p>{emailProvider.data.outlook.account_masked || "尚未配置发件账号"}{emailProvider.data.outlook.connected_at ? ` · 连接于 ${formatDate(emailProvider.data.outlook.connected_at)}` : ""}</p>
                {emailProvider.data.outlook.last_error ? <small>{emailProvider.data.outlook.last_error}</small> : null}
                <div className="admin-email-campaign">
                  <button type="button" disabled={!emailProvider.data.outlook.configured || Boolean(providerAction)} onClick={connectOutlook}>{emailProvider.data.outlook.connected ? "重新连接 Outlook" : "连接 Outlook"}</button>
                  {emailProvider.data.outlook.connected ? <button type="button" disabled={Boolean(providerAction)} onClick={confirmDisconnectOutlook}>断开连接</button> : null}
                </div>
                {outlookDevice ? (
                  <div className="admin-email-campaign">
                    <span>设备代码：<strong>{outlookDevice.user_code}</strong> · 有效期至 {formatDate(outlookDevice.expires_at)}</span>
                    <a href={outlookDevice.verification_uri} target="_blank" rel="noreferrer">打开微软授权页</a>
                    <button type="button" disabled={Boolean(providerAction)} onClick={pollOutlookConnection}>{providerAction === "poll" ? "检查中..." : "检查授权结果"}</button>
                  </div>
                ) : null}
              </article>
              <article className="admin-list-item">
                <header><b>发送测试邮件</b><span>使用当前通道</span></header>
                <div className="admin-notice-item-actions">
                  <input type="email" value={testEmail} placeholder="收件邮箱" aria-label="测试邮件收件邮箱" onChange={(event) => setTestEmail(event.target.value)} />
                  <button type="button" disabled={!testEmail.trim() || Boolean(providerAction) || emailProvider.data.provider === "log"} onClick={sendProviderTest}>{providerAction === "test" ? "发送中..." : "发送测试邮件"}</button>
                </div>
              </article>
            </div>
          </section>
        ) : null}
      </PageState>
      <PageState loading={emails.loading} error={emails.error} hasData={Boolean(emails.data)} onRetry={emails.reload}>
        {emails.data ? (
          <section className="admin-panel" id="email-tasks">
            <div className="admin-panel-head">
              <Mail aria-hidden="true" />
              <h2>{kind === "daily_top5" && status === "failed" ? "每日 TOP5 失败邮件" : kind === "daily_top5_close" && status === "failed" ? "每日 TOP5 收盘失败邮件" : "邮件任务"}</h2>
            </div>
            <div className="admin-email-campaign" aria-label="邮件任务汇总">
              <strong>{status === "failed" ? `失败涉及 ${emails.data.total} 个任务` : `共 ${emails.data.total} 个任务`}</strong>
              <span>成功 {emails.data.delivery_totals.sent} · 失败 {emails.data.delivery_totals.failed} · 跳过 {emails.data.delivery_totals.skipped}</span>
            </div>
            <div className="admin-list">
              {emails.data.items.map((item) => {
                const waitingForRetry = Boolean(item.next_retry_at && (item.pending > 0 || item.sending > 0));
                const retryable = item.failed > 0 && !waitingForRetry && item.pending === 0 && item.sending === 0;
                return (
                  <article className="admin-list-item" key={`${item.kind}-${item.id}`}>
                    <header>
                      <b>{item.title}</b>
                      <span>{emailCampaignLabel(item.status)}</span>
                    </header>
                    <p>{formatDate(item.created_at)}</p>
                    <div className="admin-email-campaign">
                      <span>{item.summary}</span>
                      <span>{campaignDeliverySummary(item)}</span>
                      {waitingForRetry && item.next_retry_at ? <span>等待自动重试：{formatDate(item.next_retry_at)}</span> : null}
                      {item.failed > 0 ? <button type="button" onClick={() => openFailureDetail(item)}>查看失败详情</button> : null}
                      {retryable ? <button type="button" onClick={() => retryCampaign(item)}>重试失败邮件</button> : null}
                    </div>
                  </article>
                );
              })}
              {!emails.data.items.length ? <EmptyState message="当前筛选条件下暂无邮件任务。" /> : null}
            </div>
            <AdminPagination page={emails.data.page} totalPages={emails.data.total_pages} onChange={(nextPage) => replaceQuery({ page: String(nextPage) })} />
          </section>
        ) : null}
      </PageState>
      {(detailLoading || detailError || detail) ? (
        <div className="admin-publish-backdrop" role="presentation">
          <section className="admin-publish-dialog admin-email-detail" role="dialog" aria-modal="true" aria-labelledby="admin-email-detail-title">
            <header>
              <h2 id="admin-email-detail-title">失败邮件详情</h2>
              <button type="button" aria-label="关闭失败邮件详情" onClick={() => { setDetail(null); setDetailError(""); setDetailLoading(false); }}><X aria-hidden="true" /></button>
            </header>
            {detailLoading ? <p role="status">正在读取失败收件人...</p> : null}
            {detailError ? <div className="admin-alert" role="alert">{detailError}</div> : null}
            {detail ? (
              <div className="admin-list">
                <p>失败 {detail.failed_deliveries.length} 人 · 任务状态 {emailCampaignLabel(detail.campaign.status)}</p>
                {detail.failed_deliveries.map((delivery) => (
                  <article className="admin-list-item" key={`${delivery.email}-${delivery.updated_at || delivery.attempt_count}`}>
                    <header><b>{delivery.email}</b><span>{delivery.status}</span></header>
                    <p>{delivery.last_error || "未记录失败原因"}</p>
                    <small>尝试 {delivery.attempt_count} 次 · {formatDate(delivery.updated_at)}</small>
                  </article>
                ))}
                {!detail.failed_deliveries.length ? <EmptyState message="当前任务没有终态失败收件人。" /> : null}
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
      <AdminConfirmDialog intent={confirmIntent} submitting={confirmSubmitting} onClose={() => !confirmSubmitting && setConfirmIntent(null)} />
    </section>
  );
}

function PageToolbar({ title, actions }: { title: string; actions: ReactNode }) {
  return (
    <div className="admin-page-toolbar">
      <h2>{title}</h2>
      <div className="admin-page-toolbar-actions">{actions}</div>
    </div>
  );
}

function PageState({
  loading,
  error,
  hasData,
  onRetry,
  children,
}: {
  loading: boolean;
  error: string;
  hasData: boolean;
  onRetry: () => void;
  children: ReactNode;
}) {
  if (loading && !hasData) {
    return <div className="admin-alert">正在读取数据...</div>;
  }
  if (error && !hasData) {
    return (
      <section className="admin-panel admin-page-state">
        <b>读取失败</b>
        <p>{error}</p>
        <button type="button" onClick={onRetry}>重试</button>
      </section>
    );
  }
  return (
    <>
      {error ? <div className="admin-alert">{error}</div> : null}
      {children}
    </>
  );
}

function SearchForm({
  value,
  onChange,
  onSubmit,
  onClear,
  placeholder,
  meta,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onClear: () => void;
  placeholder: string;
  meta: string;
}) {
  return (
    <form
      className="admin-user-toolbar"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <label className="admin-user-search">
        <Search aria-hidden="true" />
        <input type="search" value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} autoComplete="off" spellCheck={false} />
        {value ? (
          <button type="button" className="admin-user-search-clear" onClick={onClear} aria-label="清空搜索">
            <X aria-hidden="true" />
          </button>
        ) : null}
      </label>
      {meta ? <p className="admin-user-search-meta" aria-live="polite">{meta}</p> : null}
    </form>
  );
}

function EmptyState({ message }: { message: string }) {
  return <div className="admin-filter-empty">{message}</div>;
}

function AdminPagination({
  page,
  totalPages,
  onChange,
}: {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
}) {
  if (totalPages <= 1) return null;
  return (
    <nav className="admin-pagination" aria-label="分页导航">
      <button type="button" onClick={() => onChange(page - 1)} disabled={page <= 1}>上一页</button>
      <span>第 {page} / {totalPages} 页</span>
      <button type="button" onClick={() => onChange(page + 1)} disabled={page >= totalPages}>下一页</button>
    </nav>
  );
}

function useAdminQuery() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const replaceQuery = useCallback((patch: Record<string, string | null | undefined>) => {
    const next = new URLSearchParams(params.toString());
    Object.entries(patch).forEach(([key, value]) => {
      if (!value) next.delete(key);
      else next.set(key, value);
    });
    const query = next.toString();
    router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }, [params, pathname, router]);

  return { params, replaceQuery };
}

function useAdminData<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadToken, setReloadToken] = useState(0);

  const reload = useCallback(() => setReloadToken((current) => current + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    apiFetch<T>(path, { signal: controller.signal })
      .then((payload) => setData(payload))
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        setError(errorMessage(err, "读取失败"));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [path, reloadToken]);

  return { data, loading, error, reload };
}

function buildQuery(values: Record<string, string | number | null | undefined>) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") return;
    params.set(key, String(value));
  });
  return params.toString();
}

function parsePage(value: string | null) {
  const page = Number(value);
  return Number.isInteger(page) && page > 0 ? page : 1;
}

function parseAnalyticsDays(value: string | null) {
  const days = Number(value);
  return days === 7 || days === 90 ? days : 30;
}

function errorMessage(error: unknown, fallback: string) {
  const apiError = error as ApiError | Error;
  return apiError?.message || fallback;
}

function normalizeDashboardAnalytics(data: DashboardPayload): {
  featureUsage: { totals: FeatureUsageTotal[]; byDay: FeatureUsagePoint[] };
  userGrowth: { startingUsers: number; totalUsers: number; byDay: UserGrowthPoint[] };
  recentUsageEvents: RecentUsageEvent[];
} {
  const featureByDay = data.analytics?.feature_usage?.by_day || data.usage_by_day || [];
  const featureTotals = data.analytics?.feature_usage?.totals || deriveFeatureTotals(featureByDay);
  const growthRows = data.analytics?.user_growth?.by_day;
  const legacyNewUsers = data.new_users_by_day || [];
  const legacyNewTotal = legacyNewUsers.reduce((sum, item) => sum + Number(item.count || 0), 0);
  const startingUsers = Number(data.analytics?.user_growth?.starting_users ?? Math.max(0, data.totals.users - legacyNewTotal));
  let runningUsers = startingUsers;
  const userGrowth = growthRows?.map((item) => ({
    day: item.day,
    new_users: Number(item.new_users || 0),
    cumulative_users: Number(item.cumulative_users || 0),
  })) || legacyNewUsers.map((item) => {
    runningUsers += Number(item.count || 0);
    return { day: item.day, new_users: Number(item.count || 0), cumulative_users: runningUsers };
  });
  return {
    featureUsage: { totals: featureTotals, byDay: featureByDay },
    userGrowth: {
      startingUsers,
      totalUsers: Number(data.analytics?.user_growth?.total_users ?? data.totals.users),
      byDay: userGrowth,
    },
    recentUsageEvents: data.analytics?.recent_usage_events || [],
  };
}

function deriveFeatureTotals(points: FeatureUsagePoint[]): FeatureUsageTotal[] {
  const totals = new Map<string, { count: number; credits: number }>();
  points.forEach((item) => {
    const current = totals.get(item.feature) || { count: 0, credits: 0 };
    current.count += Number(item.count || 0);
    current.credits += Number(item.credits || 0);
    totals.set(item.feature, current);
  });
  return Array.from(totals, ([feature, values]) => ({ feature, ...values })).sort((a, b) => b.count - a.count);
}

function featureLabel(value: string) {
  if (value === "review_report") return "AI 复盘";
  if (value === "watch_plan") return "AI 盯盘";
  if (value === "auction_strength_view") return "每日 TOP5";
  if (value === "market_day_report") return "AI 当日行情";
  if (value === "ai_research_view") return "AI 研报";
  if (value === "membership_free") return "会员免扣";
  return value;
}

function displayUserName(user: AdminUser) {
  return user.username || user.email || user.phone || `用户 #${user.id}`;
}

function buildOrderConfirmIntent(item: OrderItem, action: "paid" | "confirm-membership" | "confirm-credits" | "reject-membership" | "reject-credits", onConfirm: (reason: string) => Promise<void>) {
  const commonDetails = [`订单：${item.order_no}`, `用户：${displayOrderUser(item)}`, `金额：¥${(item.amount_cents / 100).toFixed(2)}`];
  if (action === "paid") {
    return {
      actionLabel: "确认标记为已支付？",
      confirmLabel: "确认已支付",
      busyLabel: "正在提交...",
      description: "仅用于旧订单的通用已支付流。提交后会更新订单状态。",
      details: commonDetails,
      danger: true,
      onConfirm,
    };
  }
  if (action === "confirm-membership") {
    return {
      actionLabel: "确认到账并开通会员？",
      confirmLabel: "确认开通",
      busyLabel: "正在开通...",
      description: "提交后会把该会员订单标记为已完成，并为用户写入会员权益。",
      details: commonDetails,
      danger: true,
      onConfirm,
    };
  }
  if (action === "confirm-credits") {
    return {
      actionLabel: "确认到账并增加次数？",
      confirmLabel: "确认增加次数",
      busyLabel: "正在提交...",
      description: "提交后会把该次数订单标记为已完成，并为用户写入次数余额。",
      details: [...commonDetails, `增加次数：${item.credits}`],
      danger: true,
      onConfirm,
    };
  }
  return {
    actionLabel: action === "reject-membership" ? "确认标记会员订单异常？" : "确认驳回次数订单？",
    confirmLabel: action === "reject-membership" ? "确认标记异常" : "确认驳回",
    busyLabel: "正在提交...",
    description: "提交后会保留当前用户输入，并把订单置为异常状态。",
    details: commonDetails,
    danger: true,
    reasonLabel: "处理说明",
    reasonPlaceholder: "请填写驳回或异常原因",
    reasonRequired: true,
    onConfirm,
  };
}

function mapOrderAction(action: "paid" | "confirm-membership" | "confirm-credits" | "reject-membership" | "reject-credits") {
  if (action === "paid") return "paid";
  if (action === "confirm-membership") return "confirm-membership";
  if (action === "confirm-credits") return "confirm-credits";
  if (action === "reject-membership") return "reject-membership";
  return "reject-credits";
}

function describeOrder(item: OrderItem) {
  if (item.product_type === "membership") return `会员订阅 · ${item.plan_name} · ¥${(item.amount_cents / 100).toFixed(2)}`;
  if (item.product_type === "credits") return `${item.credits} 次 · ¥${(item.amount_cents / 100).toFixed(2)} · 固定 1 元 / 次`;
  return `${item.plan_name} · ¥${(item.amount_cents / 100).toFixed(2)}`;
}

function paymentSummary(item: OrderItem) {
  const parts = [
    paymentMethodLabel(item.payment_method || ""),
    item.payer_name || "",
    item.payer_paid_at || "",
    typeof item.submitted_amount_cents === "number" ? `¥${(item.submitted_amount_cents / 100).toFixed(2)}` : "",
    item.payer_note || "",
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "尚未提交付款信息";
}

function displayOrderUser(item: OrderItem) {
  return item.username || item.email || item.phone;
}

function emailCampaignLabel(value: EmailCampaign["status"]) {
  if (value === "pending") return "等待发送";
  if (value === "sending") return "发送中";
  if (value === "completed") return "已完成";
  if (value === "partial_failed") return "部分失败";
  return "发送失败";
}

function campaignDeliverySummary(campaign: Pick<EmailCampaign, "sent" | "pending" | "sending" | "failed" | "skipped">) {
  return `成功 ${campaign.sent} · 待发送 ${campaign.pending} · 发送中 ${campaign.sending} · 失败 ${campaign.failed} · 跳过 ${campaign.skipped}`;
}

function orderStatusLabel(value: string) {
  if (value === "pending") return "待付款";
  if (value === "submitted") return "待确认";
  if (value === "paid") return "已完成";
  if (value === "rejected") return "异常";
  return value;
}

function paymentMethodLabel(value: string) {
  if (value === "alipay") return "支付宝";
  if (value === "wechat") return "微信";
  return "未提交付款方式";
}

function formatDate(value?: string | null) {
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

function createCreditAdjustmentRequestId() {
  const randomUuid = globalThis.crypto?.randomUUID;
  if (typeof randomUuid === "function") return `credit-adjust-${randomUuid.call(globalThis.crypto)}`;
  return `credit-adjust-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
}
