"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  BellRing,
  BriefcaseBusiness,
  CalendarDays,
  ChevronLeft,
  Clock3,
  ImageUp,
  List,
  PauseCircle,
  PencilLine,
  PlayCircle,
  RefreshCcw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Triangle,
  Volume2,
  X,
  Radar,
} from "lucide-react";


const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

const POSITION_OPTIONS = [
  "1成 (10%)",
  "2成 (20%)",
  "3成 (30%)",
  "半仓 (50%)",
  "7成 (70%)",
  "重仓 (80%)",
  "满仓 (100%)",
];

const PREVIEW_FEATURES = [
  ["AI 总结", "自动整理交易逻辑和次日观察重点。"],
  ["关键价位", "输出观察位、突破位、目标位和风险位。"],
  ["操作预案", "把盘中应对动作整理成清晰执行步骤。"],
  ["盘中提醒", "在观察日按条件推送消息并尝试语音播报。"],
];

const PREVIEW_PLAN_GAP = 10;
const PREVIEW_PLAN_MIN_HEIGHT = 148;
const PREVIEW_PLAN_ROTATE_MS = 3200;

type Mode = "entry" | "result";

type WatchPlan = {
  plan_id: string;
  code: string;
  name: string;
  action: string;
  thesis: string;
  buy_date: string;
  watch_date: string;
  position: string;
  buy_price?: number | null;
  reference_price?: number | null;
  stop_loss?: number | null;
  take_profit?: number | null;
  breakout?: number | null;
  breakdown?: number | null;
  voice_line: string;
  enabled: boolean;
};

type Quote = {
  code: string;
  name: string;
  price: number;
  prev_close: number;
  pct_chg: number;
  quote_time: string;
};

type WatchEvent = {
  key: string;
  plan_id: string;
  code: string;
  name: string;
  level: string;
  triggered_key: string;
  message: string;
  voice_line: string;
  audio_url?: string;
  voice_provider?: string;
  voice_name?: string;
  occurred_at: string;
  quote: Quote;
};

type PollPayload = {
  plans: WatchPlan[];
  quotes: Quote[];
  events: WatchEvent[];
  errors: string[];
};

type VoiceSettings = {
  provider: "openai" | "edge";
  openai_voice: string;
  edge_voice: string;
  fallback_browser_voice_hint: "female" | "male";
  preview_text: string;
};

type VoiceOption = {
  value: string;
  label: string;
};

type VoiceSettingsPayload = {
  settings: VoiceSettings;
  options: {
    provider: VoiceOption[];
    openai_voice: VoiceOption[];
    edge_voice: VoiceOption[];
    fallback_browser_voice_hint: VoiceOption[];
  };
};

type WatchEntryMode = "manual" | "ocr";

type WatchFormErrors = {
  stockName?: string;
  buyDate?: string;
  position?: string;
  buyPrice?: string;
  ocrFile?: string;
};

type WatchOcrFields = {
  stock_name: string;
  buy_date: string;
  position: string;
  buy_price: string;
  note: string;
};

type WatchOcrPayload = {
  fields: WatchOcrFields;
  error?: string;
};

const FALLBACK_VOICE_OPTIONS: VoiceSettingsPayload["options"] = {
  provider: [
    { value: "openai", label: "OpenAI TTS" },
    { value: "edge", label: "Edge TTS" },
  ],
  openai_voice: [
    { value: "alloy", label: "OpenAI Alloy" },
    { value: "verse", label: "OpenAI Verse" },
    { value: "aria", label: "OpenAI Aria" },
  ],
  edge_voice: [
    { value: "zh-CN-XiaoxiaoNeural", label: "Edge 晓晓" },
    { value: "zh-CN-XiaoyiNeural", label: "Edge 晓伊" },
    { value: "zh-CN-YunxiNeural", label: "Edge 云希" },
    { value: "zh-CN-YunjianNeural", label: "Edge 云健" },
  ],
  fallback_browser_voice_hint: [
    { value: "female", label: "浏览器偏女声" },
    { value: "male", label: "浏览器偏男声" },
  ],
};

function fallbackSpeak(text: string, hint: "female" | "male" = "female") {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "zh-CN";
  utterance.rate = 1.02;
  utterance.pitch = 1.06;
  const voices = window.speechSynthesis.getVoices();
  const ranked = voices
    .filter((voice) => /zh|chinese|mandarin/i.test(`${voice.lang} ${voice.name}`))
    .sort((left, right) => scoreBrowserVoice(`${right.name} ${right.lang}`, hint) - scoreBrowserVoice(`${left.name} ${left.lang}`, hint));
  if (ranked[0]) {
    utterance.voice = ranked[0];
  }
  window.speechSynthesis.speak(utterance);
}

function scoreBrowserVoice(name: string, hint: "female" | "male") {
  let score = 0;
  if (/zh|chinese|mandarin/i.test(name)) score += 8;
  if (hint === "female" && /xiaoxiao|xiaoyi|huihui|tingting|female|woman|girl/i.test(name)) score += 5;
  if (hint === "male" && /yunxi|yunjian|male|man|boy/i.test(name)) score += 5;
  return score;
}

function fmtPrice(value?: number | null) {
  return typeof value === "number" ? value.toFixed(2) : "--";
}

function todayIsoDate() {
  const today = new Date();
  const year = today.getFullYear();
  const month = `${today.getMonth() + 1}`.padStart(2, "0");
  const day = `${today.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function isoToDisplayDate(value: string) {
  const match = value.trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return value;
  return `${match[3]}/${match[2]}/${match[1].slice(-2)}`;
}

function displayToIsoDate(value: string) {
  const text = value.trim();
  if (!text) return "";
  const isoMatch = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (isoMatch) return text;
  const slashMatch = text.match(/^(\d{2})\/(\d{2})\/(\d{2}|\d{4})$/);
  if (!slashMatch) return "";
  const rawYear = slashMatch[3];
  const year = rawYear.length === 2 ? `20${rawYear}` : rawYear;
  return `${year}-${slashMatch[2]}-${slashMatch[1]}`;
}

function normalizeDisplayDate(value: string) {
  const iso = displayToIsoDate(value);
  return iso ? isoToDisplayDate(iso) : value;
}

function buildPlanActionLines(plan: WatchPlan) {
  const lines: string[] = [];
  if (typeof plan.breakout === "number") {
    lines.push(`若股价放量突破 ${fmtPrice(plan.breakout)}，优先按“${plan.action || "顺势执行"}”处理。`);
  }
  if (typeof plan.reference_price === "number") {
    lines.push(`若盘中围绕观察位 ${fmtPrice(plan.reference_price)} 反复拉锯，重点看承接和量能是否同步改善。`);
  }
  if (typeof plan.take_profit === "number") {
    lines.push(`若拉升接近目标位 ${fmtPrice(plan.take_profit)}，优先按纪律兑现部分利润，不再临盘犹豫。`);
  }
  if (typeof plan.breakdown === "number") {
    lines.push(`若跌破失效位 ${fmtPrice(plan.breakdown)}，说明预案弱化，需要重新评估强度。`);
  } else if (typeof plan.stop_loss === "number") {
    lines.push(`若跌破止损位 ${fmtPrice(plan.stop_loss)}，趋势失效，及时控制风险。`);
  }
  if (!lines.length) {
    lines.push(plan.action || "按计划观察次日强弱变化。");
  }
  return lines;
}

function buildWatchPhase(plan: WatchPlan) {
  if (!plan.watch_date) {
    return {
      tone: "idle",
      label: "已保存预案",
      detail: "这份预案已经写入系统，等待你在观察日打开页面开始盯盘。",
    };
  }

  const today = todayIsoDate();
  if (plan.watch_date > today) {
    return {
      tone: "upcoming",
      label: `等待 ${plan.watch_date}`,
      detail: "系统会在观察日的交易时段按预案轮询并推送提醒。",
    };
  }

  if (plan.watch_date < today) {
    return {
      tone: "history",
      label: "历史预案",
      detail: "这份预案已经过了观察日，可继续作为复盘和复用参考。",
    };
  }

  if (isTradingSessionNow()) {
    return {
      tone: "live",
      label: "今日盘中盯盘中",
      detail: "当前处于观察日交易时段，系统会按价格条件推送消息并尝试语音播报。",
    };
  }

  return {
    tone: "today",
    label: "今日预案待执行",
    detail: "今天就是观察日。若还未开盘或已经收盘，系统会在下一个有效交易时段继续监控。",
  };
}

function isTradingSessionNow() {
  const now = new Date();
  const hourMinute = now.getHours() * 100 + now.getMinutes();
  const inMorning = hourMinute >= 930 && hourMinute <= 1130;
  const inAfternoon = hourMinute >= 1300 && hourMinute <= 1500;
  return inMorning || inAfternoon;
}

function shortText(text: string, limit = 78) {
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
}

function keyLevelsForPlan(plan: WatchPlan) {
  const support = plan.breakdown ?? plan.stop_loss ?? null;
  const observe = plan.reference_price ?? null;
  const resistance = plan.breakout ?? null;
  const target = plan.take_profit ?? null;
  const stop = plan.stop_loss ?? plan.breakdown ?? null;
  return [
    { label: "支撑位", value: support, tone: "support" },
    { label: "观察位", value: observe, tone: "observe" },
    { label: "压力位", value: resistance, tone: "resistance" },
    { label: "目标位", value: target, tone: "target" },
    { label: "止损位", value: stop, tone: "stop" },
  ];
}

function normalizePositionOption(value: string) {
  const text = value.trim();
  return POSITION_OPTIONS.includes(text) ? text : "";
}

export default function WatchClient({ mode }: { mode: Mode }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedPlanId = searchParams.get("planId") || "";
  const viewMode: Mode = mode === "result" || requestedPlanId ? "result" : "entry";

  const [entryMode, setEntryMode] = useState<WatchEntryMode>("manual");
  const [stockName, setStockName] = useState("");
  const [buyDate, setBuyDate] = useState("");
  const [position, setPosition] = useState("");
  const [buyPrice, setBuyPrice] = useState("");
  const [fieldErrors, setFieldErrors] = useState<WatchFormErrors>({});
  const [ocrFile, setOcrFile] = useState<File | null>(null);
  const [ocrStatus, setOcrStatus] = useState("");
  const [ocrParsing, setOcrParsing] = useState(false);
  const [plans, setPlans] = useState<WatchPlan[]>([]);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [events, setEvents] = useState<WatchEvent[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [voiceSettings, setVoiceSettings] = useState<VoiceSettings>({
    provider: "edge",
    openai_voice: "alloy",
    edge_voice: "zh-CN-XiaoyiNeural",
    fallback_browser_voice_hint: "female",
    preview_text: "请注意，预案已经触发，请按计划执行。",
  });
  const [voiceOptions, setVoiceOptions] = useState<VoiceSettingsPayload["options"]>(FALLBACK_VOICE_OPTIONS);
  const [loadingPlans, setLoadingPlans] = useState(false);
  const [loadingInitialPlans, setLoadingInitialPlans] = useState(true);
  const [savingVoice, setSavingVoice] = useState(false);
  const [previewingVoice, setPreviewingVoice] = useState(false);
  const [previewPlanLimit, setPreviewPlanLimit] = useState(2);
  const [previewPlanOffset, setPreviewPlanOffset] = useState(0);
  const [previewPlanPaused, setPreviewPlanPaused] = useState(false);
  const [previewPlanTrackAnimated, setPreviewPlanTrackAnimated] = useState(false);
  const [previewStageHeight, setPreviewStageHeight] = useState(0);
  const [polling, setPolling] = useState(viewMode === "result");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [planListOpen, setPlanListOpen] = useState(false);
  const [toast, setToast] = useState("");

  const entryFormRef = useRef<HTMLElement>(null);
  const previewStageRef = useRef<HTMLDivElement>(null);
  const calendarInputRef = useRef<HTMLInputElement>(null);
  const ocrInputRef = useRef<HTMLInputElement>(null);
  const playedKeys = useRef<Set<string>>(new Set());
  const toastTimer = useRef<number>();

  const selectedPlan = useMemo(() => {
    if (!plans.length) return null;
    return plans.find((plan) => plan.plan_id === requestedPlanId) || plans[0];
  }, [plans, requestedPlanId]);

  const selectedQuote = useMemo(() => {
    if (!selectedPlan) return null;
    return quotes.find((quote) => quote.code === selectedPlan.code) || null;
  }, [quotes, selectedPlan]);

  const selectedEvents = useMemo(() => {
    if (!selectedPlan) return events;
    return events.filter((item) => item.plan_id === selectedPlan.plan_id);
  }, [events, selectedPlan]);

  const watchPhase = selectedPlan ? buildWatchPhase(selectedPlan) : null;
  const actionLines = selectedPlan ? buildPlanActionLines(selectedPlan) : [];
  const keyLevels = selectedPlan ? keyLevelsForPlan(selectedPlan) : [];
  const previewLoopEnabled = viewMode === "entry" && plans.length > previewPlanLimit;
  const previewPlanCardHeight = useMemo(() => {
    if (!previewStageHeight || previewPlanLimit <= 0) {
      return PREVIEW_PLAN_MIN_HEIGHT;
    }
    const totalGap = PREVIEW_PLAN_GAP * Math.max(previewPlanLimit - 1, 0);
    return Math.max(PREVIEW_PLAN_MIN_HEIGHT, (previewStageHeight - totalGap) / previewPlanLimit);
  }, [previewStageHeight, previewPlanLimit]);
  const previewPlansToRender = useMemo(() => {
    if (!plans.length) return [];
    if (!previewLoopEnabled) {
      return plans.slice(0, previewPlanLimit);
    }
    return [...plans, ...plans.slice(0, previewPlanLimit)];
  }, [plans, previewLoopEnabled, previewPlanLimit]);
  const previewPlanTrackStyle = useMemo(() => ({
    "--preview-plan-gap": `${PREVIEW_PLAN_GAP}px`,
    "--preview-plan-height": `${previewPlanCardHeight}px`,
    "--preview-plan-offset": `${previewPlanOffset}`,
  } as CSSProperties), [previewPlanCardHeight, previewPlanOffset]);

  function showToast(text: string) {
    setToast(text);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(""), 2600);
  }

  function clearFieldError(field: keyof WatchFormErrors) {
    setFieldErrors((current) => {
      if (!current[field]) return current;
      return { ...current, [field]: "" };
    });
  }

  function validateEntryForm() {
    const nextErrors: WatchFormErrors = {};
    const nextStock = stockName.trim();
    const nextBuyDate = buyDate.trim();
    const nextPosition = position.trim();
    const nextBuyPrice = buyPrice.trim();

    if (!nextStock) {
      nextErrors.stockName = "请填写股票名称。";
    }
    if (!nextBuyDate) {
      nextErrors.buyDate = "请填写买入时间。";
    } else if (!displayToIsoDate(nextBuyDate)) {
      nextErrors.buyDate = "请按 DD/MM/YY 输入，或使用日历选择。";
    }
    if (!nextPosition) {
      nextErrors.position = "请选择当前仓位。";
    }
    if (!nextBuyPrice) {
      nextErrors.buyPrice = "请填写买入价。";
    } else if (Number.isNaN(Number(nextBuyPrice)) || Number(nextBuyPrice) <= 0) {
      nextErrors.buyPrice = "请输入大于 0 的买入价。";
    }
    if (entryMode === "ocr" && !ocrFile) {
      nextErrors.ocrFile = "请先上传持仓截图，再回填表单。";
    }

    setFieldErrors(nextErrors);
    return {
      valid: Object.keys(nextErrors).length === 0,
      nextStock,
      nextBuyDate,
      nextPosition,
      nextBuyPrice,
    };
  }

  async function fetchPlans() {
    const response = await fetch(`${API_BASE}/api/watch/plans`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "读取预案失败");
    }
    return (payload.plans || []) as WatchPlan[];
  }

  async function refreshPlans() {
    const nextPlans = await fetchPlans();
    setPlans(nextPlans);
    return nextPlans;
  }

  async function fetchVoiceSettings() {
    const response = await fetch(`${API_BASE}/api/watch/voice-settings`);
    const payload = (await response.json()) as VoiceSettingsPayload & { error?: string };
    if (!response.ok) {
      throw new Error(payload.error || "读取语音设置失败");
    }
    return payload;
  }

  async function pollNow(silent = false) {
    const response = await fetch(`${API_BASE}/api/watch/poll`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const payload = (await response.json()) as PollPayload & { error?: string };
    if (!response.ok) {
      throw new Error(payload.error || "轮询失败");
    }
    setPlans(payload.plans || []);
    setQuotes(payload.quotes || []);
    setErrors(payload.errors || []);
    if (payload.events?.length) {
      setEvents((current) => {
        const seen = new Set<string>();
        return [...payload.events, ...current]
          .filter((item) => {
            if (seen.has(item.key)) return false;
            seen.add(item.key);
            return true;
          })
          .slice(0, 20);
      });
      if (!silent) showToast(`收到 ${payload.events.length} 条新提醒。`);
    } else if (!silent) {
      showToast("当前没有新的触发提醒。");
    }
  }

  async function handleGeneratePlan() {
    const validation = validateEntryForm();
    if (!validation.valid) {
      showToast("请先补全必填信息。");
      return;
    }

    setLoadingPlans(true);
    try {
      const response = await fetch(`${API_BASE}/api/watch/plans`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stock_name: validation.nextStock,
          buy_date: validation.nextBuyDate,
          position: validation.nextPosition,
          buy_price: Number(validation.nextBuyPrice),
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "预案生成失败");
      }
      setPlans((current) => [payload.plan, ...current.filter((item) => item.plan_id !== payload.plan.plan_id)]);
      showToast("次日预案已生成，正在切换到预案结果视图。");
      router.push(`/watch?planId=${encodeURIComponent(payload.plan.plan_id)}`);
    } catch (error) {
      showToast(error instanceof Error ? error.message : "预案生成失败");
    } finally {
      setLoadingPlans(false);
    }
  }

  async function handleOcrFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setOcrFile(file);
    clearFieldError("ocrFile");
    setOcrStatus(`已选择 ${file.name}，正在识别。`);
    setOcrParsing(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`${API_BASE}/api/watch/ocr`, {
        method: "POST",
        body: formData,
      });
      const payload = (await response.json()) as WatchOcrPayload;
      if (!response.ok) {
        throw new Error(payload.error || "OCR 识别失败");
      }
      const fields = payload.fields;
      setStockName(fields.stock_name || "");
      setBuyDate(fields.buy_date || "");
      setPosition(normalizePositionOption(fields.position));
      setBuyPrice(fields.buy_price || "");
      setOcrStatus(fields.note || "识别结果已回填，请核对后生成预案。");
      setFieldErrors({});
      showToast("OCR 识别完成，结果已回填。");
    } catch (error) {
      setOcrStatus(error instanceof Error ? error.message : "OCR 识别失败");
      setFieldErrors((current) => ({
        ...current,
        ocrFile: error instanceof Error ? error.message : "OCR 识别失败，请重试。",
      }));
    } finally {
      setOcrParsing(false);
    }
  }

  async function handleSaveVoiceSettings(next?: VoiceSettings) {
    const payload = next || voiceSettings;
    setSavingVoice(true);
    try {
      const response = await fetch(`${API_BASE}/api/watch/voice-settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = (await response.json()) as VoiceSettingsPayload & { error?: string };
      if (!response.ok) {
        throw new Error(result.error || "保存语音设置失败");
      }
      setVoiceSettings(result.settings);
      setVoiceOptions(result.options);
      showToast("语音设置已保存。");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "保存语音设置失败");
    } finally {
      setSavingVoice(false);
    }
  }

  async function handlePreviewVoice() {
    setPreviewingVoice(true);
    try {
      const response = await fetch(`${API_BASE}/api/watch/voice-preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(voiceSettings),
      });
      const payload = (await response.json()) as {
        voice_line: string;
        audio_url?: string;
        provider?: string;
        voice?: string;
        error?: string;
      };
      if (!response.ok) {
        throw new Error(payload.error || "试听失败");
      }
      const audioUrl = payload.audio_url ? `${API_BASE}${payload.audio_url}` : "";
      if (audioUrl) {
        const audio = new Audio(audioUrl);
        audio.play().catch(() => fallbackSpeak(payload.voice_line, voiceSettings.fallback_browser_voice_hint));
      } else {
        fallbackSpeak(payload.voice_line, voiceSettings.fallback_browser_voice_hint);
      }
      showToast(`正在试听 ${payload.provider === "edge" ? "Edge" : "OpenAI"} 音色：${payload.voice || ""}`.trim());
    } catch (error) {
      showToast(error instanceof Error ? error.message : "试听失败");
    } finally {
      setPreviewingVoice(false);
    }
  }

  async function handleClearPlans() {
    try {
      const response = await fetch(`${API_BASE}/api/watch/plans/clear`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "清空预案失败");
      }
      setPlans([]);
      setQuotes([]);
      setEvents([]);
      setErrors([]);
      setPlanListOpen(false);
      showToast("预案列表已清空。");
      if (viewMode === "result") {
        router.push("/watch");
      }
    } catch (error) {
      showToast(error instanceof Error ? error.message : "清空预案失败");
    }
  }

  function openCalendarPicker() {
    const picker = calendarInputRef.current as HTMLInputElement & { showPicker?: () => void };
    if (picker?.showPicker) {
      picker.showPicker();
      return;
    }
    picker?.click();
  }

  function goToPlan(planId: string) {
    setPlanListOpen(false);
    router.push(`/watch?planId=${encodeURIComponent(planId)}`);
  }

  function handlePreviewTrackTransitionEnd() {
    if (!previewLoopEnabled) return;
    if (previewPlanOffset < plans.length) return;
    setPreviewPlanTrackAnimated(false);
    setPreviewPlanOffset(0);
  }

  useEffect(() => {
    setPolling(viewMode === "result");
  }, [viewMode]);

  useEffect(() => {
    let active = true;

    (async () => {
      try {
        const [nextPlans, nextVoice] = await Promise.all([fetchPlans(), fetchVoiceSettings()]);
        if (active) {
          setPlans(nextPlans);
          setVoiceSettings(nextVoice.settings);
          setVoiceOptions(nextVoice.options);
        }
      } catch (error) {
        if (active) {
          showToast(error instanceof Error ? error.message : "初始化失败");
        }
      } finally {
        if (active) {
          setLoadingInitialPlans(false);
        }
      }
    })();

    if (viewMode === "result") {
      pollNow(true).catch(() => undefined);
    }

    return () => {
      active = false;
      if (toastTimer.current) {
        window.clearTimeout(toastTimer.current);
      }
    };
  }, [viewMode]);

  useEffect(() => {
    if (viewMode !== "result" || !polling) return;
    const interval = window.setInterval(() => {
      pollNow(true).catch(() => undefined);
    }, 20000);
    return () => window.clearInterval(interval);
  }, [viewMode, polling]);

  useEffect(() => {
    if (viewMode !== "result") return;
    const fresh = events.find((item) => !playedKeys.current.has(item.key));
    if (!fresh) return;
    playedKeys.current.add(fresh.key);
    const audioUrl = fresh.audio_url ? `${API_BASE}${fresh.audio_url}` : "";
    if (audioUrl) {
      const audio = new Audio(audioUrl);
      audio.play().catch(() => fallbackSpeak(fresh.voice_line || fresh.message, voiceSettings.fallback_browser_voice_hint));
      return;
    }
    fallbackSpeak(fresh.voice_line || fresh.message, voiceSettings.fallback_browser_voice_hint);
  }, [events, viewMode, voiceSettings.fallback_browser_voice_hint]);

  useEffect(() => {
    if (viewMode !== "entry") return;

    let frame = 0;
    const updatePreviewPlanLimit = () => {
      const height = entryFormRef.current?.offsetHeight || 0;
      let nextLimit = 2;
      if (height >= 1120) {
        nextLimit = 4;
      } else if (height >= 920) {
        nextLimit = 3;
      }
      setPreviewPlanLimit((current) => (current === nextLimit ? current : nextLimit));
    };

    const schedule = () => {
      if (frame) window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(updatePreviewPlanLimit);
    };

    schedule();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(schedule) : null;
    if (observer && entryFormRef.current) {
      observer.observe(entryFormRef.current);
    }
    window.addEventListener("resize", schedule);

    return () => {
      window.removeEventListener("resize", schedule);
      observer?.disconnect();
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [viewMode]);

  useEffect(() => {
    if (viewMode !== "entry") return;

    let frame = 0;
    const updatePreviewStageHeight = () => {
      setPreviewStageHeight(previewStageRef.current?.offsetHeight || 0);
    };
    const schedule = () => {
      if (frame) window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(updatePreviewStageHeight);
    };

    schedule();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(schedule) : null;
    if (observer && previewStageRef.current) {
      observer.observe(previewStageRef.current);
    }
    window.addEventListener("resize", schedule);

    return () => {
      window.removeEventListener("resize", schedule);
      observer?.disconnect();
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [viewMode, previewPlanLimit, loadingPlans]);

  useEffect(() => {
    setPreviewPlanPaused(false);
    setPreviewPlanTrackAnimated(false);
    setPreviewPlanOffset(0);
  }, [viewMode, plans.length, previewPlanLimit]);

  useEffect(() => {
    if (!previewLoopEnabled || previewPlanPaused) return;
    const timer = window.setInterval(() => {
      setPreviewPlanTrackAnimated(true);
      setPreviewPlanOffset((current) => current + 1);
    }, PREVIEW_PLAN_ROTATE_MS);
    return () => window.clearInterval(timer);
  }, [previewLoopEnabled, previewPlanPaused]);

  return (
    <main className="review-entry review-entry-dashboard watch-dashboard-page">
      <aside className="review-entry-sidebar">
        <Link className="review-entry-brand" href="/">
          <span><Triangle /></span>
          <b>AI Trading</b>
          <em>Pro</em>
        </Link>

        <nav className="review-entry-menu review-function-cards" aria-label="核心功能">
          <Link href="/review">
            <BriefcaseBusiness />
            <span>
              <b>AI 复盘</b>
              <small>上传交割单，生成交易复盘</small>
            </span>
          </Link>
          <Link className="active" href={requestedPlanId ? `/watch?planId=${encodeURIComponent(requestedPlanId)}` : "/watch"}>
            <Radar />
            <span>
              <b>AI 盯盘</b>
              <small>把复盘结论变成盘中预案</small>
            </span>
          </Link>
        </nav>

        <div className="review-side-hint">支持手动填写或上传持仓截图回填，系统会自动整理次日关键价位和盘中提醒。</div>
      </aside>

      <section className="review-entry-main watch-dashboard-main">
        <header className="review-entry-topbar watch-dashboard-topbar">
          <div className="watch-dashboard-topbar-left">
            <Link className="watch-v2-nav-button watch-home-link" href="/">
              <ChevronLeft className="h-4 w-4" />
              返回主页
            </Link>
          </div>
          <div className="watch-v2-nav-actions watch-dashboard-actions">
            {viewMode === "result" ? (
              <button className="watch-v2-nav-button" type="button" onClick={() => router.push("/watch")}>
                <ChevronLeft className="h-4 w-4" />
                重新生成
              </button>
            ) : null}
            <button
              className="watch-v2-nav-button"
              type="button"
              onClick={() => {
                refreshPlans().catch(() => undefined);
                setPlanListOpen(true);
              }}
            >
              <List className="h-4 w-4" />
              预案列表
            </button>
            <button className="watch-v2-nav-button" type="button" onClick={() => setSettingsOpen(true)}>
              <Settings2 className="h-4 w-4" />
              设置
            </button>
          </div>
        </header>

        {viewMode === "entry" ? (
          <>
            <section className="review-entry-hero watch-dashboard-hero">
              <h1>AI 盯盘预案 <Sparkles /></h1>
              <p>录入你的持仓信息，AI 会生成次日预案，并在观察日按规则推送消息和语音提醒。</p>
            </section>

          <section className="watch-entry-grid">
            <section ref={entryFormRef} className="panel watch-entry-card watch-entry-form-card">
              <div className="watch-entry-step">
                <span>1</span>
                <div>
                  <h2>填写你的持仓</h2>
                  <p>先录入股票名称、买入时间、仓位和买入价。你也可以先用 OCR 从截图里回填，再逐项确认。</p>
                </div>
              </div>

              <div className="watch-entry-mode-switch" role="tablist" aria-label="填写方式">
                <button
                  className={`watch-entry-mode-button ${entryMode === "manual" ? "active" : ""}`}
                  type="button"
                  onClick={() => setEntryMode("manual")}
                >
                  <PencilLine className="h-4 w-4" />
                  手动填写
                </button>
                <button
                  className={`watch-entry-mode-button ${entryMode === "ocr" ? "active" : ""}`}
                  type="button"
                  onClick={() => setEntryMode("ocr")}
                >
                  <ImageUp className="h-4 w-4" />
                  OCR 填表
                </button>
              </div>

              {entryMode === "ocr" ? (
                <div className="watch-ocr-box">
                  <input
                    ref={ocrInputRef}
                    type="file"
                    hidden
                    accept="image/png,image/jpeg,image/jpg,image/webp"
                    onChange={handleOcrFileChange}
                  />
                  <button className="watch-ocr-upload" type="button" onClick={() => ocrInputRef.current?.click()} disabled={ocrParsing}>
                    <ImageUp className="h-6 w-6" />
                    <b>{ocrParsing ? "正在识别截图" : ocrFile ? "重新上传持仓截图" : "上传持仓截图"}</b>
                    <span>支持 jpg / png / webp。系统会调用 OpenAI OCR 抽取股票、买入时间、仓位和买入价，并自动回填到下方。</span>
                  </button>
                  {ocrStatus ? <p className="watch-ocr-status">{ocrStatus}</p> : null}
                  {fieldErrors.ocrFile ? <p className="watch-entry-error">{fieldErrors.ocrFile}</p> : null}
                </div>
              ) : null}

              <div className="watch-search-input">
                <Search className="h-5 w-5" />
                <input
                  value={stockName}
                  onChange={(event) => {
                    setStockName(event.target.value);
                    clearFieldError("stockName");
                  }}
                  placeholder="例如：长电科技 600584"
                  autoComplete="off"
                />
                {stockName ? (
                  <button type="button" aria-label="清空股票名称" onClick={() => { setStockName(""); clearFieldError("stockName"); }}>
                    <X className="h-4 w-4" />
                  </button>
                ) : null}
              </div>
              {fieldErrors.stockName ? <p className="watch-entry-error">{fieldErrors.stockName}</p> : null}

              <div className="watch-entry-fields">
                <label className="watch-entry-field">
                  <span>买入时间</span>
                  <div className="watch-date-input">
                    <input
                      value={buyDate}
                      onChange={(event) => {
                        setBuyDate(event.target.value);
                        clearFieldError("buyDate");
                      }}
                      onBlur={() => {
                        setBuyDate((current) => normalizeDisplayDate(current));
                      }}
                      placeholder="DD/MM/YY"
                      inputMode="numeric"
                    />
                    <button type="button" aria-label="选择买入时间" onClick={openCalendarPicker}>
                      <CalendarDays className="h-4 w-4" />
                    </button>
                    <input
                      ref={calendarInputRef}
                      className="watch-hidden-calendar"
                      type="date"
                      tabIndex={-1}
                      aria-hidden="true"
                      value={displayToIsoDate(buyDate)}
                      onChange={(event) => {
                        setBuyDate(isoToDisplayDate(event.target.value));
                        clearFieldError("buyDate");
                      }}
                    />
                  </div>
                  {fieldErrors.buyDate ? <p className="watch-entry-error">{fieldErrors.buyDate}</p> : null}
                </label>

                <label className="watch-entry-field">
                  <span>当前仓位</span>
                  <select
                    value={position}
                    onChange={(event) => {
                      setPosition(event.target.value);
                      clearFieldError("position");
                    }}
                  >
                    <option value="">请选择仓位</option>
                    {POSITION_OPTIONS.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                  {fieldErrors.position ? <p className="watch-entry-error">{fieldErrors.position}</p> : null}
                </label>
              </div>

              <div className="watch-entry-step watch-entry-step-optional">
                <span>2</span>
                <div>
                  <h3>确认持仓成本</h3>
                  <p>买入价现在是必填项。无论是手动录入还是 OCR 回填，都请你核对后再生成预案。</p>
                </div>
              </div>

              <label className="watch-entry-field">
                <span>买入价</span>
                <div className="watch-amount-input">
                  <input
                    value={buyPrice}
                    onChange={(event) => {
                      setBuyPrice(event.target.value);
                      clearFieldError("buyPrice");
                    }}
                    placeholder="请输入买入价"
                    inputMode="decimal"
                  />
                  <em>元</em>
                </div>
                {fieldErrors.buyPrice ? <p className="watch-entry-error">{fieldErrors.buyPrice}</p> : null}
              </label>

              <button className="button watch-v2-submit" type="button" onClick={handleGeneratePlan} disabled={loadingPlans}>
                <Sparkles className="h-4 w-4" />
                {loadingPlans ? "正在生成明日预案" : "生成明日预案"}
              </button>
              <p className="watch-entry-hint">通常 10 - 20 秒即可完成分析，生成后会直接展示次日预案。</p>
            </section>

            {loadingPlans ? (
              <section className="panel watch-entry-card review-report-loading watch-generate-loading">
                <div className="review-report-orbit">
                  <span />
                  <span />
                  <span />
                </div>
                <h2>正在生成次日预案</h2>
                <p>系统正在结合走势和你的持仓信息整理次日计划，稍等片刻即可查看关键价位和操作建议。</p>
              </section>
            ) : (
              <section className="panel watch-entry-card watch-entry-preview-card">
                <div className="watch-entry-preview-head">
                  <div className="tag">
                    <Sparkles className="h-4 w-4" />
                    生成结果预览
                  </div>
                </div>

                <div className="watch-preview-feature-grid">
                  {PREVIEW_FEATURES.map(([title, text]) => (
                    <article className="watch-preview-feature" key={title}>
                      <b>{title}</b>
                      <span>{text}</span>
                    </article>
                  ))}
                </div>

                <div className="watch-preview-list-head">
                  <h3>最近保存的预案</h3>
                  <button className="watch-inline-link" type="button" onClick={() => setPlanListOpen(true)}>
                    查看全部
                  </button>
                </div>

                {plans.length ? (
                  <div
                    ref={previewStageRef}
                    className={`watch-preview-plan-marquee ${previewLoopEnabled ? "is-looping" : ""}`}
                    style={previewPlanTrackStyle}
                    onMouseEnter={() => setPreviewPlanPaused(true)}
                    onMouseLeave={() => setPreviewPlanPaused(false)}
                    onFocusCapture={() => setPreviewPlanPaused(true)}
                    onBlurCapture={() => setPreviewPlanPaused(false)}
                  >
                    <div
                      className={`watch-preview-plan-track ${previewPlanTrackAnimated ? "" : "no-transition"}`}
                      onTransitionEnd={handlePreviewTrackTransitionEnd}
                    >
                      {previewPlansToRender.map((plan, index) => (
                        <button className="watch-preview-plan" type="button" key={`${plan.plan_id}-${index}`} onClick={() => goToPlan(plan.plan_id)}>
                          <div>
                            <b>
                              {plan.name} <small>{plan.code}</small>
                            </b>
                            <span>{plan.watch_date || "观察日待确认"} · {plan.position || "仓位待补充"}</span>
                          </div>
                          <p>{shortText(plan.thesis, 72)}</p>
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="watch-empty watch-entry-empty">
                    <b>还没有已保存的预案</b>
                    <span>填写左侧信息后，这里会自动显示你最近生成的次日预案。</span>
                  </div>
                )}
              </section>
            )}
          </section>
          </>
        ) : loadingInitialPlans ? (
          <section className="panel review-report-loading watch-result-loading">
            <div className="review-report-orbit">
              <span />
              <span />
              <span />
            </div>
            <h2>正在读取你的预案</h2>
            <p>系统正在加载已保存的次日预案和盘中提醒状态。</p>
          </section>
        ) : selectedPlan ? (
          <div className="watch-result-stack">
            <section className="panel watch-result-hero">
              <div className="watch-result-hero-head">
                <div>
                  <div className="tag">
                    <Sparkles className="h-4 w-4" />
                    AI 明日预案
                  </div>
                  <h2>
                    {selectedPlan.name} <small>{selectedPlan.code}</small>
                  </h2>
                  <p>{selectedPlan.thesis}</p>
                </div>
                <div className="watch-phase-card" data-tone={watchPhase?.tone}>
                  <strong>{watchPhase?.label}</strong>
                  <span>{watchPhase?.detail}</span>
                </div>
              </div>

              <div className="watch-summary-callout">
                <b>AI 总结</b>
                <p>{selectedPlan.thesis}</p>
              </div>

              <div className="watch-key-grid-v2">
                {keyLevels.map((item) => (
                  <article className="watch-key-card" key={item.label} data-tone={item.tone}>
                    <span>{item.label}</span>
                    <strong>{fmtPrice(item.value)}</strong>
                  </article>
                ))}
              </div>

              <div className="watch-action-panel">
                <h3>明日操作预案</h3>
                <ul>
                  {actionLines.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </div>

              <div className="watch-result-actions">
                <button className="button watch-v2-submit" type="button" onClick={() => setPolling((value) => !value)}>
                  {polling ? <PauseCircle className="h-4 w-4" /> : <PlayCircle className="h-4 w-4" />}
                  {polling ? "暂停盯盘提醒" : "开始盯盘提醒"}
                </button>
                <button className="button secondary" type="button" onClick={() => pollNow().catch((error) => showToast(error instanceof Error ? error.message : "刷新失败"))}>
                  <RefreshCcw className="h-4 w-4" />
                  立即刷新
                </button>
                <button className="button secondary" type="button" onClick={() => setSettingsOpen(true)}>
                  <Volume2 className="h-4 w-4" />
                  通知设置
                </button>
              </div>
              <p className="watch-result-note">预案已经保存。到观察日打开页面后，系统会按条件提醒，并尝试语音播报。</p>
            </section>

            <section className="watch-result-grid">
              <article className="panel watch-result-card">
                <div className="watch-result-card-head">
                  <Clock3 className="h-5 w-5" />
                  <div>
                    <h3>观察窗口</h3>
                    <p>{selectedPlan.watch_date || "未设置"} · {selectedPlan.position || "仓位待补充"}</p>
                  </div>
                </div>
                <div className="watch-result-stat">
                  <span>买入时间</span>
                  <strong>{selectedPlan.buy_date || "--"}</strong>
                </div>
                <div className="watch-result-stat">
                  <span>买入价</span>
                  <strong>{fmtPrice(selectedPlan.buy_price)}</strong>
                </div>
                <div className="watch-result-stat">
                  <span>语音播报</span>
                  <strong>{voiceSettings.provider === "edge" ? voiceSettings.edge_voice : voiceSettings.openai_voice}</strong>
                </div>
              </article>

              <article className="panel watch-result-card">
                <div className="watch-result-card-head">
                  <RefreshCcw className="h-5 w-5" />
                  <div>
                    <h3>盘中快照</h3>
                    <p>只展示当前预案对应标的的最新行情</p>
                  </div>
                </div>
                {selectedQuote ? (
                  <div className="watch-quote-compact">
                    <strong>{selectedQuote.price.toFixed(2)}</strong>
                    <span data-tone={selectedQuote.pct_chg >= 0 ? "up" : "down"}>{selectedQuote.pct_chg.toFixed(2)}%</span>
                    <em>{selectedQuote.quote_time}</em>
                  </div>
                ) : (
                  <div className="watch-empty watch-compact-empty">
                    <b>暂无实时快照</b>
                    <span>开启盯盘后，观察日盘中会自动拉取实时行情。</span>
                  </div>
                )}
              </article>

              <article className="panel watch-result-card">
                <div className="watch-result-card-head">
                  <BellRing className="h-5 w-5" />
                  <div>
                    <h3>提醒状态</h3>
                    <p>触发后会先推送消息，再尝试语音播报</p>
                  </div>
                </div>
                <div className="watch-result-stat">
                  <span>轮询状态</span>
                  <strong>{polling ? "已开启" : "已暂停"}</strong>
                </div>
                <div className="watch-result-stat">
                  <span>新提醒数</span>
                  <strong>{selectedEvents.length}</strong>
                </div>
                <div className="watch-result-stat">
                  <span>语音回退</span>
                  <strong>{voiceSettings.fallback_browser_voice_hint === "female" ? "浏览器偏女声" : "浏览器偏男声"}</strong>
                </div>
              </article>
            </section>

            <section className="panel watch-alert-panel watch-alert-panel-v2">
              <div className="watch-result-section-head">
                <div>
                  <h3>最新触发提醒</h3>
                  <p>提醒条件由后端规则引擎判定，触发文案和语音由 agent 生成。</p>
                </div>
                <button className="watch-inline-link" type="button" onClick={() => setPlanListOpen(true)}>
                  切换预案
                </button>
              </div>
              {errors.length ? <div className="watch-error">{errors.join("；")}</div> : null}
              <div className="watch-alert-list">
                {selectedEvents.length ? selectedEvents.map((event) => (
                  <article className="watch-alert-item" key={event.key}>
                    <b>
                      {event.name} {event.code} · {event.level}
                    </b>
                    <p>{event.message}</p>
                    <span>{event.voice_line}</span>
                    <small>音色：{event.voice_provider === "edge" ? "Edge" : "OpenAI"} · {event.voice_name || "--"}</small>
                    <small>{event.quote.quote_time}</small>
                  </article>
                )) : (
                  <div className="watch-empty">
                    <b>当前没有新提醒</b>
                    <span>观察日盘中达到条件后，会在这里追加提醒并尝试播放音频。</span>
                  </div>
                )}
              </div>
            </section>
          </div>
        ) : (
          <section className="panel watch-result-empty">
            <div className="watch-empty">
              <b>还没有可展示的预案</b>
              <span>先返回上方输入信息并生成预案，完成后就会直接展示在这里。</span>
            </div>
            <Link className="button watch-v2-submit watch-result-back" href="/watch">
              <ChevronLeft className="h-4 w-4" />
              返回盯盘输入
            </Link>
          </section>
        )}

        {(settingsOpen || planListOpen) ? <div className="watch-sheet-backdrop" onClick={() => { setSettingsOpen(false); setPlanListOpen(false); }} /> : null}

        <aside className={`watch-sheet ${settingsOpen ? "open" : ""}`} role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
          <div className="watch-sheet-head">
            <div>
              <h3>通知设置</h3>
              <p>在这里调整语音播报方式、试听文案和回退音色。</p>
            </div>
            <button type="button" aria-label="关闭设置" onClick={() => setSettingsOpen(false)}>
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="watch-sheet-body">
            <label className="watch-entry-field">
              <span>语音引擎</span>
              <select
                value={voiceSettings.provider}
                onChange={(event) => setVoiceSettings((current) => ({ ...current, provider: event.target.value as VoiceSettings["provider"] }))}
              >
                {voiceOptions.provider.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="watch-entry-field">
              <span>OpenAI 音色</span>
              <select
                value={voiceSettings.openai_voice}
                disabled={voiceSettings.provider !== "openai"}
                onChange={(event) => setVoiceSettings((current) => ({ ...current, openai_voice: event.target.value }))}
              >
                {voiceOptions.openai_voice.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="watch-entry-field">
              <span>Edge 音色</span>
              <select
                value={voiceSettings.edge_voice}
                disabled={voiceSettings.provider !== "edge"}
                onChange={(event) => setVoiceSettings((current) => ({ ...current, edge_voice: event.target.value }))}
              >
                {voiceOptions.edge_voice.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="watch-entry-field">
              <span>浏览器回退</span>
              <select
                value={voiceSettings.fallback_browser_voice_hint}
                onChange={(event) => setVoiceSettings((current) => ({ ...current, fallback_browser_voice_hint: event.target.value as VoiceSettings["fallback_browser_voice_hint"] }))}
              >
                {voiceOptions.fallback_browser_voice_hint.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="watch-entry-field">
              <span>试听文案</span>
              <textarea
                value={voiceSettings.preview_text}
                onChange={(event) => setVoiceSettings((current) => ({ ...current, preview_text: event.target.value }))}
                placeholder="输入试听文案"
                rows={4}
              />
            </label>
          </div>
          <div className="watch-sheet-actions">
            <button className="button secondary" type="button" onClick={handlePreviewVoice} disabled={previewingVoice}>
              <Volume2 className="h-4 w-4" />
              {previewingVoice ? "正在试听" : "试听当前音色"}
            </button>
            <button className="button watch-v2-submit watch-sheet-submit" type="button" onClick={() => handleSaveVoiceSettings()} disabled={savingVoice}>
              <ShieldCheck className="h-4 w-4" />
              {savingVoice ? "正在保存" : "保存设置"}
            </button>
          </div>
        </aside>

        <aside className={`watch-sheet ${planListOpen ? "open" : ""}`} role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
          <div className="watch-sheet-head">
            <div>
              <h3>我的预案列表</h3>
              <p>这里会保留已经生成的预案，方便你随时切换查看。</p>
            </div>
            <button type="button" aria-label="关闭预案列表" onClick={() => setPlanListOpen(false)}>
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="watch-sheet-body">
            {plans.length ? (
              <div className="watch-plan-list-drawer">
                {plans.map((plan) => (
                  <button className={`watch-plan-list-item ${selectedPlan?.plan_id === plan.plan_id ? "active" : ""}`} type="button" key={plan.plan_id} onClick={() => goToPlan(plan.plan_id)}>
                    <div>
                      <b>
                        {plan.name} <small>{plan.code}</small>
                      </b>
                      <span>{plan.watch_date || "未设置观察日"} · {plan.position || "仓位待补充"}</span>
                    </div>
                    <p>{shortText(plan.thesis, 92)}</p>
                  </button>
                ))}
              </div>
            ) : (
              <div className="watch-empty">
                <b>当前还没有预案</b>
                <span>回到输入页生成第一份次日预案后，这里就会出现可切换的预案列表。</span>
              </div>
            )}
          </div>
          <div className="watch-sheet-actions">
            <button className="button secondary" type="button" onClick={() => refreshPlans().catch((error) => showToast(error instanceof Error ? error.message : "刷新失败"))}>
              <RefreshCcw className="h-4 w-4" />
              刷新列表
            </button>
            <button className="button secondary" type="button" onClick={handleClearPlans}>
              清空全部预案
            </button>
          </div>
        </aside>

        {toast ? <div className="watch-toast">{toast}</div> : null}
      </section>
    </main>
  );
}
