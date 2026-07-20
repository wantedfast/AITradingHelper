"use client";

import type { EChartsOption } from "echarts";
import { Activity, CheckCircle2, CreditCard, Gift, Megaphone, MessageSquare, PauseCircle, PlayCircle, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AdminAnalyticsChart } from "@/components/admin/admin-analytics-chart";
import type { HighFrequencyUser } from "@/components/admin/admin-analytics-types";
import { AdminStatusFilters, adminStatusLabel } from "@/components/admin/admin-navigation";

type GrantDraft = { credits: string; reason: string };

type CreditGrantCampaign = {
  id: number;
  credits: number;
  reason: string;
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

type FeedbackItem = {
  id: number;
  phone: string;
  category: string;
  content: string;
  status: string;
  created_at: string;
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

type DailyTop5EmailCampaign = EmailCampaign & {
  trade_date: string;
  report_id: string;
  full: number;
  teaser: number;
  created_at: string;
  finished_at?: string | null;
};

type UpdateNotice = {
  id: number;
  title: string;
  version: string;
  items: string[];
  summary?: string;
  content_markdown?: string;
  expires_at?: string | null;
  status: "draft" | "published" | "archived";
  created_at: string;
  updated_at: string;
  published_at?: string | null;
  email_campaign?: EmailCampaign | null;
};

type NoticeDraft = {
  title: string;
  version: string;
  summary: string;
  contentMarkdown: string;
  expiresAt: string;
  itemsText: string;
};

function sectionClass(section: "users" | "feedback" | "orders" | "updates", active: boolean) {
  return `admin-section admin-section--${section}${active ? " is-active" : ""}`;
}

export function AdminUsersSection({
  active,
  bulkDraft,
  onBulkDraftChange,
  onRequestBulkGrant,
  campaigns,
  users,
  highFrequencyUsers,
  days,
  grantDrafts,
  onGrantDraftChange,
  onGrantCredits,
  onToggleUserStatus,
}: {
  active: boolean;
  bulkDraft: GrantDraft;
  onBulkDraftChange: (patch: Partial<GrantDraft>) => void;
  onRequestBulkGrant: () => void;
  campaigns: CreditGrantCampaign[];
  users: AdminUser[];
  highFrequencyUsers: HighFrequencyUser[];
  days: number;
  grantDrafts: Record<number, GrantDraft>;
  onGrantDraftChange: (userId: number, patch: Partial<GrantDraft>) => void;
  onGrantCredits: (userId: number) => void;
  onToggleUserStatus: (userId: number, nextStatus: "active" | "disabled") => void;
}) {
  return (
    <section className={`${sectionClass("users", active)} admin-section-stack`}>
      <section className="admin-panel admin-bulk-credit-panel">
        <div className="admin-panel-head">
          <Gift />
          <h2>给所有现有用户增加次数</h2>
        </div>
        <p>只覆盖发放时已经注册的账号。整批操作在同一事务里完成，不会只发到部分用户。</p>
        <div className="admin-bulk-credit-form">
          <label>
            每人增加次数
            <input
              type="number"
              min="1"
              max="10000"
              step="1"
              value={bulkDraft.credits}
              onChange={(event) => onBulkDraftChange({ credits: event.target.value })}
            />
          </label>
          <label>
            发放原因
            <input
              maxLength={300}
              value={bulkDraft.reason}
              onChange={(event) => onBulkDraftChange({ reason: event.target.value })}
              placeholder="例如：平台更新福利"
            />
          </label>
          <button type="button" onClick={onRequestBulkGrant}>确认发放范围</button>
        </div>
        {!!campaigns.length && (
          <div className="admin-bulk-credit-history">
            <b>最近发放记录</b>
            {campaigns.slice(0, 5).map((campaign) => (
              <span key={campaign.id}>
                {formatDate(campaign.completed_at || campaign.created_at)} · {campaign.granted_count} 人 × {campaign.credits} 次 · {campaign.reason}
              </span>
            ))}
          </div>
        )}
      </section>

      <HighFrequencyAnalytics users={highFrequencyUsers} days={days} />

      <section className="admin-grid admin-grid--single">
        <article className="admin-panel">
          <div className="admin-panel-head">
            <Users />
            <h2>用户次数与状态</h2>
          </div>
          <div className="admin-table">
            {users.map((item) => {
              const draft = grantDrafts[item.id] || { credits: "", reason: "" };
              const isAdmin = item.role === "admin";
              const nextStatus = item.status === "disabled" ? "active" : "disabled";
              return (
                <div key={item.id} className="admin-user-card">
                  <div className="admin-user-main">
                    <span>{displayUserName(item)}</span>
                    <div className="admin-user-meta">
                      <b>{item.used_count} 次使用</b>
                      <em>{isAdmin ? "管理员免扣" : `${item.credits} 次余额`}</em>
                      <strong className={`admin-user-status admin-user-status--${item.status === "disabled" ? "disabled" : "active"}`}>
                        {item.status === "disabled" ? "已暂停" : "正常"}
                      </strong>
                    </div>
                    <small>
                      {item.phone}
                      {item.created_at ? ` · 注册 ${formatDate(item.created_at)}` : ""}
                      {item.last_login_at ? ` · 最近登录 ${formatDate(item.last_login_at)}` : ""}
                    </small>
                  </div>
                  {!isAdmin ? (
                    <div className="admin-credit-grant">
                      <input
                        type="number"
                        step="1"
                        value={draft.credits}
                        onChange={(event) => onGrantDraftChange(item.id, { credits: event.target.value })}
                        placeholder="正数增加，负数扣减"
                        aria-label={`调整 ${displayUserName(item)} 次数`}
                      />
                      <input
                        value={draft.reason}
                        onChange={(event) => onGrantDraftChange(item.id, { reason: event.target.value })}
                        placeholder="填写调整原因，会写入台账"
                        aria-label={`填写 ${displayUserName(item)} 次数调整原因`}
                      />
                      <div className="admin-credit-actions">
                        <button type="button" onClick={() => onGrantCredits(item.id)}>
                          调整次数
                        </button>
                        <button
                          type="button"
                          className="admin-secondary-button"
                          onClick={() => onToggleUserStatus(item.id, nextStatus)}
                        >
                          {nextStatus === "disabled" ? <PauseCircle /> : <PlayCircle />}
                          {nextStatus === "disabled" ? "暂停账号" : "恢复账号"}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <small>管理员账号不允许通过这里调整次数或状态。</small>
                  )}
                </div>
              );
            })}
          </div>
        </article>
      </section>
    </section>
  );
}

function HighFrequencyAnalytics({ users, days }: { users: HighFrequencyUser[]; days: number }) {
  const topUsers = useMemo(() => users.slice(0, 5), [users]);
  const [selectedId, setSelectedId] = useState<number | null>(topUsers[0]?.id ?? null);

  useEffect(() => {
    if (!topUsers.some((item) => item.id === selectedId)) setSelectedId(topUsers[0]?.id ?? null);
  }, [selectedId, topUsers]);

  const selected = topUsers.find((item) => item.id === selectedId) || topUsers[0];
  const displayNames = useMemo(() => buildUserDisplayNames(topUsers), [topUsers]);
  const option = useMemo(() => buildHighFrequencyOption(topUsers, displayNames), [displayNames, topUsers]);

  return (
    <section className="admin-panel admin-analytics-panel admin-high-frequency-panel">
      <div className="admin-panel-head admin-analytics-heading">
        <Activity />
        <div>
          <h2>高频用户趋势</h2>
          <p>近 {days} 天使用最多的 5 位用户，可点击图例或用户标签查看个人摘要。</p>
        </div>
      </div>
      <AdminAnalyticsChart
        option={option}
        ariaLabel={`近 ${days} 天高频用户每日使用次数折线图`}
        empty={!topUsers.length || !topUsers.some((item) => item.usage_by_day.length) ? "这段时间还没有可展示的用户使用曲线。" : undefined}
        className="admin-echart--users"
        onLegendSelect={(name) => {
          const match = topUsers.find((item) => displayNames.get(item.id) === name);
          if (match) setSelectedId(match.id);
        }}
      />
      {!!topUsers.length && (
        <>
          <div className="admin-user-series-selector" aria-label="选择高频用户">
            {topUsers.map((item, index) => (
              <button
                key={item.id}
                type="button"
                className={item.id === selected?.id ? "active" : ""}
                onClick={() => setSelectedId(item.id)}
              >
                <i style={{ background: analyticsColors[index % analyticsColors.length] }} />
                <span>{userLabel(item)}</span>
              </button>
            ))}
          </div>
          {selected && (
            <div className="admin-user-usage-summary" aria-label={`${userLabel(selected)} 使用摘要`}>
              <article>
                <span>总使用次数</span>
                <b>{selected.total_uses.toLocaleString()}</b>
              </article>
              <article>
                <span>活跃天数</span>
                <b>{selected.active_days.toLocaleString()}</b>
              </article>
              <article>
                <span>消耗次数</span>
                <b>{selected.credits_spent.toLocaleString()}</b>
              </article>
            </div>
          )}
        </>
      )}
    </section>
  );
}

const analyticsColors = ["#f5d77a", "#55d6a8", "#79a9ff", "#f39a72", "#c897e8"];

function buildHighFrequencyOption(users: HighFrequencyUser[], displayNames: Map<number, string>): EChartsOption {
  const days = Array.from(new Set(users.flatMap((user) => user.usage_by_day.map((point) => point.day)))).sort();
  return {
    color: analyticsColors,
    animationDuration: 450,
    textStyle: { color: "#aab1ad", fontFamily: "Inter, Microsoft YaHei, sans-serif" },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(7,10,9,.96)",
      borderColor: "rgba(245,215,122,.25)",
      textStyle: { color: "#f4f0e8" },
    },
    legend: {
      top: 0,
      type: "scroll",
      data: users.map((item) => displayNames.get(item.id) || userLabel(item)),
      textStyle: { color: "#aab1ad" },
      pageTextStyle: { color: "#aab1ad" },
    },
    grid: { top: 52, right: 24, bottom: 28, left: 50 },
    xAxis: {
      type: "category",
      data: days.map((day) => day.slice(5)),
      boundaryGap: false,
      axisLine: { lineStyle: { color: "rgba(244,240,232,.15)" } },
      axisLabel: { color: "#89918c", hideOverlap: true },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      minInterval: 1,
      name: "使用次数",
      axisLabel: { color: "#89918c" },
      nameTextStyle: { color: "#727b75" },
      splitLine: { lineStyle: { color: "rgba(244,240,232,.07)" } },
    },
    series: users.map((user, index) => ({
      name: displayNames.get(user.id) || userLabel(user),
      type: "line",
      data: days.map((day) => user.usage_by_day.find((item) => item.day === day)?.count || 0),
      smooth: days.length > 2 ? 0.25 : false,
      symbol: days.length === 1 ? "circle" : "none",
      symbolSize: 8,
      lineStyle: { width: 2, color: analyticsColors[index % analyticsColors.length] },
      itemStyle: { color: analyticsColors[index % analyticsColors.length] },
      emphasis: { focus: "series" },
    })),
  };
}

function buildUserDisplayNames(users: HighFrequencyUser[]) {
  const labels = users.map(userLabel);
  return new Map(
    users.map((item, index) => [
      item.id,
      labels.filter((label) => label === labels[index]).length > 1 ? `${labels[index]} · #${item.id}` : labels[index],
    ]),
  );
}

function userLabel(user: HighFrequencyUser) {
  return user.username || user.email || user.phone || `用户 #${user.id}`;
}

function displayUserName(user: AdminUser) {
  return user.username || user.email || user.phone || `用户 #${user.id}`;
}

export function AdminFeedbackSection({
  active,
  filter,
  onFilterChange,
  items,
  onRewardRequest,
}: {
  active: boolean;
  filter: string;
  onFilterChange: (value: string) => void;
  items: FeedbackItem[];
  onRewardRequest: (id: number) => void;
}) {
  return (
    <section className="admin-grid">
      <article className={`admin-panel ${sectionClass("feedback", active)}`}>
        <div className="admin-panel-head">
          <MessageSquare />
          <h2>反馈建议</h2>
        </div>
        <AdminStatusFilters value={filter} onChange={onFilterChange} options={["all", "pending", "accepted"]} />
        <div className="admin-list">
          {items.map((item) => (
            <div className="admin-list-item" key={item.id}>
              <header>
                <b>{item.category}</b>
                <span>{adminStatusLabel(item.status)}</span>
              </header>
              <p>{item.content}</p>
              <small>{item.phone} · {formatDate(item.created_at)}</small>
              {item.status === "pending" && (
                <button type="button" onClick={() => onRewardRequest(item.id)}>
                  <CheckCircle2 />
                  采纳并奖励 10 次
                </button>
              )}
            </div>
          ))}
          {!items.length ? <div className="admin-filter-empty">当前筛选条件下暂无反馈。</div> : null}
        </div>
      </article>
    </section>
  );
}

export function AdminOrdersSection({
  active,
  filter,
  onFilterChange,
  items,
  onConfirmMembership,
  onRejectMembership,
  onConfirmCredits,
  onRejectCredits,
  onMarkPaid,
}: {
  active: boolean;
  filter: string;
  onFilterChange: (value: string) => void;
  items: OrderItem[];
  onConfirmMembership: (id: number) => void;
  onRejectMembership: (id: number) => void;
  onConfirmCredits: (id: number) => void;
  onRejectCredits: (id: number) => void;
  onMarkPaid: (id: number) => void;
}) {
  return (
    <section className="admin-grid">
      <article className={`admin-panel ${sectionClass("orders", active)}`}>
        <div className="admin-panel-head">
          <CreditCard />
          <h2>订单处理</h2>
        </div>
        <AdminStatusFilters value={filter} onChange={onFilterChange} options={["all", "pending", "submitted", "paid", "rejected"]} />
        <div className="admin-order-table-head" aria-hidden="true">
          <span>商品与状态</span>
          <span>金额</span>
          <span>用户与订单</span>
          <span>付款信息</span>
          <span>操作</span>
        </div>
        <div className="admin-list admin-order-table">
          {items.map((item) => (
            <div className="admin-list-item" key={item.id}>
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
                    <button type="button" onClick={() => onConfirmMembership(item.id)}>
                      <CheckCircle2 />
                      确认到账并开通会员
                    </button>
                    <button type="button" className="admin-secondary-button" onClick={() => onRejectMembership(item.id)}>
                      标记异常
                    </button>
                  </>
                ) : null}
                {item.product_type === "credits" && item.status === "submitted" ? (
                  <>
                    <button type="button" onClick={() => onConfirmCredits(item.id)}>
                      <CheckCircle2 />
                      确认到账并增加次数
                    </button>
                    <button type="button" className="admin-secondary-button" onClick={() => onRejectCredits(item.id)}>
                      驳回本次提交
                    </button>
                  </>
                ) : null}
                {item.product_type !== "membership" && item.product_type !== "credits" && item.status !== "paid" ? (
                  <button type="button" onClick={() => onMarkPaid(item.id)}>
                    <CheckCircle2 />
                    标记已支付
                  </button>
                ) : null}
              </div>
            </div>
          ))}
          {!items.length ? <div className="admin-filter-empty">当前筛选条件下暂无订单。</div> : null}
        </div>
      </article>
    </section>
  );
}

export function AdminUpdatesSection({
  active,
  draft,
  editingNoticeId,
  onDraftChange,
  onSave,
  onRequestFormPublish,
  onCancelEdit,
  notices,
  dailyTop5Campaigns,
  onRetryCampaign,
  onRetryDailyTop5Campaign,
  onEdit,
  onUnpublish,
  onPublish,
}: {
  active: boolean;
  draft: NoticeDraft;
  editingNoticeId: number | null;
  onDraftChange: (patch: Partial<NoticeDraft>) => void;
  onSave: () => void;
  onRequestFormPublish: () => void;
  onCancelEdit: () => void;
  notices: UpdateNotice[];
  dailyTop5Campaigns: DailyTop5EmailCampaign[];
  onRetryCampaign: (id: number) => void;
  onRetryDailyTop5Campaign: (id: number) => void;
  onEdit: (notice: UpdateNotice) => void;
  onUnpublish: (id: number) => void;
  onPublish: (id: number) => void;
}) {
  const className = `admin-panel ${sectionClass("updates", active)}`;
  return (
    <section className="admin-grid">
      <article className={className}>
        <div className="admin-panel-head">
          <Megaphone />
          <h2>每日 TOP5 邮件推送</h2>
        </div>
        <p>完整报告上线后自动创建任务；同一交易日只推送一次，失败不会影响网站报告上线。</p>
        <div className="admin-list">
          {dailyTop5Campaigns.map((campaign) => (
            <div className="admin-list-item" key={campaign.id}>
              <header>
                <b>{campaign.trade_date} · 每日 TOP5</b>
                <span>{emailCampaignLabel(campaign.status)}</span>
              </header>
              <p>{formatDate(campaign.created_at)}</p>
              <div className="admin-email-campaign">
                <span>会员完整版 {campaign.full} · 普通用户摘要版 {campaign.teaser}</span>
                <span>成功 {campaign.sent} · 待发送 {campaign.pending + campaign.sending} · 失败 {campaign.failed} · 跳过 {campaign.skipped}</span>
                {campaign.failed > 0 && (
                  <button type="button" onClick={() => onRetryDailyTop5Campaign(campaign.id)}>
                    重试失败邮件
                  </button>
                )}
              </div>
            </div>
          ))}
          {!dailyTop5Campaigns.length && <p>暂时还没有每日 TOP5 邮件任务。</p>}
        </div>
      </article>

      <article className={className}>
        <div className="admin-panel-head">
          <Megaphone />
          <h2>更新公告</h2>
        </div>
        <div className="admin-notice-form">
          <input value={draft.title} onChange={(event) => onDraftChange({ title: event.target.value })} placeholder="公告标题，例如：本周更新" />
          <input type="date" value={draft.version} onChange={(event) => onDraftChange({ version: event.target.value })} aria-label="公告日期" />
          <input value={draft.summary} onChange={(event) => onDraftChange({ summary: event.target.value })} placeholder="公告摘要（最多 240 字）" />
          <textarea
            value={draft.contentMarkdown}
            onChange={(event) => onDraftChange({ contentMarkdown: event.target.value })}
            placeholder="公告正文（支持安全 Markdown 文本，不执行 HTML）"
            rows={7}
          />
          <label>
            <span>到期时间（可选）</span>
            <input type="datetime-local" value={draft.expiresAt} onChange={(event) => onDraftChange({ expiresAt: event.target.value })} />
          </label>
          <textarea value={draft.itemsText} onChange={(event) => onDraftChange({ itemsText: event.target.value })} placeholder="每行一条更新内容" rows={5} />
          <div className="admin-notice-actions">
            <button type="button" onClick={onSave}>{editingNoticeId ? "保存修改" : "保存草稿"}</button>
            <button type="button" onClick={onRequestFormPublish}>保存并发布</button>
            {editingNoticeId && <button type="button" onClick={onCancelEdit}>取消编辑</button>}
          </div>
        </div>
      </article>

      <article className={className}>
        <div className="admin-panel-head">
          <Megaphone />
          <h2>公告列表</h2>
        </div>
        <div className="admin-list">
          {notices.map((notice) => (
            <div className="admin-list-item" key={notice.id}>
              <header>
                <b>{notice.title}</b>
                <span>{notice.status === "published" ? "已发布" : notice.status === "archived" ? "已归档" : "草稿"}</span>
              </header>
              <p>{notice.version} · {formatDate(notice.published_at || notice.updated_at)}</p>
              {notice.summary ? <p>{notice.summary}</p> : null}
              <small>{notice.items.join(" / ")}</small>
              {notice.email_campaign && (
                <div className="admin-email-campaign">
                  <b>邮件：{emailCampaignLabel(notice.email_campaign.status)}</b>
                  <span>成功 {notice.email_campaign.sent} · 待发送 {notice.email_campaign.pending + notice.email_campaign.sending} · 失败 {notice.email_campaign.failed} · 跳过 {notice.email_campaign.skipped}</span>
                  {notice.email_campaign.failed > 0 && (
                    <button type="button" onClick={() => onRetryCampaign(notice.email_campaign!.id)}>
                      重试失败邮件
                    </button>
                  )}
                </div>
              )}
              <div className="admin-notice-item-actions">
                <button type="button" onClick={() => onEdit(notice)}>编辑</button>
                {notice.status === "published" ? (
                  <button type="button" onClick={() => onUnpublish(notice.id)}>下线</button>
                ) : notice.status === "draft" ? (
                  <button type="button" onClick={() => onPublish(notice.id)}>发布</button>
                ) : null}
              </div>
            </div>
          ))}
          {!notices.length && <p>暂无更新公告。</p>}
        </div>
      </article>
    </section>
  );
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
