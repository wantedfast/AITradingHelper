import { CheckCircle2, CreditCard, Gift, Megaphone, MessageSquare, Users } from "lucide-react";
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
  used_count: number;
  credits: number;
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

type NoticeDraft = { title: string; version: string; itemsText: string };

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
  grantDrafts,
  onGrantDraftChange,
  onGrantCredits,
}: {
  active: boolean;
  bulkDraft: GrantDraft;
  onBulkDraftChange: (patch: Partial<GrantDraft>) => void;
  onRequestBulkGrant: () => void;
  campaigns: CreditGrantCampaign[];
  users: AdminUser[];
  grantDrafts: Record<number, GrantDraft>;
  onGrantDraftChange: (userId: number, patch: Partial<GrantDraft>) => void;
  onGrantCredits: (userId: number) => void;
}) {
  return (
    <section className={`${sectionClass("users", active)} admin-section-stack`}>
      <section className="admin-panel admin-bulk-credit-panel">
        <div className="admin-panel-head"><Gift /><h2>给所有现有用户增加次数</h2></div>
        <p>仅包含确认发放时已经注册的账号。整批在一个事务中完成，失败不会只发给部分用户。</p>
        <div className="admin-bulk-credit-form">
          <label>
            每人增加次数
            <input type="number" min="1" max="10000" step="1" value={bulkDraft.credits} onChange={(event) => onBulkDraftChange({ credits: event.target.value })} />
          </label>
          <label>
            发放原因
            <input maxLength={300} value={bulkDraft.reason} onChange={(event) => onBulkDraftChange({ reason: event.target.value })} placeholder="例如：平台更新福利" />
          </label>
          <button type="button" onClick={onRequestBulkGrant}>确认发放范围</button>
        </div>
        {!!campaigns.length && (
          <div className="admin-bulk-credit-history">
            <b>最近发放记录</b>
            {campaigns.slice(0, 5).map((campaign) => (
              <span key={campaign.id}>{formatDate(campaign.completed_at || campaign.created_at)} · {campaign.granted_count} 人 × {campaign.credits} 次 · {campaign.reason}</span>
            ))}
          </div>
        )}
      </section>

      <section className="admin-grid">
        <article className="admin-panel">
          <div className="admin-panel-head"><Users /><h2>高频用户</h2></div>
          <div className="admin-table">
            {users.map((item) => (
              <div key={item.id}>
                <span>{item.username || item.email || item.phone}</span>
                <b>{item.used_count} 次使用</b>
                <em>{item.role === "admin" ? "无限免扣" : `${item.credits} 次余额`}</em>
                {item.role !== "admin" && (
                  <div className="admin-credit-grant">
                    <input type="number" min="1" step="1" value={grantDrafts[item.id]?.credits || ""} onChange={(event) => onGrantDraftChange(item.id, { credits: event.target.value })} placeholder="增加次数" />
                    <input value={grantDrafts[item.id]?.reason || ""} onChange={(event) => onGrantDraftChange(item.id, { reason: event.target.value })} placeholder="增加原因，会写入邮件" />
                    <button type="button" onClick={() => onGrantCredits(item.id)}>增加并邮件提醒</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </article>
      </section>
    </section>
  );
}

export function AdminFeedbackSection({ active, filter, onFilterChange, items, onRewardRequest }: {
  active: boolean;
  filter: string;
  onFilterChange: (value: string) => void;
  items: FeedbackItem[];
  onRewardRequest: (id: number) => void;
}) {
  return (
    <section className="admin-grid">
      <article className={`admin-panel ${sectionClass("feedback", active)}`}>
        <div className="admin-panel-head"><MessageSquare /><h2>反馈建议</h2></div>
        <AdminStatusFilters value={filter} onChange={onFilterChange} options={["all", "pending", "accepted"]} />
        <div className="admin-list">
          {items.map((item) => (
            <div className="admin-list-item" key={item.id}>
              <header><b>{item.category}</b><span>{adminStatusLabel(item.status)}</span></header>
              <p>{item.content}</p>
              <small>{item.phone} · {formatDate(item.created_at)}</small>
              {item.status === "pending" && <button type="button" onClick={() => onRewardRequest(item.id)}><CheckCircle2 />采纳并奖励 10 次</button>}
            </div>
          ))}
          {!items.length ? <div className="admin-filter-empty">当前筛选条件下暂无反馈。</div> : null}
        </div>
      </article>
    </section>
  );
}

export function AdminOrdersSection({ active, filter, onFilterChange, items, onConfirmMembership, onRejectMembership, onMarkPaid }: {
  active: boolean;
  filter: string;
  onFilterChange: (value: string) => void;
  items: OrderItem[];
  onConfirmMembership: (id: number) => void;
  onRejectMembership: (id: number) => void;
  onMarkPaid: (id: number) => void;
}) {
  return (
    <section className="admin-grid">
      <article className={`admin-panel ${sectionClass("orders", active)}`}>
        <div className="admin-panel-head"><CreditCard /><h2>订单系统</h2></div>
        <AdminStatusFilters value={filter} onChange={onFilterChange} options={["all", "pending", "submitted", "paid", "rejected"]} />
        <div className="admin-order-table-head" aria-hidden="true"><span>套餐与状态</span><span>金额</span><span>用户与订单</span><span>付款信息</span><span>操作</span></div>
        <div className="admin-list admin-order-table">
          {items.map((item) => (
            <div className="admin-list-item" key={item.id}>
              <header><b>{item.plan_name}</b><span>{orderStatusLabel(item.status)}</span></header>
              <p>{item.product_type === "membership" ? `会员订阅 · ${item.plan_name}` : `${item.credits} 次`} · ¥{(item.amount_cents / 100).toFixed(2)}</p>
              <small>{item.username || item.email || item.phone} · {item.order_no}</small>
              {item.product_type === "membership" && (
                <p>{paymentMethodLabel(item.payment_method || "")}{item.payer_name ? ` · ${item.payer_name}` : ""}{item.payer_paid_at ? ` · ${item.payer_paid_at}` : ""}{item.submitted_amount_cents ? ` · ¥${(item.submitted_amount_cents / 100).toFixed(2)}` : ""}{item.payer_note ? ` · ${item.payer_note}` : ""}</p>
              )}
              {item.admin_note ? <small>备注：{item.admin_note}</small> : null}
              {item.product_type === "membership" && item.status === "submitted" && (
                <><button type="button" onClick={() => onConfirmMembership(item.id)}><CheckCircle2 />确认到账并开通会员</button><button type="button" onClick={() => onRejectMembership(item.id)}>标记异常</button></>
              )}
              {item.product_type !== "membership" && item.status !== "paid" && <button type="button" onClick={() => onMarkPaid(item.id)}><CheckCircle2 />标记已支付</button>}
            </div>
          ))}
          {!items.length ? <div className="admin-filter-empty">当前筛选条件下暂无订单。</div> : null}
        </div>
      </article>
    </section>
  );
}

export function AdminUpdatesSection({ active, draft, editingNoticeId, onDraftChange, onSave, onRequestFormPublish, onCancelEdit, notices, onRetryCampaign, onEdit, onUnpublish, onPublish }: {
  active: boolean;
  draft: NoticeDraft;
  editingNoticeId: number | null;
  onDraftChange: (patch: Partial<NoticeDraft>) => void;
  onSave: () => void;
  onRequestFormPublish: () => void;
  onCancelEdit: () => void;
  notices: UpdateNotice[];
  onRetryCampaign: (id: number) => void;
  onEdit: (notice: UpdateNotice) => void;
  onUnpublish: (id: number) => void;
  onPublish: (id: number) => void;
}) {
  const className = `admin-panel ${sectionClass("updates", active)}`;
  return (
    <section className="admin-grid">
      <article className={className}>
        <div className="admin-panel-head"><Megaphone /><h2>更新公告</h2></div>
        <div className="admin-notice-form">
          <input value={draft.title} onChange={(event) => onDraftChange({ title: event.target.value })} placeholder="公告标题，例如：本周更新" />
          <input type="date" value={draft.version} onChange={(event) => onDraftChange({ version: event.target.value })} aria-label="公告日期" />
          <textarea value={draft.itemsText} onChange={(event) => onDraftChange({ itemsText: event.target.value })} placeholder="每行一条更新内容" rows={5} />
          <div className="admin-notice-actions">
            <button type="button" onClick={onSave}>{editingNoticeId ? "保存修改" : "保存草稿"}</button>
            <button type="button" onClick={onRequestFormPublish}>保存并发布</button>
            {editingNoticeId && <button type="button" onClick={onCancelEdit}>取消编辑</button>}
          </div>
        </div>
      </article>

      <article className={className}>
        <div className="admin-panel-head"><Megaphone /><h2>公告列表</h2></div>
        <div className="admin-list">
          {notices.map((notice) => (
            <div className="admin-list-item" key={notice.id}>
              <header><b>{notice.title}</b><span>{notice.status === "published" ? "已发布" : "草稿"}</span></header>
              <p>{notice.version} · {formatDate(notice.published_at || notice.updated_at)}</p>
              <small>{notice.items.join(" / ")}</small>
              {notice.email_campaign && (
                <div className="admin-email-campaign">
                  <b>邮件：{emailCampaignLabel(notice.email_campaign.status)}</b>
                  <span>成功 {notice.email_campaign.sent} · 待发送 {notice.email_campaign.pending + notice.email_campaign.sending} · 失败 {notice.email_campaign.failed} · 跳过 {notice.email_campaign.skipped}</span>
                  {notice.email_campaign.failed > 0 && <button type="button" onClick={() => onRetryCampaign(notice.email_campaign!.id)}>重试失败邮件</button>}
                </div>
              )}
              <button type="button" onClick={() => onEdit(notice)}>编辑</button>
              {notice.status === "published" ? <button type="button" onClick={() => onUnpublish(notice.id)}>下线</button> : <button type="button" onClick={() => onPublish(notice.id)}>发布</button>}
            </div>
          ))}
          {!notices.length && <p>暂无更新公告。</p>}
        </div>
      </article>
    </section>
  );
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
