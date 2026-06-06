import { resonance } from "@/lib/mock-data";

const colors: Record<string, string> = {
  blue: "from-terminal-blue to-blue-300",
  cyan: "from-cyan-300 to-terminal-blue",
  green: "from-terminal-glow to-emerald-300"
};

export function ResonanceBars() {
  const max = Math.max(...resonance.map((item) => item.value));

  return (
    <div className="space-y-4">
      {resonance.map((item) => (
        <div key={item.label}>
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="text-slate-300">{item.label}</span>
            <span className="font-mono text-slate-100">{item.value.toFixed(2)}%</span>
          </div>
          <div className="h-3 overflow-hidden rounded-full bg-white/8">
            <div
              className={`h-full rounded-full bg-gradient-to-r ${colors[item.tone]}`}
              style={{ width: `${Math.max(8, (item.value / max) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
