import { BarChart3, CreditCard, Gift, MessageSquare, Users } from "lucide-react";
import type { ReactNode } from "react";
import type { AdminSection } from "./admin-navigation";

type OverviewProps = {
  active: boolean;
  totals: { users: number; credits: number; feedback_pending: number; orders_paid: number };
  usage: Array<{ day: string; feature: string; count: number }>;
  newUsers: Array<{ day: string; count: number }>;
  pendingOrders: number;
  pendingFeedback: number;
  failedEmails: number;
  onNavigate: (section: AdminSection) => void;
  featureLabel: (value: string) => string;
};

export function AdminOverviewSection(props: OverviewProps) {
  const usageMax = Math.max(1, ...props.usage.map((item) => item.count));
  const userMax = Math.max(1, ...props.newUsers.map((item) => item.count));
  return (
    <section className={`admin-section admin-section--overview${props.active ? " is-active" : ""}`}>
      <section className="admin-priority-grid">
        <PriorityCard label="待确认会员订单" count={props.pendingOrders} onClick={() => props.onNavigate("orders")} />
        <PriorityCard label="待处理反馈" count={props.pendingFeedback} onClick={() => props.onNavigate("feedback")} />
        <PriorityCard label="失败邮件任务" count={props.failedEmails} onClick={() => props.onNavigate("updates")} />
      </section>
      <section className="admin-metrics">
        <Metric icon={Users} label="普通用户" value={props.totals.users} />
        <Metric icon={Gift} label="系统剩余次数" value={props.totals.credits} />
        <Metric icon={MessageSquare} label="待审核反馈" value={props.totals.feedback_pending} />
        <Metric icon={CreditCard} label="已支付订单" value={props.totals.orders_paid} />
      </section>
      <section className="admin-grid">
        <Trend title="近 14 日功能使用" icon={<BarChart3 />} empty="暂无使用记录。">
          {props.usage.map((item) => <div key={`${item.day}-${item.feature}`}><span>{item.day.slice(5)} · {props.featureLabel(item.feature)}</span><i style={{ width: `${Math.max(8, item.count / usageMax * 100)}%` }} /><b>{item.count}</b></div>)}
        </Trend>
        <Trend title="近 14 日新增用户" icon={<Users />} empty="暂无新增用户。">
          {props.newUsers.map((item) => <div key={item.day}><span>{item.day.slice(5)}</span><i style={{ width: `${Math.max(8, item.count / userMax * 100)}%` }} /><b>{item.count}</b></div>)}
        </Trend>
      </section>
    </section>
  );
}

function PriorityCard({ label, count, onClick }: { label: string; count: number; onClick: () => void }) {
  return <button className={count ? "has-items" : ""} type="button" onClick={onClick}><span>{label}</span><b>{count}</b><small>{count ? "立即处理" : "当前无待办"}</small></button>;
}

function Metric({ icon: Icon, label, value }: { icon: typeof Users; label: string; value: number }) {
  return <article><Icon /><span>{label}</span><b>{value}</b></article>;
}

function Trend({ title, icon, children, empty }: { title: string; icon: ReactNode; children: ReactNode[]; empty: string }) {
  return <article className="admin-panel admin-chart-panel"><div className="admin-panel-head">{icon}<h2>{title}</h2></div><div className="admin-chart">{children.length ? children : <p>{empty}</p>}</div></article>;
}
