import { chainNodes } from "@/lib/mock-data";

const tone: Record<string, string> = {
  driver: "border-terminal-blue bg-terminal-blue/12 text-blue-100",
  core: "border-terminal-glow bg-terminal-glow/14 text-emerald-100",
  stock: "border-terminal-amber bg-terminal-amber/14 text-amber-100",
  adjacent: "border-cyan-300/50 bg-cyan-300/10 text-cyan-100",
  upstream: "border-violet-300/50 bg-violet-300/10 text-violet-100",
  downstream: "border-sky-300/50 bg-sky-300/10 text-sky-100"
};

export function IndustryOrbit() {
  const core = chainNodes.find((node) => node.id === "package")!;

  return (
    <div className="relative h-[360px] overflow-hidden rounded-lg border border-white/10 bg-black/20">
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none">
        {chainNodes
          .filter((node) => node.id !== core.id)
          .map((node) => (
            <line
              key={node.id}
              x1={core.x}
              y1={core.y}
              x2={node.x}
              y2={node.y}
              stroke="rgba(92,242,194,.22)"
              strokeWidth="0.35"
            />
          ))}
      </svg>
      {chainNodes.map((node) => (
        <div
          key={node.id}
          className={`absolute grid h-20 w-20 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border text-center text-xs font-medium shadow-glow ${tone[node.group]}`}
          style={{ left: `${node.x}%`, top: `${node.y}%` }}
        >
          <span className="px-2 leading-4">{node.label}</span>
        </div>
      ))}
      <div className="absolute bottom-4 left-4 right-4 rounded-md border border-white/10 bg-terminal-bg/70 p-3 text-xs leading-5 text-slate-300">
        产业链判断：交易标的不是链条中心，中心驱动是“AI算力对先进封装需求上行”。长电科技处在封测/先进封装兑现节点，壁垒来自客户认证、产能利用率、工艺经验和规模交付。
      </div>
    </div>
  );
}
