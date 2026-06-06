export const tradeSummary = {
  stock: "长电科技",
  code: "600584",
  date: "2026-05-29",
  score: 87,
  rating: "A-",
  verdict: "买点合格，卖点需要规则化",
  pnl: "+18.6%",
  bestExit: "5日线失守或放量长阴后减仓",
  market: "指数缩量震荡，半导体方向强于沪深300",
  nextAction: "若反抽到预案价，按计划减仓，不临盘改剧本"
};

export const resonance = [
  { label: "沪深300", value: 0.72, tone: "blue" },
  { label: "半导体板块", value: 3.84, tone: "cyan" },
  { label: "长电科技", value: 7.92, tone: "green" }
];

export const execution = [
  { label: "逻辑", value: 92 },
  { label: "买点", value: 88 },
  { label: "卖点", value: 76 },
  { label: "风控", value: 84 }
];

export const chainNodes = [
  { id: "driver", label: "AI算力", group: "driver", x: 50, y: 12 },
  { id: "package", label: "先进封装", group: "core", x: 50, y: 36 },
  { id: "jcet", label: "长电科技", group: "stock", x: 50, y: 61 },
  { id: "material", label: "基板/材料", group: "adjacent", x: 22, y: 48 },
  { id: "equipment", label: "封测设备", group: "adjacent", x: 78, y: 48 },
  { id: "server", label: "服务器链", group: "downstream", x: 28, y: 76 },
  { id: "chip", label: "GPU/ASIC", group: "upstream", x: 72, y: 76 }
];

export const alerts = [
  { name: "长电科技", condition: "反抽至 82.05", action: "减仓/走人", status: "待触发" },
  { name: "风华高科", condition: "跌破 46.20", action: "止损", status: "暂停" },
  { name: "中国巨石", condition: "放量突破前高", action: "确认强度", status: "待触发" }
];
