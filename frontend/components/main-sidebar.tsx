"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { BarChart3, Boxes, FileText, FileUp, Info, TrendingUp, Trophy } from "lucide-react";
import {
  Article as PhArticle,
  ChartBar as PhChartBar,
  FileText as PhFileText,
  Info as PhInfo,
  TrendUp as PhTrendUp,
  Trophy as PhTrophy,
} from "@phosphor-icons/react";

type MainSidebarKey = "review" | "watch" | "market-day" | "ai-research" | "auction-strength" | "stock-research";

type MainSidebarProps = {
  activeKey: MainSidebarKey;
  note?: ReactNode;
  hrefOverrides?: Partial<Record<MainSidebarKey, string>>;
  prototypeIcons?: boolean;
};

const navItems: Array<{
  key: MainSidebarKey;
  href: string;
  label: string;
  shortLabel: string;
  icon: typeof FileUp;
  prototypeIcon: typeof PhArticle;
}> = [
  { key: "auction-strength", href: "/auction-strength", label: "每日 TOP5", shortLabel: "TOP5", icon: Trophy, prototypeIcon: PhTrophy },
  { key: "review", href: "/review", label: "AI 复盘", shortLabel: "复盘", icon: FileUp, prototypeIcon: PhArticle },
  { key: "watch", href: "/watch", label: "AI 盯盘", shortLabel: "盯盘", icon: BarChart3, prototypeIcon: PhChartBar },
  { key: "market-day", href: "/market-day", label: "AI 当日行情", shortLabel: "行情", icon: TrendingUp, prototypeIcon: PhTrendUp },
  { key: "ai-research", href: "/ai-research", label: "AI 研报", shortLabel: "研报", icon: FileText, prototypeIcon: PhFileText },
  { key: "stock-research", href: "/stock-research", label: "产业链研究", shortLabel: "产业链", icon: Boxes, prototypeIcon: PhFileText },
];

export function MainSidebar({ activeKey, note, hrefOverrides, prototypeIcons = false }: MainSidebarProps) {
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
        {navItems.map(({ key, href, label, shortLabel, icon, prototypeIcon }) => {
          const Icon = prototypeIcons ? prototypeIcon : icon;
          return (
          <Link
            aria-current={activeKey === key ? "page" : undefined}
            className={activeKey === key ? "active" : undefined}
            data-feature-key={key}
            href={hrefOverrides?.[key] || href}
            key={key}
          >
            <Icon aria-hidden="true" />
            <span className="review-workbench-nav-label">
              <b>{label}</b>
              <small>{shortLabel}</small>
            </span>
          </Link>
          );
        })}
      </nav>
      {note ? (
        <div className="review-rail-note">
          {prototypeIcons ? <PhInfo /> : <Info />}
          <span>{note}</span>
        </div>
      ) : null}
    </aside>
  );
}

export function MobileFeatureNav({ activeKey }: Pick<MainSidebarProps, "activeKey">) {
  return (
    <nav className="mobile-only-feature-nav" aria-label="核心功能">
      {navItems.map(({ key, href, shortLabel, icon: Icon }) => (
        <Link aria-current={activeKey === key ? "page" : undefined} className={activeKey === key ? "active" : undefined} href={href} key={key}>
          <Icon aria-hidden="true" />
          <span>{shortLabel}</span>
        </Link>
      ))}
    </nav>
  );
}
