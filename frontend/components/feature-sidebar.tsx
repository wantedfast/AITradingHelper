import Image from "next/image";
import Link from "next/link";
import { BarChart3, FileUp, Info, TrendingUp, Trophy } from "lucide-react";

type FeatureKey = "review" | "watch" | "market-day" | "auction-strength";

type FeatureSidebarProps = {
  active: FeatureKey;
  note?: string;
  watchHref?: string;
};

const NAV_ITEMS = [
  { key: "review", href: "/review", label: "AI复盘", icon: FileUp },
  { key: "watch", href: "/watch", label: "AI盯盘", icon: BarChart3 },
  { key: "market-day", href: "/market-day", label: "AI当日行情", icon: TrendingUp },
  { key: "auction-strength", href: "/auction-strength", label: "竞价强者", icon: Trophy },
] satisfies Array<{ key: FeatureKey; href: string; label: string; icon: typeof FileUp }>;

export function FeatureSidebar({ active, note, watchHref }: FeatureSidebarProps) {
  return (
    <aside className="review-workbench-rail">
      <Link className="review-workbench-brand feature-sidebar-brand" href="/">
        <Image alt="盈航" src="/brand-logo-transparent.png" width={88} height={88} priority />
        <span>
          <b>盈航</b>
          <small>MARKET DAY</small>
        </span>
      </Link>
      <nav className="review-workbench-nav" aria-label="核心功能">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const href = item.key === "watch" && watchHref ? watchHref : item.href;
          return (
            <Link className={active === item.key ? "active" : ""} href={href} key={item.key}>
              <Icon />
              <span><b>{item.label}</b></span>
            </Link>
          );
        })}
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
