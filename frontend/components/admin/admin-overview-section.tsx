"use client";

import type { EChartsOption } from "echarts";
import { BarChart3, Clock3, CreditCard, Gift, MessageSquare, PieChart, TrendingUp, Users } from "lucide-react";
import { useMemo, useState } from "react";
import { AdminAnalyticsChart } from "./admin-analytics-chart";
import type { FeatureUsagePoint, FeatureUsageTotal, RecentUsageEvent, UserGrowthPoint } from "./admin-analytics-types";
import type { AdminSection } from "./admin-navigation";

type OverviewProps = {
  active: boolean;
  totals: { users: number; credits: number; feedback_pending: number; orders_paid: number };
  featureUsage: { totals: FeatureUsageTotal[]; byDay: FeatureUsagePoint[] };
  userGrowth: { startingUsers: number; totalUsers: number; byDay: UserGrowthPoint[] };
  days: number;
  pendingOrders: number;
  pendingFeedback: number;
  failedEmails: number;
  failedDailyTop5Emails: number;
  onNavigate: (section: AdminSection) => void;
  featureLabel: (value: string) => string;
  recentUsageEvents: RecentUsageEvent[];
};

const chartColors = ["#f5d77a", "#55d6a8", "#79a9ff", "#f39a72", "#c897e8", "#88c7d8", "#e3b85d"];

export function AdminOverviewSection(props: OverviewProps) {
  const [usageFeature, setUsageFeature] = useState("all");
  const featureTrendOption = useMemo(
    () => buildFeatureTrendOption(props.featureUsage.byDay, props.featureLabel),
    [props.featureUsage.byDay, props.featureLabel],
  );
  const featureShareOption = useMemo(
    () => buildFeatureShareOption(props.featureUsage.totals, props.featureLabel),
    [props.featureUsage.totals, props.featureLabel],
  );
  const userGrowthOption = useMemo(
    () => buildUserGrowthOption(props.userGrowth.byDay),
    [props.userGrowth.byDay],
  );
  const featureTotal = props.featureUsage.totals.reduce((sum, item) => sum + item.count, 0);
  const hasFeatureUsage = featureTotal > 0;
  const hasUserGrowth = props.userGrowth.byDay.some((item) => item.new_users > 0 || item.cumulative_users > 0);
  const filteredUsageEvents = usageFeature === "all"
    ? props.recentUsageEvents
    : props.recentUsageEvents.filter((item) => item.feature === usageFeature);

  return (
    <section className={`admin-section admin-section--overview${props.active ? " is-active" : ""}`}>
      <section className="admin-priority-grid">
        <PriorityCard label="待确认会员订单" count={props.pendingOrders} onClick={() => props.onNavigate("orders")} />
        <PriorityCard label="待处理反馈" count={props.pendingFeedback} onClick={() => props.onNavigate("feedback")} />
        <PriorityCard label="失败邮件任务" count={props.failedEmails} onClick={() => props.onNavigate("updates")} />
        <PriorityCard label="失败 TOP5 邮件" count={props.failedDailyTop5Emails} onClick={() => props.onNavigate("updates")} />
      </section>
      <section className="admin-metrics">
        <Metric icon={Users} label="普通用户" value={props.totals.users} />
        <Metric icon={Gift} label="系统剩余次数" value={props.totals.credits} />
        <Metric icon={MessageSquare} label="待审核反馈" value={props.totals.feedback_pending} />
        <Metric icon={CreditCard} label="已支付订单" value={props.totals.orders_paid} />
      </section>

      <section className="admin-analytics-grid">
        <article className="admin-panel admin-analytics-panel admin-analytics-panel--wide">
          <PanelHeading icon={BarChart3} title={`近 ${props.days} 天功能使用趋势`} subtitle="按天查看五项功能的使用次数，可点击图例隐藏或显示曲线。" />
          <AdminAnalyticsChart
            option={featureTrendOption}
            ariaLabel={`近 ${props.days} 天各功能每日使用次数折线图`}
            empty={!hasFeatureUsage ? "这段时间还没有功能使用记录。" : undefined}
            className="admin-echart--trend"
          />
        </article>

        <article className="admin-panel admin-analytics-panel">
          <PanelHeading icon={PieChart} title="功能使用构成" subtitle={`合计 ${featureTotal.toLocaleString()} 次使用`} />
          <div className="admin-feature-share-layout">
            <AdminAnalyticsChart
              option={featureShareOption}
              ariaLabel={`近 ${props.days} 天功能使用占比环形图`}
              empty={!hasFeatureUsage ? "暂无可统计的功能使用。" : undefined}
              className="admin-echart--donut"
            />
            {hasFeatureUsage && (
              <div className="admin-feature-ranking" aria-label="功能使用排名">
                {props.featureUsage.totals.map((item, index) => {
                  const share = item.share ?? (featureTotal ? item.count / featureTotal : 0);
                  return (
                    <div key={item.feature}>
                      <i style={{ background: chartColors[index % chartColors.length] }} />
                      <span><b>{props.featureLabel(item.feature)}</b><small>{item.credits} 次额度消耗</small></span>
                      <strong>{item.count}<small>{formatShare(share)}</small></strong>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </article>

        <article className="admin-panel admin-analytics-panel">
          <PanelHeading icon={TrendingUp} title="用户增长" subtitle={`期初 ${props.userGrowth.startingUsers} 人 · 当前 ${props.userGrowth.totalUsers} 人`} />
          <AdminAnalyticsChart
            option={userGrowthOption}
            ariaLabel={`近 ${props.days} 天每日新增用户柱状图与累计用户折线图`}
            empty={!hasUserGrowth ? "这段时间还没有用户增长数据。" : undefined}
            className="admin-echart--growth"
          />
        </article>
      </section>

      <article className="admin-panel admin-usage-timeline">
        <div className="admin-panel-head admin-usage-timeline-head">
          <Clock3 />
          <div>
            <h2>最近功能使用时间</h2>
            <p>记录用户首次成功使用的北京时间；重复刷新不会重复计算。</p>
          </div>
          <label>
            <span>筛选功能</span>
            <select value={usageFeature} onChange={(event) => setUsageFeature(event.target.value)}>
              <option value="all">全部功能</option>
              {props.featureUsage.totals.map((item) => (
                <option value={item.feature} key={item.feature}>{props.featureLabel(item.feature)}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="admin-usage-timeline-table">
          <div className="admin-usage-timeline-row admin-usage-timeline-row--head" aria-hidden="true">
            <span>用户</span><span>功能</span><span>使用时间</span><span>状态</span>
          </div>
          {filteredUsageEvents.map((item) => (
            <div className="admin-usage-timeline-row" key={item.id}>
              <span data-label="用户"><b>{item.display_name}</b><small>用户 ID {item.user_id}</small></span>
              <span data-label="功能"><b>{props.featureLabel(item.feature)}</b>{item.market_session ? <em className={item.market_session}>{item.market_session === "before_open" ? "开盘前" : "开盘后"}</em> : null}</span>
              <span data-label="使用时间"><b>{formatUsageTime(item.used_at)}</b></span>
              <span data-label="状态"><b>{item.status === "membership_free" ? "会员免扣" : `扣 ${item.credits_spent} 次`}</b></span>
            </div>
          ))}
          {!filteredUsageEvents.length ? <div className="admin-filter-empty">当前周期内暂无该功能的成功使用记录。</div> : null}
        </div>
      </article>
    </section>
  );
}

function formatUsageTime(value: string) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

function PriorityCard({ label, count, onClick }: { label: string; count: number; onClick: () => void }) {
  return <button className={count ? "has-items" : ""} type="button" onClick={onClick}><span>{label}</span><b>{count}</b><small>{count ? "立即处理" : "当前无待办"}</small></button>;
}

function Metric({ icon: Icon, label, value }: { icon: typeof Users; label: string; value: number }) {
  return <article><Icon /><span>{label}</span><b>{value.toLocaleString()}</b></article>;
}

function PanelHeading({ icon: Icon, title, subtitle }: { icon: typeof Users; title: string; subtitle: string }) {
  return <div className="admin-panel-head admin-analytics-heading"><Icon /><div><h2>{title}</h2><p>{subtitle}</p></div></div>;
}

function buildFeatureTrendOption(points: FeatureUsagePoint[], featureLabel: (value: string) => string): EChartsOption {
  const days = unique(points.map((item) => item.day)).sort();
  const features = unique(points.map((item) => item.feature));
  return baseCartesianOption({
    legend: analyticsLegend(features.map(featureLabel)),
    xAxis: categoryAxis(days.map(shortDay), false),
    yAxis: valueAxis("使用次数"),
    series: features.map((feature, index) => ({
      name: featureLabel(feature),
      type: "line",
      data: days.map((day) => points.find((item) => item.day === day && item.feature === feature)?.count || 0),
      smooth: days.length > 2 ? 0.25 : false,
      symbol: days.length === 1 ? "circle" : "none",
      symbolSize: 8,
      lineStyle: { width: 2, color: chartColors[index % chartColors.length] },
      itemStyle: { color: chartColors[index % chartColors.length] },
      emphasis: { focus: "series" },
    })),
  });
}

function buildFeatureShareOption(totals: FeatureUsageTotal[], featureLabel: (value: string) => string): EChartsOption {
  return {
    color: chartColors,
    animationDuration: 450,
    tooltip: { trigger: "item", formatter: "{b}<br/>{c} 次 · {d}%" },
    series: [{
      type: "pie",
      radius: ["54%", "78%"],
      center: ["50%", "50%"],
      avoidLabelOverlap: true,
      label: { show: false },
      emphasis: { label: { show: true, color: "#f4f0e8", fontWeight: 800, formatter: "{d}%" } },
      itemStyle: { borderColor: "#090c0b", borderWidth: 3, borderRadius: 4 },
      data: totals.map((item) => ({ name: featureLabel(item.feature), value: item.count })),
    }],
  };
}

function buildUserGrowthOption(points: UserGrowthPoint[]): EChartsOption {
  const days = points.map((item) => item.day);
  return baseCartesianOption({
    legend: analyticsLegend(["每日新增", "累计用户"]),
    xAxis: categoryAxis(days.map(shortDay), true),
    yAxis: [
      valueAxis("新增"),
      { ...valueAxis("累计"), splitLine: { show: false } },
    ],
    series: [
      { name: "每日新增", type: "bar", data: points.map((item) => item.new_users), barMaxWidth: 22, itemStyle: { color: "rgba(245,215,122,.72)", borderRadius: [5, 5, 0, 0] } },
      { name: "累计用户", type: "line", yAxisIndex: 1, data: points.map((item) => item.cumulative_users), smooth: points.length > 2 ? 0.25 : false, symbol: points.length === 1 ? "circle" : "none", symbolSize: 8, lineStyle: { color: "#55d6a8", width: 2 }, itemStyle: { color: "#55d6a8" } },
    ],
  });
}

function baseCartesianOption(option: EChartsOption): EChartsOption {
  return {
    color: chartColors,
    animationDuration: 450,
    textStyle: { color: "#aab1ad", fontFamily: "Inter, Microsoft YaHei, sans-serif" },
    tooltip: { trigger: "axis", backgroundColor: "rgba(7,10,9,.96)", borderColor: "rgba(245,215,122,.25)", textStyle: { color: "#f4f0e8" } },
    grid: { top: 52, right: 24, bottom: 28, left: 50, containLabel: false },
    ...option,
  };
}

function analyticsLegend(data: string[]) {
  return { top: 0, type: "scroll" as const, data, textStyle: { color: "#aab1ad" }, pageTextStyle: { color: "#aab1ad" } };
}

function categoryAxis(data: string[], boundaryGap: boolean) {
  return {
    type: "category" as const,
    data,
    boundaryGap,
    axisLine: { lineStyle: { color: "rgba(244,240,232,.15)" } },
    axisLabel: { color: "#89918c", hideOverlap: true },
    axisTick: { show: false },
  };
}

function valueAxis(name: string) {
  return {
    type: "value" as const,
    minInterval: 1,
    name,
    axisLabel: { color: "#89918c" },
    nameTextStyle: { color: "#727b75" },
    splitLine: { lineStyle: { color: "rgba(244,240,232,.07)" } },
  };
}

function unique(values: string[]) {
  return Array.from(new Set(values));
}

function shortDay(value: string) {
  return value.length >= 10 ? value.slice(5) : value;
}

function formatShare(value: number) {
  const percent = value > 1 ? value : value * 100;
  return `${percent.toFixed(percent >= 10 ? 0 : 1)}%`;
}
