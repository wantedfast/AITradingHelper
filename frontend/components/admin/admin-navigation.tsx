import Link from "next/link";
import { BarChart3, Boxes, CreditCard, Mail, Megaphone, MessageSquare, Users } from "lucide-react";

export type AdminSection = "overview" | "users" | "orders" | "feedback" | "updates" | "emails" | "stock-research";

export const adminSections: Array<{ key: AdminSection; label: string; icon: typeof BarChart3 }> = [
  { key: "overview", label: "总览", icon: BarChart3 },
  { key: "users", label: "用户与次数", icon: Users },
  { key: "orders", label: "订单处理", icon: CreditCard },
  { key: "feedback", label: "反馈建议", icon: MessageSquare },
  { key: "updates", label: "更新公告", icon: Megaphone },
  { key: "emails", label: "邮件推送", icon: Mail },
  { key: "stock-research", label: "A股研究", icon: Boxes },
];

export function adminSectionPath(section: AdminSection) {
  return `/admin/${section}`;
}

export function isAdminSection(value: string): value is AdminSection {
  return adminSections.some((item) => item.key === value);
}

export function AdminNavigation({ active }: { active: AdminSection }) {
  return (
    <nav className="admin-section-nav" aria-label="管理台分区">
      {adminSections.map(({ key, label, icon: Icon }) => (
        <Link
          key={key}
          aria-current={active === key ? "page" : undefined}
          className={active === key ? "active" : ""}
          href={adminSectionPath(key)}
        >
          <Icon aria-hidden="true" />
          <span>{label}</span>
        </Link>
      ))}
    </nav>
  );
}

export function AdminStatusFilters({ value, onChange, options }: { value: string; onChange: (value: string) => void; options: string[] }) {
  return (
    <div className="admin-status-filters">
      {options.map((option) => (
        <button key={option} type="button" className={value === option ? "active" : ""} onClick={() => onChange(option)}>
          {adminStatusLabel(option)}
        </button>
      ))}
    </div>
  );
}

export function adminStatusLabel(value: string) {
  if (value === "all") return "全部";
  if (value === "pending") return "待处理";
  if (value === "submitted") return "待确认";
  if (value === "paid") return "已完成";
  if (value === "accepted") return "已采纳";
  if (value === "rejected") return "异常";
  if (value === "queued") return "排队中";
  if (value === "running") return "生成中";
  if (value === "completed") return "已完成";
  if (value === "failed") return "生成失败";
  if (value === "timed_out") return "已超时";
  if (value === "payment_required") return "余额不足";
  return value;
}
