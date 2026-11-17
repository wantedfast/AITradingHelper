"use client";

import type { EChartsOption } from "echarts";
import { useEffect, useRef } from "react";

type MarketBreadthChartProps = {
  option: EChartsOption;
  ariaLabel: string;
  empty?: string;
};

export function MarketBreadthChart({ option, ariaLabel, empty }: MarketBreadthChartProps) {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (empty || !hostRef.current) return;
    let disposed = false;
    let resizeObserver: ResizeObserver | null = null;
    let chart: import("echarts").ECharts | null = null;

    void import("echarts").then((echarts) => {
      if (disposed || !hostRef.current) return;
      chart = echarts.init(hostRef.current, undefined, { renderer: "canvas" });
      chart.setOption(option, { notMerge: true });
      resizeObserver = new ResizeObserver(() => chart?.resize());
      resizeObserver.observe(hostRef.current);
    });

    return () => {
      disposed = true;
      resizeObserver?.disconnect();
      chart?.dispose();
    };
  }, [empty, option]);

  if (empty) return <div className="market-breadth-chart-empty">{empty}</div>;
  return <div className="market-breadth-chart" ref={hostRef} role="img" aria-label={ariaLabel} />;
}
