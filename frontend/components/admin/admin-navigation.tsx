import { BarChart3, CreditCard, Megaphone, MessageSquare, Users } from "lucide-react";

export type AdminSection = "overview" | "users" | "orders" | "feedback" | "updates";

export const adminSections: Array<{ key: AdminSection; label: string; icon: typeof BarChart3 }> = [
  { key: "overview", label: "总览", icon: BarChart3 },
  { key: "users", label: "用户与次数", icon: Users },
  { key: "orders", label: "订单处理", icon: CreditCard },
  { key: "feedback", label: "反馈建议", icon: MessageSquare },
  { key: "updates", label: "更新公告", icon: Megaphone },
];

export function AdminNavigation({ active, onChange }: { active: AdminSection; onChange: (section: AdminSection) => void }) {
  return (
    <nav className="admin-section-nav" aria-label="管理台分区">
      {adminSections.map(({ key, label, icon: Icon }) => (
        <button
          key={key}
          type="button"
          aria-current={active === key ? "page" : undefined}
          className={active === key ? "active" : ""}
          onClick={() => onChange(key)}
        >
          <Icon aria-hidden="true" />
          <span>{label}</span>
        </button>
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
  return value;
}
