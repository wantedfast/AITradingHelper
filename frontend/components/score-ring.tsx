export function ScoreRing({ score }: { score: number }) {
  const radius = 52;
  const stroke = 9;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - score / 100);

  return (
    <div className="relative h-36 w-36">
      <svg viewBox="0 0 128 128" className="h-full w-full -rotate-90">
        <circle cx="64" cy="64" r={radius} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} />
        <circle
          cx="64"
          cy="64"
          r={radius}
          fill="none"
          stroke="url(#scoreGradient)"
          strokeLinecap="round"
          strokeWidth={stroke}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
        <defs>
          <linearGradient id="scoreGradient" x1="0" x2="1" y1="0" y2="1">
            <stop stopColor="#5CF2C2" />
            <stop offset="1" stopColor="#6BA8FF" />
          </linearGradient>
        </defs>
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <div className="text-center">
          <div className="text-4xl font-bold">{score}</div>
          <div className="text-xs text-slate-400">综合评分</div>
        </div>
      </div>
    </div>
  );
}
