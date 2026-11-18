"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { useEffect, useState } from "react";
import { WAYPOINTS, beijingNow, dayPhase, dialAngle, type BeijingNow } from "./trading-day";

const SIZE = 400;
const C = SIZE / 2;
const R = 150;

// Rounded so server (Node) and browser produce identical SVG attributes:
// their Math.sin/cos differ in the last float digits, which broke hydration.
const round = (value: number) => Math.round(value * 100) / 100;

function polar(angle: number, radius: number) {
  const rad = (angle * Math.PI) / 180;
  return { x: round(C + radius * Math.sin(rad)), y: round(C - radius * Math.cos(rad)) };
}

function arcPath(fromMinute: number, toMinute: number, radius: number) {
  const a0 = dialAngle(fromMinute);
  const a1 = dialAngle(toMinute);
  const start = polar(a0, radius);
  const end = polar(a1, radius);
  const large = a1 - a0 > 180 ? 1 : 0;
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${radius} ${radius} 0 ${large} 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
}

const MARKERS = [
  { minute: 8 * 60 + 30, label: "研报" },
  { minute: 9 * 60 + 25, label: "TOP5" },
  { minute: 15 * 60, label: "收盘" },
  { minute: 19 * 60, label: "行情" },
];

/**
 * A live 12-hour dial (08:00 -> 20:00 Beijing time). One revolution is one
 * trading day; the hand shows where the market is right now and the caption
 * says which tool is most useful at this moment.
 */
export function TradingDayClock() {
  const [now, setNow] = useState<BeijingNow | null>(null);

  useEffect(() => {
    const tick = () => setNow(beijingNow());
    tick();
    const timer = window.setInterval(tick, 20_000);
    return () => window.clearInterval(timer);
  }, []);

  const phase = now ? dayPhase(now) : null;
  const inDial = now ? now.minute >= 8 * 60 && now.minute <= 20 * 60 && phase?.key !== "closed" : false;
  const angle = now && inDial ? dialAngle(now.minute) : 0;
  const focus = phase ? WAYPOINTS.filter((waypoint) => phase.focus.includes(waypoint.id)) : [];

  return (
    <figure className="yh-clock" aria-label="交易日时钟">
      <div className="yh-clock__dial">
        <svg viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-labelledby="yh-clock-title yh-clock-desc">
          <title id="yh-clock-title">交易日时钟（北京时间 08:00 至 20:00）</title>
          <desc id="yh-clock-desc">
            {now && phase ? `现在北京时间 ${now.text}，${phase.title}。${phase.detail}` : "正在读取北京时间"}
          </desc>
          <circle className="yh-clock__face" cx={C} cy={C} r={R + 34} />
          <circle className="yh-clock__track" cx={C} cy={C} r={R} />
          {Array.from({ length: 48 }, (_, index) => {
            const minute = 8 * 60 + index * 15;
            const major = index % 4 === 0;
            const a = dialAngle(minute);
            const p0 = polar(a, R + 10);
            const p1 = polar(a, R + (major ? 22 : 15));
            return <line key={index} className={major ? "yh-clock__tick is-major" : "yh-clock__tick"} x1={p0.x} y1={p0.y} x2={p1.x} y2={p1.y} />;
          })}
          {Array.from({ length: 12 }, (_, index) => {
            const hour = 8 + index;
            const p = polar(dialAngle(hour * 60), R + 46);
            return (
              <text key={hour} className="yh-clock__hour" x={p.x} y={p.y} textAnchor="middle" dominantBaseline="central">
                {hour === 8 ? "08/20" : String(hour).padStart(2, "0")}
              </text>
            );
          })}
          {/* Continuous auction sessions: the hours the market actually trades. */}
          <path className="yh-clock__session" d={arcPath(9 * 60 + 30, 11 * 60 + 30, R)} />
          <path className="yh-clock__session" d={arcPath(13 * 60, 15 * 60, R)} />
          {inDial && now ? <path className="yh-clock__elapsed" d={arcPath(8 * 60, now.minute, R - 18)} /> : null}
          {MARKERS.map((marker) => {
            const p = polar(dialAngle(marker.minute), R);
            const label = polar(dialAngle(marker.minute), R - 30);
            const active = phase?.focus.some((id) => WAYPOINTS.find((w) => w.id === id)?.minute === marker.minute);
            return (
              <g key={marker.label} className={active ? "yh-clock__marker is-active" : "yh-clock__marker"}>
                <circle cx={p.x} cy={p.y} r={6} />
                <text x={label.x} y={label.y} textAnchor="middle" dominantBaseline="central">{marker.label}</text>
              </g>
            );
          })}
          <g className={`yh-clock__hand${inDial ? "" : " is-parked"}${now ? " is-ready" : ""}`} style={{ transform: `rotate(${angle}deg)` }}>
            {/* An outer pointer, not a centre hand: the dial centre holds the time readout. */}
            <line x1={C} y1={C - 74} x2={C} y2={C - R + 6} />
            <circle cx={C} cy={C - R + 6} r={7} />
          </g>
        </svg>
        <div className="yh-clock__readout" aria-hidden="true">
          <span>北京时间</span>
          <b>{now ? now.text : "--:--"}</b>
          <em>{phase ? phase.title : " "}</em>
        </div>
      </div>
      <figcaption className="yh-clock__caption">
        <p>{phase ? phase.detail : "按交易日节奏，告诉你此刻该看什么。"}</p>
        {focus.length ? (
          <ul aria-label="现在适合使用">
            {focus.map((waypoint) => {
              const Icon = waypoint.icon;
              return (
                <li key={waypoint.id}>
                  <Link href={waypoint.href}>
                    <Icon aria-hidden="true" />
                    <span>{waypoint.title}</span>
                    <ArrowUpRight aria-hidden="true" />
                  </Link>
                </li>
              );
            })}
          </ul>
        ) : null}
      </figcaption>
    </figure>
  );
}
