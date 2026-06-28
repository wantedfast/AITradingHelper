"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8600" : "");

export type AuctionPerformanceRow = {
  trade_date: string;
  code: string;
  name: string;
  buy_price: number | null;
  sell_date: string;
  sell_price: number | null;
  return_pct: number;
  return_text: string;
  result: string;
};

export type AuctionPerformancePayload = {
  sample_count: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  win_rate_text: string;
  recent_5_avg_return: number;
  recent_5_avg_return_text: string;
  best_trade: AuctionPerformanceRow | null;
  rows: AuctionPerformanceRow[];
};

export const FALLBACK_AUCTION_PERFORMANCE: AuctionPerformancePayload = {
  sample_count: 7,
  win_count: 7,
  loss_count: 0,
  win_rate: 100,
  win_rate_text: "100.0%",
  recent_5_avg_return: 7.92,
  recent_5_avg_return_text: "+7.92%",
  best_trade: {
    trade_date: "2026-06-18",
    code: "600353",
    name: "旭光电子",
    buy_price: 41.5,
    sell_date: "2026-06-22",
    sell_price: 46.21,
    return_pct: 11.35,
    return_text: "+11.35%",
    result: "win",
  },
  rows: [
    { trade_date: "2026-06-16", code: "301176", name: "逸豪新材", buy_price: 78.41, sell_date: "2026-06-17", sell_price: 79.89, return_pct: 1.89, return_text: "+1.89%", result: "win" },
    { trade_date: "2026-06-17", code: "002741", name: "光华科技", buy_price: 38.68, sell_date: "2026-06-18", sell_price: 41.3, return_pct: 6.77, return_text: "+6.77%", result: "win" },
    { trade_date: "2026-06-18", code: "600353", name: "旭光电子", buy_price: 41.5, sell_date: "2026-06-22", sell_price: 46.21, return_pct: 11.35, return_text: "+11.35%", result: "win" },
    { trade_date: "2026-06-22", code: "600397", name: "江铃装备", buy_price: 21.98, sell_date: "2026-06-23", sell_price: 24.44, return_pct: 11.19, return_text: "+11.19%", result: "win" },
    { trade_date: "2026-06-23", code: "600353", name: "旭光电子", buy_price: 48.74, sell_date: "2026-06-24", sell_price: 52.9, return_pct: 8.54, return_text: "+8.54%", result: "win" },
    { trade_date: "2026-06-24", code: "000566", name: "海南海药", buy_price: 4.33, sell_date: "2026-06-25", sell_price: 4.59, return_pct: 6.0, return_text: "+6.00%", result: "win" },
    { trade_date: "2026-06-25", code: "002409", name: "雅克科技", buy_price: 184.0, sell_date: "2026-06-26", sell_price: 188.6, return_pct: 2.5, return_text: "+2.50%", result: "win" },
  ],
};

export function useAuctionStrengthPerformance() {
  const [performance, setPerformance] = useState<AuctionPerformancePayload>(FALLBACK_AUCTION_PERFORMANCE);

  useEffect(() => {
    let cancelled = false;
    async function loadPerformance() {
      try {
        const response = await fetch(`${API_BASE}/api/auction-strength/performance`, { cache: "no-store" });
        if (!response.ok) return;
        const payload = (await response.json()) as AuctionPerformancePayload;
        if (!cancelled && Array.isArray(payload.rows) && payload.rows.length) {
          setPerformance(payload);
        }
      } catch {
        // Keep the seeded fallback visible when the local API is unavailable.
      }
    }
    void loadPerformance();
    return () => {
      cancelled = true;
    };
  }, []);

  return performance;
}

export function AuctionStrengthPerformanceTicker({ performance }: { performance: AuctionPerformancePayload }) {
  const rows = performance.rows.length ? performance.rows : FALLBACK_AUCTION_PERFORMANCE.rows;
  const loopRows = [...rows, ...rows];

  return (
    <div className="auction-performance-card">
      <div className="auction-performance-top">
        <div>
          <p className="auction-performance-label">目前个股胜率</p>
          <h3>{performance.win_rate_text}</h3>
        </div>
        <div className="auction-performance-badge">集合竞价强者 Top1</div>
      </div>

      <div className="auction-performance-summary">
        <span>近 5 日平均一日收益</span>
        <strong>{performance.recent_5_avg_return_text}</strong>
      </div>

      <div className="auction-performance-header">
        <span>推荐日</span>
        <span>Top1 股票</span>
        <span>买入价</span>
        <span>次日收益</span>
      </div>

      <div className="auction-performance-mask">
        <div className="auction-performance-track">
          {loopRows.map((row, index) => {
            const isNegative = row.return_pct < 0;
            return (
              <div className="auction-performance-row" key={`${row.trade_date}-${row.code || row.name}-${index}`}>
                <span>{row.trade_date}</span>
                <span>{row.name}</span>
                <span>{formatPrice(row.buy_price)}</span>
                <span className={isNegative ? "profit-negative" : "profit-positive"}>{row.return_text}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function formatPrice(value: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "--";
  return value.toFixed(value >= 10 ? 2 : 3).replace(/0+$/, "").replace(/\.$/, "");
}
