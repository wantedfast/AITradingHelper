import { cn } from "@/lib/utils";

type MetricCardProps = {
  label: string;
  value: string;
  hint?: string;
  tone?: "green" | "blue" | "amber" | "red";
};

const toneClass = {
  green: "text-terminal-glow",
  blue: "text-terminal-blue",
  amber: "text-terminal-amber",
  red: "text-terminal-red"
};

export function MetricCard({ label, value, hint, tone = "green" }: MetricCardProps) {
  return (
    <div className="glass-panel rounded-lg p-4">
      <div className="text-xs text-slate-400">{label}</div>
      <div className={cn("mt-2 text-3xl font-semibold tracking-tight", toneClass[tone])}>{value}</div>
      {hint ? <div className="mt-2 text-xs leading-5 text-slate-400">{hint}</div> : null}
    </div>
  );
}
