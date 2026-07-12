"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { BarChart3, FileText, FileUp, Info, TrendingUp, Trophy } from "lucide-react";

type MainSidebarKey = "review" | "watch" | "market-day" | "ai-research" | "auction-strength";

type MainSidebarProps = {
  activeKey: MainSidebarKey;
  note?: ReactNode;
  hrefOverrides?: Partial<Record<MainSidebarKey, string>>;
};

const navItems: Array<{
  key: MainSidebarKey;
  href: string;
  label: string;
  icon: typeof FileUp;
}> = [
  { key: "review", href: "/review", label: "AI复盘", icon: FileUp },
  { key: "watch", href: "/watch", label: "AI盯盘", icon: BarChart3 },
  { key: "market-day", href: "/market-day", label: "AI当日行情", icon: TrendingUp },
  { key: "ai-research", href: "/ai-research", label: "AI研报", icon: FileText },
  { key: "auction-strength", href: "/auction-strength", label: "竞价强者", icon: Trophy },
];

export function MainSidebar({ activeKey, note, hrefOverrides }: MainSidebarProps) {
  return (
    <aside className="review-workbench-rail">
      <Link className="review-workbench-brand" href="/">
        <span className="brand-mark">盈</span>
        <span>
          <b>盈航</b>
          <small>AI TRADING</small>
        </span>
      </Link>
      <nav className="review-workbench-nav" aria-label="核心功能">
        {navItems.map(({ key, href, label, icon: Icon }) => (
          <Link className={activeKey === key ? "active" : undefined} href={hrefOverrides?.[key] || href} key={key}>
            <Icon />
            <span>
              <b>{label}</b>
            </span>
          </Link>
        ))}
      </nav>
      {note ? (
        <div className="review-rail-note">
          <Info />
          <span>{note}</span>
        </div>
      ) : null}
    </aside>
  );
}
