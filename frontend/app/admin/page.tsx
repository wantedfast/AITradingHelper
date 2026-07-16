"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink, Gift, LogOut, Megaphone, MessageSquare, RefreshCw } from "lucide-react";
import { apiFetch, clearAuth, getAuthToken, getStoredUser, refreshCurrentUser, type UserProfile } from "@/lib/auth-client";
import { useModalAccessibility } from "@/lib/modal-accessibility";
import { AdminNavigation, adminSections, type AdminSection } from "@/components/admin/admin-navigation";
import { AdminOverviewSection } from "@/components/admin/admin-overview-section";
import { AdminFeedbackSection, AdminOrdersSection, AdminUpdatesSection, AdminUsersSection } from "@/components/admin/admin-sections";
import type { AdminAnalytics, FeatureUsagePoint, FeatureUsageTotal, HighFrequencyUser, UserGrowthPoint } from "@/components/admin/admin-analytics-types";

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
  const [section, setSection] = useState<AdminSection>("overview");
  const [days, setDays] = useState(30);
  const [orderFilter, setOrderFilter] = useState("submitted");
  const [feedbackFilter, setFeedbackFilter] = useState("pending");
  const [feedbackRewardIntent, setFeedbackRewardIntent] = useState<number | null>(null);
  const activeDialogRef = useRef<HTMLElement>(null);

  useModalAccessibility(
    Boolean(publishIntent) || bulkGrantIntent || feedbackRewardIntent !== null,
    () => {
      if (!publishing) setPublishIntent(null);
      if (!bulkGrantSubmitting) setBulkGrantIntent(false);
      setFeedbackRewardIntent(null);
    },
    activeDialogRef,
    !publishing && !bulkGrantSubmitting,
  );

  const loadDashboard = useCallback(async (windowDays: number) => {
    setLoading(true);
    setMessage("");
    try {
      const payload = await apiFetch<DashboardPayload>(`/api/admin/dashboard?days=${windowDays}`);
      setData(payload);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取统计失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const querySection = params.get("section");
    const queryDays = parseAnalyticsDays(params.get("days"));
    const initialSection = isAdminSection(querySection) ? querySection : "overview";
    if (isAdminSection(querySection)) setSection(querySection);
    setDays(queryDays);
    if (querySection !== initialSection || params.get("days") !== String(queryDays)) {
      router.replace(`/admin?section=${initialSection}&days=${queryDays}`, { scroll: false });
    }
    if (!getAuthToken()) {
      setLoading(false);
      router.replace("/admin/login?redirect=/admin");
      return;
    }
    refreshCurrentUser()
      .then((nextUser) => {
        setUser(nextUser);
        if (nextUser?.role === "admin") return loadDashboard(queryDays);
        setLoading(false);
      })
      .catch(() => {
        clearAuth();
        setLoading(false);
        router.replace("/admin/login?redirect=/admin");
      });
  }, [loadDashboard, router]);

  function changeSection(nextSection: AdminSection) {
    setSection(nextSection);
    router.replace(`/admin?section=${nextSection}&days=${days}`, { scroll: false });
  }

  function changeDays(nextDays: number) {
    if (nextDays === days) return;
    setDays(nextDays);
    router.replace(`/admin?section=${section}&days=${nextDays}`, { scroll: false });
    void loadDashboard(nextDays);
  }

  async function acceptFeedback(id: number) {
    await apiFetch(`/api/admin/feedback/${id}`, {
      method: "POST",
      body: JSON.stringify({ status: "accepted", admin_note: "反馈已采纳，奖励 10 次免费机会" }),
    });
    await loadDashboard(days);
    setFeedbackRewardIntent(null);
  }

  async function markPaid(id: number) {
    await apiFetch(`/api/admin/orders/${id}/paid`, { method: "POST" });
    await loadDashboard(days);
  }

  async function confirmMembership(id: number) {
    await apiFetch(`/api/admin/orders/${id}/confirm-membership`, {
      method: "POST",
      body: JSON.stringify({ admin_note: "已人工核对到账，开通会员" }),
    });
    await loadDashboard(days);
  }

  async function rejectMembership(id: number) {
    const reason = window.prompt("请输入异常或驳回原因");
    if (!reason) return;
    await apiFetch(`/api/admin/orders/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ admin_note: reason }),
    });
    await loadDashboard(days);
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
      await loadDashboard(days);
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
      await loadDashboard(days);
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
      await loadDashboard(days);
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
      await loadDashboard(days);
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
    await loadDashboard(days);
    setMessage("失败邮件已重新加入发送队列。");
  }

  async function unpublishUpdateNotice(id: number) {
    await apiFetch(`/api/admin/update-notices/${id}/unpublish`, { method: "POST" });
    await loadDashboard(days);
  }

  const filteredOrders = useMemo(
    () => (data?.orders || []).filter((item) => orderFilter === "all" || item.status === orderFilter),
    [data, orderFilter],
  );
  const filteredFeedback = useMemo(
    () => (data?.feedback || []).filter((item) => feedbackFilter === "all" || item.status === feedbackFilter),
    [data, feedbackFilter],
  );
  const pendingMembershipOrders = (data?.orders || []).filter((item) => item.product_type === "membership" && item.status === "submitted");
  const pendingFeedback = (data?.feedback || []).filter((item) => item.status === "pending");
  const failedEmailTasks = (data?.update_notices || []).filter((item) => (item.email_campaign?.failed || 0) > 0);
  const analytics = useMemo(() => (data ? normalizeDashboardAnalytics(data) : null), [data]);

  if (!loading && user?.role !== "admin") {
    return (
      <main className="admin-page">
        <section className="admin-locked">
          <h1>管理员面板</h1>
          <p>当前登录账号没有运营管理权限。</p>
          <Link href="/">返回网站</Link>
        </section>
      </main>
    );
  }

  return (
    <main className="admin-page">
      <div className="admin-layout">
        <aside className="admin-sidebar">
          <Link className="admin-sidebar-brand" href="/">盈航运营台</Link>
          <AdminNavigation active={section} onChange={changeSection} />
        </aside>
      <section className="admin-shell">
        <header className="admin-topbar">
          <div>
            <h1>{adminSections.find((item) => item.key === section)?.label || "运营管理台"}</h1>
          </div>
          <div className="admin-actions">
            <button type="button" onClick={() => void loadDashboard(days)}>
              <RefreshCw />
              刷新
            </button>
            <Link href="/"><ExternalLink />返回网站</Link>
            <button
              type="button"
              onClick={() => {
                clearAuth();
                setUser(null);
                router.push("/admin/login");
              }}
            >
              <LogOut />
              退出
            </button>
          </div>
        </header>

        <div className="admin-analytics-window" aria-label="数据统计周期">
          <span>统计周期</span>
          {[7, 30, 90].map((value) => (
            <button key={value} type="button" className={days === value ? "active" : ""} onClick={() => changeDays(value)} disabled={loading}>
              {value} 天
            </button>
          ))}
        </div>

        <div className="admin-mobile-section-switcher"><AdminNavigation active={section} onChange={changeSection} /></div>

        {message && <div className="admin-alert">{message}</div>}
        {loading && <div className="admin-alert">正在读取统计数据...</div>}

        {data && (
          <>
            <AdminOverviewSection active={section === "overview"} totals={data.totals} featureUsage={analytics!.featureUsage} userGrowth={analytics!.userGrowth} days={days} pendingOrders={pendingMembershipOrders.length} pendingFeedback={pendingFeedback.length} failedEmails={failedEmailTasks.length} onNavigate={changeSection} featureLabel={featureLabel} />

            <AdminUsersSection
              active={section === "users"}
              bulkDraft={bulkGrantDraft}
              onBulkDraftChange={(patch) => setBulkGrantDraft((current) => ({ ...current, ...patch }))}
              onRequestBulkGrant={requestBulkGrantConfirmation}
              campaigns={data.credit_grant_campaigns || []}
              users={data.top_users}
              highFrequencyUsers={analytics!.highFrequencyUsers}
              days={days}
              grantDrafts={grantDrafts}
              onGrantDraftChange={updateGrantDraft}
              onGrantCredits={grantCredits}
            />
            <AdminFeedbackSection active={section === "feedback"} filter={feedbackFilter} onFilterChange={setFeedbackFilter} items={filteredFeedback} onRewardRequest={setFeedbackRewardIntent} />
            <AdminOrdersSection active={section === "orders"} filter={orderFilter} onFilterChange={setOrderFilter} items={filteredOrders} onConfirmMembership={confirmMembership} onRejectMembership={rejectMembership} onMarkPaid={markPaid} />
            <AdminUpdatesSection
              active={section === "updates"}
              draft={noticeDraft}
              editingNoticeId={editingNoticeId}
              onDraftChange={(patch) => setNoticeDraft((current) => ({ ...current, ...patch }))}
              onSave={saveUpdateNotice}
              onRequestFormPublish={() => setPublishIntent({ source: "form", noticeId: editingNoticeId })}
              onCancelEdit={() => { setEditingNoticeId(null); setNoticeDraft(emptyNoticeDraft); }}
              notices={data.update_notices || []}
              onRetryCampaign={retryEmailCampaign}
              onEdit={editUpdateNotice}
              onUnpublish={unpublishUpdateNotice}
              onPublish={publishUpdateNotice}
            />
          </>
        )}
      </section>
      </div>
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
      {feedbackRewardIntent !== null && (
        <div className="admin-publish-backdrop" role="presentation" onMouseDown={() => setFeedbackRewardIntent(null)}>
          <section className="admin-publish-dialog" role="dialog" aria-modal="true" aria-labelledby="feedback-reward-dialog-title" ref={activeDialogRef} tabIndex={-1} onMouseDown={(event) => event.stopPropagation()}>
            <MessageSquare />
            <h2 id="feedback-reward-dialog-title">确认采纳反馈并奖励？</h2>
            <p>确认后将把反馈标记为已采纳，并给该用户增加 10 次使用机会。</p>
            <div>
              <button type="button" onClick={() => acceptFeedback(feedbackRewardIntent)}>确认采纳并奖励</button>
              <button type="button" onClick={() => setFeedbackRewardIntent(null)}>取消</button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}

function isAdminSection(value: string | null): value is AdminSection {
  return adminSections.some((item) => item.key === value);
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

function parseAnalyticsDays(value: string | null) {
  const days = Number(value);
  return days === 7 || days === 90 ? days : 30;
}

function normalizeDashboardAnalytics(data: DashboardPayload): {
  featureUsage: { totals: FeatureUsageTotal[]; byDay: FeatureUsagePoint[] };
  userGrowth: { startingUsers: number; totalUsers: number; byDay: UserGrowthPoint[] };
  highFrequencyUsers: HighFrequencyUser[];
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
  const analyticsHighFrequencyUsers = (data.analytics?.high_frequency_users || []).map((item) => ({
    id: Number(item.id || 0),
    phone: item.phone,
    username: item.username,
    email: item.email,
    total_uses: Number(item.total_uses || 0),
    credits_spent: Number(item.credits_spent || 0),
    active_days: Number(item.active_days || 0),
    usage_by_day: (item.usage_by_day || []).map((point) => ({ day: point.day, count: Number(point.count || 0), credits: Number(point.credits || 0) })),
  })).filter((item) => item.id > 0);
  const highFrequencyUsers = analyticsHighFrequencyUsers.length ? analyticsHighFrequencyUsers : data.top_users.map((item) => ({
    id: item.id,
    phone: item.phone,
    username: item.username,
    email: item.email,
    total_uses: Number(item.used_count || 0),
    credits_spent: 0,
    active_days: 0,
    usage_by_day: [],
  }));
  return {
    featureUsage: { totals: featureTotals, byDay: featureByDay },
    userGrowth: {
      startingUsers,
      totalUsers: Number(data.analytics?.user_growth?.total_users ?? data.totals.users),
      byDay: userGrowth,
    },
    highFrequencyUsers,
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

