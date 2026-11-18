import { Activity, BellRing, Boxes, FileSearch, FileText, TrendingUp, Trophy, type LucideIcon } from "lucide-react";

/**
 * The product, organised the way a trader actually lives it: one trading day.
 * Times are Beijing time (Asia/Shanghai). `minute` is minutes after midnight.
 */
export type Waypoint = {
  id: string;
  time: string;
  minute: number | null;
  href: string;
  title: string;
  label: string;
  icon: LucideIcon;
  summary: string;
  points: [string, string];
};

export const WAYPOINTS: Waypoint[] = [
  {
    id: "research",
    time: "08:30",
    minute: 8 * 60 + 30,
    href: "/ai-research",
    title: "AI 研报",
    label: "Morning brief",
    icon: FileText,
    summary: "汇总隔夜国内外重要消息，讲清 CPI、黄金、原油和海外观点可能怎样影响 A 股。",
    points: ["国内外重要消息", "利好利空怎么理解"],
  },
  {
    id: "top5",
    time: "09:25",
    minute: 9 * 60 + 25,
    href: "/auction-strength",
    title: "每日 TOP5",
    label: "Opening auction",
    icon: Trophy,
    summary: "集合竞价一结束，选出当天最值得关注的 5 只强势股，并提示需要回避的方向。",
    points: ["5 只强势股", "风险方向提示"],
  },
  {
    id: "breadth",
    time: "盘中",
    minute: 9 * 60 + 30,
    href: "/market-breadth",
    title: "市场真实强弱",
    label: "Live breadth",
    icon: Activity,
    summary: "汇总全市场涨跌家数和成交额，看清指数是真涨真跌，还是少数权重股造成的假象。",
    points: ["识别真假涨跌", "每分钟更新"],
  },
  {
    id: "review",
    time: "15:00",
    minute: 15 * 60,
    href: "/review",
    title: "AI 复盘",
    label: "Trade review",
    icon: FileSearch,
    summary: "输入今天的一笔交易，看哪里做对、哪里要改，下次遇到同样情况怎么做。",
    points: ["做对了什么", "下次怎么改"],
  },
  {
    id: "watch",
    time: "15:00",
    minute: 15 * 60,
    href: "/watch",
    title: "AI 盯盘",
    label: "Tomorrow's plan",
    icon: BellRing,
    summary: "填入持仓和计划，整理明天观察什么、什么情况买卖、什么情况先停手。",
    points: ["明天观察什么", "何时买卖或停手"],
  },
  {
    id: "market-day",
    time: "19:00",
    minute: 19 * 60,
    href: "/market-day",
    title: "AI 当日行情",
    label: "Evening wrap",
    icon: TrendingUp,
    summary: "总结今天市场在炒什么、哪些板块强弱，并给出第二天的关注重点。",
    points: ["板块强弱", "明天关注重点"],
  },
  {
    id: "value",
    time: "随时",
    minute: null,
    href: "/stock-research",
    title: "价值投资",
    label: "Deep research",
    icon: Boxes,
    summary: "从竞争壁垒、盈利质量和成长确定性出发，读懂一家公司及它在产业链里的位置。",
    points: ["竞争壁垒", "盈利与成长"],
  },
];

export type DayPhase = {
  key: "closed" | "pre" | "brief" | "auction" | "session" | "lunch" | "after" | "evening" | "night";
  title: string;
  detail: string;
  /** Waypoint ids that are most useful right now. */
  focus: string[];
};

export type BeijingNow = { minute: number; weekday: number; text: string };

/** Current Beijing time, independent of the visitor's own timezone. */
export function beijingNow(date = new Date()): BeijingNow {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Shanghai",
    hour: "2-digit",
    minute: "2-digit",
    weekday: "short",
    hour12: false,
  }).formatToParts(date);
  const get = (type: string) => parts.find((part) => part.type === type)?.value || "";
  const hour = Number(get("hour")) % 24;
  const minute = Number(get("minute"));
  const weekday = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(get("weekday"));
  return { minute: hour * 60 + minute, weekday, text: `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}` };
}

/**
 * Where we are in the trading day. Exchange holidays are not modelled; the
 * copy therefore speaks of "交易日" rhythm rather than promising the market is open.
 */
export function dayPhase(now: BeijingNow): DayPhase {
  const m = now.minute;
  if (now.weekday === 0 || now.weekday === 6) {
    return { key: "closed", title: "周末休市", detail: "适合做功课：读懂一家公司，或回看这周的复盘。", focus: ["value", "review"] };
  }
  if (m < 8 * 60 + 30) return { key: "pre", title: "开盘前", detail: "08:30 发布 AI 研报，先了解隔夜发生了什么。", focus: ["research"] };
  if (m < 9 * 60 + 25) return { key: "brief", title: "早盘准备", detail: "读研报，09:25 集合竞价结束后看 TOP5。", focus: ["research", "top5"] };
  if (m < 9 * 60 + 30) return { key: "auction", title: "集合竞价刚结束", detail: "今天的 TOP5 已出炉，开盘前看清强势股与回避方向。", focus: ["top5"] };
  if (m < 11 * 60 + 30) return { key: "session", title: "上午盘中", detail: "用市场真实强弱判断指数涨跌是否失真。", focus: ["breadth", "top5"] };
  if (m < 13 * 60) return { key: "lunch", title: "午间休市", detail: "回看上午的强弱与 TOP5 表现，想好下午的计划。", focus: ["breadth", "top5"] };
  if (m < 15 * 60) return { key: "session", title: "下午盘中", detail: "用市场真实强弱判断指数涨跌是否失真。", focus: ["breadth"] };
  if (m < 19 * 60) return { key: "after", title: "收盘后", detail: "趁记忆新鲜复盘今天的交易，并整理明天的盯盘计划。", focus: ["review", "watch"] };
  if (m < 23 * 60) return { key: "evening", title: "晚间", detail: "AI 当日行情已发布：今天在炒什么，明天看什么。", focus: ["market-day", "watch"] };
  return { key: "night", title: "夜间", detail: "休息一下。明早 08:30 见 AI 研报。", focus: ["research"] };
}

/** The 12-hour dial runs from 08:00 to 20:00 - one revolution is one trading day. */
export const DIAL_START = 8 * 60;
export const DIAL_SPAN = 12 * 60;

export function dialAngle(minute: number) {
  const clamped = Math.min(Math.max(minute - DIAL_START, 0), DIAL_SPAN);
  return (clamped / DIAL_SPAN) * 360;
}
