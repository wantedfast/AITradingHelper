"use client";

import type { EChartsOption } from "echarts";
import { useEffect, useRef } from "react";

type AdminAnalyticsChartProps = {
  option: EChartsOption;
  ariaLabel: string;
  empty?: string;
  className?: string;
  onLegendSelect?: (name: string) => void;
};

export function AdminAnalyticsChart({ option, ariaLabel, empty, className = "", onLegendSelect }: AdminAnalyticsChartProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const legendHandlerRef = useRef(onLegendSelect);

  legendHandlerRef.current = onLegendSelect;

  useEffect(() => {
    if (empty || !hostRef.current) return;
    let disposed = false;
    let resizeObserver: ResizeObserver | null = null;
    let chart: import("echarts").ECharts | null = null;

    void import("echarts").then((echarts) => {
      if (disposed || !hostRef.current) return;
      chart = echarts.init(hostRef.current, undefined, { renderer: "canvas" });
      chart.setOption(option, { notMerge: true });
      chart.on("legendselectchanged", (event: unknown) => {
        const name = event && typeof event === "object" && "name" in event ? (event as { name?: unknown }).name : undefined;
        if (typeof name === "string") legendHandlerRef.current?.(name);
      });
      resizeObserver = new ResizeObserver(() => chart?.resize());
      resizeObserver.observe(hostRef.current);
    });

    return () => {
      disposed = true;
      resizeObserver?.disconnect();
      chart?.dispose();
    };
  }, [empty, option]);

  if (empty) return <div className="admin-analytics-empty">{empty}</div>;
  return <div ref={hostRef} className={`admin-echart ${className}`.trim()} role="img" aria-label={ariaLabel} />;
}
