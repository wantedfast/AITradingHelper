"use client";

import { useEffect, useMemo, useRef, useState, type ChangeEvent, type Dispatch, type RefObject, type SetStateAction } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  BarChart3,
  BellRing,
  CalendarDays,
  ChevronLeft,
  Clock3,
  FileUp,
  ImageUp,
  Info,
  List,
  Loader2,
  PauseCircle,
  PlayCircle,
  Radar,
  RefreshCcw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Volume2,
  X,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8600" : "");
const SHOW_WATCH_VOICE_TEST = process.env.NODE_ENV === "development";
const WATCH_VOICE_TEST_LINE = "贵州茅台触达风险位，请按预案控制回撤。";

const POSITION_OPTIONS = ["1 成 (10%)", "2 成 (20%)", "3 成 (30%)", "半仓 (50%)", "7 成 (70%)", "重仓 (80%)", "满仓 (100%)"];

const PREVIEW_FEATURES = [
  ["AI 总结", "自动整理交易逻辑和次日观察重点。"],
  ["关键价位", "输出观察位、突破位、目标位和风险位。"],
  ["操作预案", "把盘中应对动作整理成清晰执行步骤。"],
  ["盘中提醒", "在观察日按条件推送消息并尝试语音播报。"],
];

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

type WatchOcrPayload = {
  fields: {
    stock_name: string;
    buy_date: string;
    position: string;
    buy_price: string;
    note: string;
  };
  error?: string;
};

async function apiFetchJson<T>(path: string, init?: RequestInit, fallbackError = "请求失败"): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  const text = await response.text();
  let payload: unknown = null;
  if (text.trim()) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }
  if (!response.ok) {
    if (payload && typeof payload === "object") {
      const record = payload as { error?: unknown; detail?: unknown };
      const message = typeof record.error === "string" ? record.error : typeof record.detail === "string" ? record.detail : "";
      if (message) throw new Error(message);
    }
    const suffix = text.trim() ? `：${shortText(text.trim(), 120)}` : `（HTTP ${response.status}）`;
    throw new Error(`${fallbackError}${suffix}`);
  }
  if (!payload || typeof payload !== "object") {
    throw new Error(text.trim() ? `${fallbackError}：响应不是 JSON` : `${fallbackError}：响应为空`);
  }
  return payload as T;
}

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
  if (typeof window === "undefined") return;
  if (!("speechSynthesis" in window)) {
    recordWatchSpeechTestCall(text);
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "zh-CN";
  utterance.rate = 1.02;
  utterance.pitch = 1.06;
  const voices = window.speechSynthesis.getVoices();
  const ranked = voices
    .filter((voice) => /zh|chinese|mandarin/i.test(`${voice.lang} ${voice.name}`))
    .sort((left, right) => scoreBrowserVoice(`${right.name} ${right.lang}`, hint) - scoreBrowserVoice(`${left.name} ${left.lang}`, hint));
  if (ranked[0]) utterance.voice = ranked[0];
  recordWatchSpeechTestCall(text);
  window.speechSynthesis.speak(utterance);
}

function recordWatchSpeechTestCall(text: string) {
  if (!watchSpeechTestEnabled()) return;
  const attr = "data-watch-speech-calls";
  const current = document.documentElement.getAttribute(attr);
  let calls: string[] = [];
  if (current) {
    try {
      const parsed = JSON.parse(current);
      if (Array.isArray(parsed)) calls = parsed.filter((item): item is string => typeof item === "string");
    } catch {
      calls = [];
    }
  }
  document.documentElement.setAttribute(attr, JSON.stringify([...calls, text]));
}

function watchSpeechTestEnabled() {
  if (typeof window === "undefined") return false;
  return window.location.search.includes("watchSpeechTest=1");
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
  return `${today.getFullYear()}-${`${today.getMonth() + 1}`.padStart(2, "0")}-${`${today.getDate()}`.padStart(2, "0")}`;
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
  const year = slashMatch[3].length === 2 ? `20${slashMatch[3]}` : slashMatch[3];
  return `${year}-${slashMatch[2]}-${slashMatch[1]}`;
}

function normalizeDisplayDate(value: string) {
  const iso = displayToIsoDate(value);
  return iso ? isoToDisplayDate(iso) : value;
}

function normalizePositionOption(value: string) {
  const text = value.trim();
  return POSITION_OPTIONS.includes(text) ? text : "";
}

function isTradingSessionNow() {
  const now = new Date();
  const hourMinute = now.getHours() * 100 + now.getMinutes();
  return (hourMinute >= 930 && hourMinute <= 1130) || (hourMinute >= 1300 && hourMinute <= 1500);
}

function shortText(text: string, limit = 78) {
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
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
      detail: "系统会在观察日的交易时段按预案轮询，并推送触发提醒。",
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

function buildPlanActionLines(plan: WatchPlan) {
  const lines: string[] = [];
  if (typeof plan.breakout === "number") lines.push(`若股价放量突破 ${fmtPrice(plan.breakout)}，优先按「${plan.action || "顺势执行"}」处理。`);
  if (typeof plan.reference_price === "number") lines.push(`若盘中围绕观察位 ${fmtPrice(plan.reference_price)} 反复拉锯，重点看承接和量能是否同步改善。`);
  if (typeof plan.take_profit === "number") lines.push(`若拉升接近目标位 ${fmtPrice(plan.take_profit)}，优先按纪律兑现部分利润，不再临盘犹豫。`);
  if (typeof plan.breakdown === "number") lines.push(`若跌破失效位 ${fmtPrice(plan.breakdown)}，说明预案弱化，需要重新评估强度。`);
  else if (typeof plan.stop_loss === "number") lines.push(`若跌破止损位 ${fmtPrice(plan.stop_loss)}，趋势失效，及时控制风险。`);
  if (!lines.length) lines.push(plan.action || "按计划观察次日强弱变化。");
  return lines;
}

function keyLevelsForPlan(plan: WatchPlan) {
  return [
    { label: "支撑位", value: plan.breakdown ?? plan.stop_loss ?? null, tone: "support" },
    { label: "观察位", value: plan.reference_price ?? null, tone: "observe" },
    { label: "压力位", value: plan.breakout ?? null, tone: "resistance" },
    { label: "目标位", value: plan.take_profit ?? null, tone: "target" },
    { label: "止损位", value: plan.stop_loss ?? plan.breakdown ?? null, tone: "stop" },
  ];
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
  const [polling, setPolling] = useState(viewMode === "result");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [planListOpen, setPlanListOpen] = useState(false);
  const [toast, setToast] = useState("");

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

  function showToast(text: string) {
    setToast(text);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(""), 2600);
  }

  function handleTestVoiceAlert() {
    showToast(`测试语音提醒：${WATCH_VOICE_TEST_LINE}`);
    fallbackSpeak(WATCH_VOICE_TEST_LINE, voiceSettings.fallback_browser_voice_hint);
  }

  function clearFieldError(field: keyof WatchFormErrors) {
    setFieldErrors((current) => (current[field] ? { ...current, [field]: "" } : current));
  }

  function validateEntryForm() {
    const nextErrors: WatchFormErrors = {};
    const nextStock = stockName.trim();
    const nextBuyDate = buyDate.trim();
    const nextPosition = position.trim();
    const nextBuyPrice = buyPrice.trim();
    if (!nextStock) nextErrors.stockName = "请填写股票名称。";
    if (!nextBuyDate) nextErrors.buyDate = "请填写买入时间。";
    else if (!displayToIsoDate(nextBuyDate)) nextErrors.buyDate = "请按 DD/MM/YY 输入，或使用日历选择。";
    if (!nextPosition) nextErrors.position = "请选择当前仓位。";
    if (!nextBuyPrice) nextErrors.buyPrice = "请填写买入价。";
    else if (Number.isNaN(Number(nextBuyPrice)) || Number(nextBuyPrice) <= 0) nextErrors.buyPrice = "请输入大于 0 的买入价。";
    if (entryMode === "ocr" && !ocrFile) nextErrors.ocrFile = "请先上传持仓截图，再回填表单。";
    setFieldErrors(nextErrors);
    return { valid: Object.keys(nextErrors).length === 0, nextStock, nextBuyDate, nextPosition, nextBuyPrice };
  }

  async function fetchPlans() {
    const payload = await apiFetchJson<{ plans?: WatchPlan[] }>("/api/watch/plans", undefined, "读取预案失败");
    return (payload.plans || []) as WatchPlan[];
  }

  async function refreshPlans() {
    const nextPlans = await fetchPlans();
    setPlans(nextPlans);
    return nextPlans;
  }

  async function fetchVoiceSettings() {
    return apiFetchJson<VoiceSettingsPayload>("/api/watch/voice-settings", undefined, "读取语音设置失败");
  }

  async function pollNow(silent = false) {
    const payload = await apiFetchJson<PollPayload>("/api/watch/poll", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    }, "轮询失败");
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
      const payload = await apiFetchJson<{ plan: WatchPlan; plans?: WatchPlan[] }>("/api/watch/plans", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stock_name: validation.nextStock,
          buy_date: validation.nextBuyDate,
          position: validation.nextPosition,
          buy_price: Number(validation.nextBuyPrice),
        }),
      }, "预案生成失败");
      setPlans((current) => [payload.plan, ...current.filter((item) => item.plan_id !== payload.plan.plan_id)]);
      showToast("次日预案已生成，正在切换到预案结果视图。");
      const testSuffix = watchSpeechTestEnabled() ? "&watchSpeechTest=1" : "";
      router.push(`/watch?planId=${encodeURIComponent(payload.plan.plan_id)}${testSuffix}`);
    } catch (error) {
      showToast(error instanceof Error ? error.message : "预案生成失败");
    } finally {
      setLoadingPlans(false);
    }
  }

  async function handleOcrFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setOcrFile(file);
    clearFieldError("ocrFile");
    setOcrStatus(`已选择 ${file.name}，正在识别。`);
    setOcrParsing(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const payload = await apiFetchJson<WatchOcrPayload>("/api/watch/ocr", { method: "POST", body: formData }, "OCR 识别失败");
      setStockName(payload.fields.stock_name || "");
      setBuyDate(payload.fields.buy_date || "");
      setPosition(normalizePositionOption(payload.fields.position));
      setBuyPrice(payload.fields.buy_price || "");
      setOcrStatus(payload.fields.note || "识别结果已回填，请核对后生成预案。");
      setFieldErrors({});
      showToast("OCR 识别完成，结果已回填。");
    } catch (error) {
      const message = error instanceof Error ? error.message : "OCR 识别失败，请重试。";
      setOcrStatus(message);
      setFieldErrors((current) => ({ ...current, ocrFile: message }));
    } finally {
      setOcrParsing(false);
    }
  }

  async function handleSaveVoiceSettings(next?: VoiceSettings) {
    const payload = next || voiceSettings;
    setSavingVoice(true);
    try {
      const result = await apiFetchJson<VoiceSettingsPayload>("/api/watch/voice-settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }, "保存语音设置失败");
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
      const payload = await apiFetchJson<{ voice_line: string; audio_url?: string; provider?: string; voice?: string }>("/api/watch/voice-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(voiceSettings),
      }, "试听失败");
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
      await apiFetchJson<{ plans?: WatchPlan[] }>("/api/watch/plans/clear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      }, "清空预案失败");
      setPlans([]);
      setQuotes([]);
      setEvents([]);
      setErrors([]);
      setPlanListOpen(false);
      showToast("预案列表已清空。");
      if (viewMode === "result") router.push("/watch");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "清空预案失败");
    }
  }

  function openCalendarPicker() {
    const picker = calendarInputRef.current as HTMLInputElement & { showPicker?: () => void };
    if (picker?.showPicker) picker.showPicker();
    else picker?.click();
  }

  function goToPlan(planId: string) {
    setPlanListOpen(false);
    router.push(`/watch?planId=${encodeURIComponent(planId)}`);
  }

  useEffect(() => {
    setPolling(viewMode === "result");
    // pollNow closes over current state setters only; including it would restart initialization on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      } catch {
        if (active) {
          setPlans([]);
          setVoiceOptions(FALLBACK_VOICE_OPTIONS);
        }
      } finally {
        if (active) setLoadingInitialPlans(false);
      }
    })();

    if (viewMode === "result") pollNow(true).catch(() => undefined);
    return () => {
      active = false;
      if (toastTimer.current) window.clearTimeout(toastTimer.current);
    };
    // pollNow closes over current state setters only; including it would restart initialization on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewMode]);

  useEffect(() => {
    if (viewMode !== "result" || !polling) return;
    const interval = window.setInterval(() => {
      pollNow(true).catch(() => undefined);
    }, 20000);
    return () => window.clearInterval(interval);
    // Keep the interval tied to view mode and the polling toggle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewMode, polling]);

  useEffect(() => {
    if (viewMode !== "result") return;
    const fresh = events.find((item) => !playedKeys.current.has(item.key));
    if (!fresh) return;
    playedKeys.current.add(fresh.key);
    const speechText = fresh.voice_line || fresh.message;
    const audioUrl = fresh.audio_url ? `${API_BASE}${fresh.audio_url}` : "";
    if (audioUrl) {
      const audio = new Audio(audioUrl);
      audio.play().catch(() => fallbackSpeak(speechText, voiceSettings.fallback_browser_voice_hint));
      return;
    }
    fallbackSpeak(speechText, voiceSettings.fallback_browser_voice_hint);
  }, [events, viewMode, voiceSettings.fallback_browser_voice_hint]);

  return (
    <main className="review-workbench-page watch-terminal-page">
      <aside className="review-workbench-rail">
        <Link className="review-workbench-brand" href="/">
          <span className="brand-mark">盈</span>
          <span>
            <b>盈航</b>
            <small>WATCH TERMINAL</small>
          </span>
        </Link>
        <nav className="review-workbench-nav" aria-label="核心功能">
          <Link href="/review">
            <FileUp />
            <span>
              <b>AI 复盘</b>
            </span>
          </Link>
          <Link className="active" href={requestedPlanId ? `/watch?planId=${encodeURIComponent(requestedPlanId)}` : "/watch"}>
            <BarChart3 />
            <span>
              <b>AI 盯盘</b>
            </span>
          </Link>
        </nav>
        <div className="review-rail-note">
          <Info />
          <span>把复盘结论沉淀为盘中预案，用纪律替代临盘情绪。</span>
        </div>
      </aside>

      <section className="review-workbench-main">
        <header className="review-workbench-topbar">
          <div className="review-topbar-title">
            <span className="topbar-icon">
              <Radar />
            </span>
            <b>AI 盯盘预案</b>
            <i>LIVE</i>
          </div>
          <div className="review-workbench-actions">
            <button type="button" onClick={() => router.push("/")}>
              <ChevronLeft />
              <span>首页</span>
            </button>
            {viewMode === "result" ? (
              <button type="button" onClick={() => router.push("/watch")}>
                <RefreshCcw />
                <span>重新生成</span>
              </button>
            ) : null}
            <button type="button" onClick={() => { refreshPlans().catch(() => undefined); setPlanListOpen(true); }}>
              <List />
              <span>预案列表</span>
            </button>
            {SHOW_WATCH_VOICE_TEST ? (
              <button type="button" onClick={handleTestVoiceAlert}>
                <Volume2 />
                <span>测试语音提醒</span>
              </button>
            ) : null}
            <button type="button" onClick={() => setSettingsOpen(true)}>
              <Settings2 />
              <span>设置</span>
            </button>
          </div>
        </header>

        {viewMode === "entry" ? (
          <WatchEntryView
            entryMode={entryMode}
            setEntryMode={setEntryMode}
            stockName={stockName}
            setStockName={setStockName}
            buyDate={buyDate}
            setBuyDate={setBuyDate}
            position={position}
            setPosition={setPosition}
            buyPrice={buyPrice}
            setBuyPrice={setBuyPrice}
            fieldErrors={fieldErrors}
            clearFieldError={clearFieldError}
            loadingPlans={loadingPlans}
            ocrFile={ocrFile}
            ocrStatus={ocrStatus}
            ocrParsing={ocrParsing}
            ocrInputRef={ocrInputRef}
            calendarInputRef={calendarInputRef}
            openCalendarPicker={openCalendarPicker}
            handleOcrFileChange={handleOcrFileChange}
            handleGeneratePlan={handleGeneratePlan}
            plans={plans}
            goToPlan={goToPlan}
            setPlanListOpen={setPlanListOpen}
          />
        ) : loadingInitialPlans ? (
          <section className="research-panel watch-loading-panel">
            <Loader2 className="spin-icon" />
            <h2>正在读取你的预案</h2>
            <p>系统正在加载已保存的次日预案和盘中提醒状态。</p>
          </section>
        ) : selectedPlan ? (
          <WatchResultView
            selectedPlan={selectedPlan}
            selectedQuote={selectedQuote}
            selectedEvents={selectedEvents}
            watchPhase={watchPhase}
            keyLevels={keyLevels}
            actionLines={actionLines}
            polling={polling}
            setPolling={setPolling}
            voiceSettings={voiceSettings}
            pollNow={pollNow}
            showToast={showToast}
            setSettingsOpen={setSettingsOpen}
            setPlanListOpen={setPlanListOpen}
            errors={errors}
          />
        ) : (
          <section className="research-panel watch-result-empty">
            <div className="watch-empty">
              <b>还没有可展示的预案</b>
              <span>先返回输入页生成第一份次日预案，完成后会直接展示在这里。</span>
            </div>
            <Link className="button watch-v2-submit watch-result-back" href="/watch">
              <ChevronLeft className="h-4 w-4" />
              返回盯盘输入
            </Link>
          </section>
        )}

        {(settingsOpen || planListOpen) ? <div className="watch-sheet-backdrop" onClick={() => { setSettingsOpen(false); setPlanListOpen(false); }} /> : null}

        <VoiceSettingsSheet
          open={settingsOpen}
          voiceSettings={voiceSettings}
          setVoiceSettings={setVoiceSettings}
          voiceOptions={voiceOptions}
          savingVoice={savingVoice}
          previewingVoice={previewingVoice}
          handlePreviewVoice={handlePreviewVoice}
          handleSaveVoiceSettings={handleSaveVoiceSettings}
          close={() => setSettingsOpen(false)}
        />

        <PlanListSheet
          open={planListOpen}
          plans={plans}
          selectedPlan={selectedPlan}
          goToPlan={goToPlan}
          refreshPlans={refreshPlans}
          handleClearPlans={handleClearPlans}
          showToast={showToast}
          close={() => setPlanListOpen(false)}
        />

        {toast ? <div className="watch-toast">{toast}</div> : null}
      </section>
    </main>
  );
}

function WatchEntryView(props: {
  entryMode: WatchEntryMode;
  setEntryMode: (mode: WatchEntryMode) => void;
  stockName: string;
  setStockName: (value: string) => void;
  buyDate: string;
  setBuyDate: (value: string | ((current: string) => string)) => void;
  position: string;
  setPosition: (value: string) => void;
  buyPrice: string;
  setBuyPrice: (value: string) => void;
  fieldErrors: WatchFormErrors;
  clearFieldError: (field: keyof WatchFormErrors) => void;
  loadingPlans: boolean;
  ocrFile: File | null;
  ocrStatus: string;
  ocrParsing: boolean;
  ocrInputRef: RefObject<HTMLInputElement>;
  calendarInputRef: RefObject<HTMLInputElement>;
  openCalendarPicker: () => void;
  handleOcrFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  handleGeneratePlan: () => void;
  plans: WatchPlan[];
  goToPlan: (planId: string) => void;
  setPlanListOpen: (open: boolean) => void;
}) {
  return (
    <>
      <section className="review-workbench-hero watch-workbench-hero">
        <div className="review-hero-copy">
          <p className="review-kicker">AI WATCH AGENT</p>
          <h1>
            AI 盯盘预案
            <br />
            交易执行工作台
          </h1>
          <p>录入持仓信息后，AI 会生成次日预案，并在观察日按规则推送消息和语音提醒。</p>
          <div className="review-hero-actions">
            <button className="hero-primary-upload" type="button" onClick={props.handleGeneratePlan} disabled={props.loadingPlans}>
              {props.loadingPlans ? <Loader2 className="spin-icon" /> : <Sparkles />}
              {props.loadingPlans ? "正在生成预案" : "生成明日预案"}
            </button>
            <span>支持手动录入或 OCR 回填持仓截图。</span>
          </div>
        </div>
        <section className="research-panel watch-entry-form-card">
          <div className="watch-entry-step">
            <span>1</span>
            <div>
              <h2>填写你的持仓</h2>
              <p>先录入股票名称、买入时间、仓位和买入价。你也可以先用 OCR 从截图里回填，再逐项确认。</p>
            </div>
          </div>

          <div className="watch-entry-mode-switch" role="tablist" aria-label="填写方式">
            <button className={`watch-entry-mode-button ${props.entryMode === "manual" ? "active" : ""}`} type="button" onClick={() => props.setEntryMode("manual")}>
              手动填写
            </button>
            <button className={`watch-entry-mode-button ${props.entryMode === "ocr" ? "active" : ""}`} type="button" onClick={() => props.setEntryMode("ocr")}>
              OCR 填表
            </button>
          </div>

          {props.entryMode === "ocr" ? (
            <div className="watch-ocr-box">
              <input ref={props.ocrInputRef} type="file" hidden accept="image/png,image/jpeg,image/jpg,image/webp" onChange={props.handleOcrFileChange} />
              <button className="watch-ocr-upload" type="button" onClick={() => props.ocrInputRef.current?.click()} disabled={props.ocrParsing}>
                <ImageUp className="h-6 w-6" />
                <b>{props.ocrParsing ? "正在识别截图" : props.ocrFile ? "重新上传持仓截图" : "上传持仓截图"}</b>
                <span>支持 jpg / png / webp。系统会调用 OCR 抽取股票、买入时间、仓位和买入价，并自动回填到下方。</span>
              </button>
              {props.ocrStatus ? <p className="watch-ocr-status">{props.ocrStatus}</p> : null}
              {props.fieldErrors.ocrFile ? <p className="watch-entry-error">{props.fieldErrors.ocrFile}</p> : null}
            </div>
          ) : null}

          <div className="watch-search-input">
            <Search className="h-5 w-5" />
            <input
              value={props.stockName}
              onChange={(event) => {
                props.setStockName(event.target.value);
                props.clearFieldError("stockName");
              }}
              placeholder="例如：长电科技 600584"
              autoComplete="off"
            />
            {props.stockName ? (
              <button type="button" aria-label="清空股票名称" onClick={() => { props.setStockName(""); props.clearFieldError("stockName"); }}>
                <X className="h-4 w-4" />
              </button>
            ) : null}
          </div>
          {props.fieldErrors.stockName ? <p className="watch-entry-error">{props.fieldErrors.stockName}</p> : null}

          <div className="watch-entry-fields">
            <label className="watch-entry-field">
              <span>买入时间</span>
              <div className="watch-date-input">
                <input
                  value={props.buyDate}
                  onChange={(event) => {
                    props.setBuyDate(event.target.value);
                    props.clearFieldError("buyDate");
                  }}
                  onBlur={() => props.setBuyDate((current) => normalizeDisplayDate(current))}
                  placeholder="DD/MM/YY"
                  inputMode="numeric"
                />
                <button type="button" aria-label="选择买入时间" onClick={props.openCalendarPicker}>
                  <CalendarDays className="h-4 w-4" />
                </button>
                <input
                  ref={props.calendarInputRef}
                  className="watch-hidden-calendar"
                  type="date"
                  tabIndex={-1}
                  aria-hidden="true"
                  value={displayToIsoDate(props.buyDate)}
                  onChange={(event) => {
                    props.setBuyDate(isoToDisplayDate(event.target.value));
                    props.clearFieldError("buyDate");
                  }}
                />
              </div>
              {props.fieldErrors.buyDate ? <p className="watch-entry-error">{props.fieldErrors.buyDate}</p> : null}
            </label>

            <label className="watch-entry-field">
              <span>当前仓位</span>
              <select
                value={props.position}
                onChange={(event) => {
                  props.setPosition(event.target.value);
                  props.clearFieldError("position");
                }}
              >
                <option value="">请选择仓位</option>
                {POSITION_OPTIONS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
              {props.fieldErrors.position ? <p className="watch-entry-error">{props.fieldErrors.position}</p> : null}
            </label>
          </div>

          <label className="watch-entry-field">
            <span>买入价</span>
            <div className="watch-amount-input">
              <input
                value={props.buyPrice}
                onChange={(event) => {
                  props.setBuyPrice(event.target.value);
                  props.clearFieldError("buyPrice");
                }}
                placeholder="请输入买入价"
                inputMode="decimal"
              />
              <em>元</em>
            </div>
            {props.fieldErrors.buyPrice ? <p className="watch-entry-error">{props.fieldErrors.buyPrice}</p> : null}
          </label>

          <button className="button watch-v2-submit" type="button" onClick={props.handleGeneratePlan} disabled={props.loadingPlans}>
            {props.loadingPlans ? <Loader2 className="spin-icon" /> : <Sparkles className="h-4 w-4" />}
            {props.loadingPlans ? "正在生成明日预案" : "生成明日预案"}
          </button>
          <p className="watch-entry-hint">通常 10 - 20 秒即可完成分析，生成后会直接展示次日预案。</p>
        </section>
      </section>

      <section className="review-workbench-grid watch-entry-grid">
        {props.loadingPlans ? (
          <section className="research-panel watch-loading-panel">
            <Loader2 className="spin-icon" />
            <h2>正在生成次日预案</h2>
            <p>系统正在结合走势和你的持仓信息整理次日计划，稍等片刻即可查看关键价位和操作建议。</p>
          </section>
        ) : (
          <section className="research-panel watch-entry-preview-card">
            <div className="watch-entry-preview-head">
              <span className="card-label">生成结果预览</span>
            </div>
            <div className="watch-preview-feature-grid">
              {PREVIEW_FEATURES.map(([title, text]) => (
                <article className="watch-preview-feature" key={title}>
                  <b>{title}</b>
                  <span>{text}</span>
                </article>
              ))}
            </div>
          </section>
        )}

        <section className="research-panel watch-entry-preview-card">
          <div className="watch-preview-list-head">
            <h3>最近保存的预案</h3>
            <button className="watch-inline-link" type="button" onClick={() => props.setPlanListOpen(true)}>
              查看全部
            </button>
          </div>
          {props.plans.length ? (
            <div className="watch-preview-plan-list">
              {props.plans.slice(0, 4).map((plan) => (
                <button className="watch-preview-plan" type="button" key={plan.plan_id} onClick={() => props.goToPlan(plan.plan_id)}>
                  <div>
                    <b>
                      {plan.name} <small>{plan.code}</small>
                    </b>
                    <span>{plan.watch_date || "观察日待确认"} · {plan.position || "仓位待补全"}</span>
                  </div>
                  <p>{shortText(plan.thesis, 92)}</p>
                </button>
              ))}
            </div>
          ) : (
            <div className="watch-empty watch-entry-empty">
              <b>还没有已保存的预案</b>
              <span>填写上方信息后，这里会自动显示你最近生成的次日预案。</span>
            </div>
          )}
        </section>
      </section>
    </>
  );
}

function WatchResultView(props: {
  selectedPlan: WatchPlan;
  selectedQuote: Quote | null;
  selectedEvents: WatchEvent[];
  watchPhase: ReturnType<typeof buildWatchPhase> | null;
  keyLevels: ReturnType<typeof keyLevelsForPlan>;
  actionLines: string[];
  polling: boolean;
  setPolling: Dispatch<SetStateAction<boolean>>;
  voiceSettings: VoiceSettings;
  pollNow: () => Promise<void>;
  showToast: (text: string) => void;
  setSettingsOpen: (open: boolean) => void;
  setPlanListOpen: (open: boolean) => void;
  errors: string[];
}) {
  return (
    <div className="watch-result-stack">
      <section className="research-panel watch-result-hero">
        <div className="watch-result-hero-head">
          <div>
            <span className="card-label">AI 明日预案</span>
            <h2>
              {props.selectedPlan.name} <small>{props.selectedPlan.code}</small>
            </h2>
            <p>{props.selectedPlan.thesis}</p>
          </div>
          <div className="watch-phase-card" data-tone={props.watchPhase?.tone}>
            <strong>{props.watchPhase?.label}</strong>
            <span>{props.watchPhase?.detail}</span>
          </div>
        </div>

        <div className="watch-summary-callout">
          <b>AI 总结</b>
          <p>{props.selectedPlan.thesis}</p>
        </div>

        <div className="watch-key-grid-v2">
          {props.keyLevels.map((item) => (
            <article className="watch-key-card" key={item.label} data-tone={item.tone}>
              <span>{item.label}</span>
              <strong>{fmtPrice(item.value)}</strong>
            </article>
          ))}
        </div>

        <div className="watch-action-panel">
          <h3>明日操作预案</h3>
          <ul>
            {props.actionLines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>

        <div className="watch-result-actions">
          <button className="button watch-v2-submit" type="button" onClick={() => props.setPolling((value) => !value)}>
            {props.polling ? <PauseCircle className="h-4 w-4" /> : <PlayCircle className="h-4 w-4" />}
            {props.polling ? "暂停盯盘提醒" : "开始盯盘提醒"}
          </button>
          <button className="button secondary" type="button" onClick={() => props.pollNow().catch((error) => props.showToast(error instanceof Error ? error.message : "刷新失败"))}>
            <RefreshCcw className="h-4 w-4" />
            立即刷新
          </button>
          <button className="button secondary" type="button" onClick={() => props.setSettingsOpen(true)}>
            <Volume2 className="h-4 w-4" />
            通知设置
          </button>
        </div>
        <p className="watch-result-note">预案已经保存。到观察日打开页面后，系统会按条件提醒，并尝试语音播报。</p>
      </section>

      <section className="watch-result-grid">
        <article className="research-panel watch-result-card">
          <div className="watch-result-card-head">
            <Clock3 className="h-5 w-5" />
            <div>
              <h3>观察窗口</h3>
              <p>{props.selectedPlan.watch_date || "未设置"} · {props.selectedPlan.position || "仓位待补全"}</p>
            </div>
          </div>
          <Stat label="买入时间" value={props.selectedPlan.buy_date || "--"} />
          <Stat label="买入价" value={fmtPrice(props.selectedPlan.buy_price)} />
          <Stat label="语音播报" value={props.voiceSettings.provider === "edge" ? props.voiceSettings.edge_voice : props.voiceSettings.openai_voice} />
        </article>

        <article className="research-panel watch-result-card">
          <div className="watch-result-card-head">
            <RefreshCcw className="h-5 w-5" />
            <div>
              <h3>盘中快照</h3>
              <p>展示当前预案对应标的的最新行情。</p>
            </div>
          </div>
          {props.selectedQuote ? (
            <div className="watch-quote-compact">
              <strong>{props.selectedQuote.price.toFixed(2)}</strong>
              <span data-tone={props.selectedQuote.pct_chg >= 0 ? "up" : "down"}>{props.selectedQuote.pct_chg.toFixed(2)}%</span>
              <em>{props.selectedQuote.quote_time}</em>
            </div>
          ) : (
            <div className="watch-empty watch-compact-empty">
              <b>暂无实时快照</b>
              <span>开启盯盘后，观察日盘中会自动拉取实时行情。</span>
            </div>
          )}
        </article>

        <article className="research-panel watch-result-card">
          <div className="watch-result-card-head">
            <BellRing className="h-5 w-5" />
            <div>
              <h3>提醒状态</h3>
              <p>触发后会先推送消息，再尝试语音播报。</p>
            </div>
          </div>
          <Stat label="轮询状态" value={props.polling ? "已开启" : "已暂停"} />
          <Stat label="新提醒数" value={String(props.selectedEvents.length)} />
          <Stat label="语音回退" value={props.voiceSettings.fallback_browser_voice_hint === "female" ? "浏览器偏女声" : "浏览器偏男声"} />
        </article>
      </section>

      <section className="research-panel watch-alert-panel-v2">
        <div className="watch-result-section-head">
          <div>
            <h3>最新触发提醒</h3>
            <p>提醒条件由后端规则引擎判定，触发文案和语音由 Agent 生成。</p>
          </div>
          <button className="watch-inline-link" type="button" onClick={() => props.setPlanListOpen(true)}>
            切换预案
          </button>
        </div>
        {props.errors.length ? <div className="watch-error">{props.errors.join("；")}</div> : null}
        <div className="watch-alert-list">
          {props.selectedEvents.length ? props.selectedEvents.map((event) => (
            <article className="watch-alert-item" key={event.key}>
              <b>{event.name} {event.code} · {event.level}</b>
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
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="watch-result-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function VoiceSettingsSheet(props: {
  open: boolean;
  voiceSettings: VoiceSettings;
  setVoiceSettings: Dispatch<SetStateAction<VoiceSettings>>;
  voiceOptions: VoiceSettingsPayload["options"];
  savingVoice: boolean;
  previewingVoice: boolean;
  handlePreviewVoice: () => void;
  handleSaveVoiceSettings: () => void;
  close: () => void;
}) {
  return (
    <aside className={`watch-sheet ${props.open ? "open" : ""}`} role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
      <div className="watch-sheet-head">
        <div>
          <h3>通知设置</h3>
          <p>调整语音播报方式、试听文案和浏览器回退音色。</p>
        </div>
        <button type="button" aria-label="关闭设置" onClick={props.close}>
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="watch-sheet-body">
        <VoiceSelect label="语音引擎" value={props.voiceSettings.provider} options={props.voiceOptions.provider} onChange={(value) => props.setVoiceSettings((current) => ({ ...current, provider: value as VoiceSettings["provider"] }))} />
        <VoiceSelect label="OpenAI 音色" value={props.voiceSettings.openai_voice} options={props.voiceOptions.openai_voice} disabled={props.voiceSettings.provider !== "openai"} onChange={(value) => props.setVoiceSettings((current) => ({ ...current, openai_voice: value }))} />
        <VoiceSelect label="Edge 音色" value={props.voiceSettings.edge_voice} options={props.voiceOptions.edge_voice} disabled={props.voiceSettings.provider !== "edge"} onChange={(value) => props.setVoiceSettings((current) => ({ ...current, edge_voice: value }))} />
        <VoiceSelect label="浏览器回退" value={props.voiceSettings.fallback_browser_voice_hint} options={props.voiceOptions.fallback_browser_voice_hint} onChange={(value) => props.setVoiceSettings((current) => ({ ...current, fallback_browser_voice_hint: value as VoiceSettings["fallback_browser_voice_hint"] }))} />
        <label className="watch-entry-field">
          <span>试听文案</span>
          <textarea value={props.voiceSettings.preview_text} onChange={(event) => props.setVoiceSettings((current) => ({ ...current, preview_text: event.target.value }))} placeholder="输入试听文案" rows={4} />
        </label>
      </div>
      <div className="watch-sheet-actions">
        <button className="button secondary" type="button" onClick={props.handlePreviewVoice} disabled={props.previewingVoice}>
          <Volume2 className="h-4 w-4" />
          {props.previewingVoice ? "正在试听" : "试听当前音色"}
        </button>
        <button className="button watch-v2-submit watch-sheet-submit" type="button" onClick={props.handleSaveVoiceSettings} disabled={props.savingVoice}>
          <ShieldCheck className="h-4 w-4" />
          {props.savingVoice ? "正在保存" : "保存设置"}
        </button>
      </div>
    </aside>
  );
}

function VoiceSelect(props: { label: string; value: string; options: VoiceOption[]; disabled?: boolean; onChange: (value: string) => void }) {
  return (
    <label className="watch-entry-field">
      <span>{props.label}</span>
      <select value={props.value} disabled={props.disabled} onChange={(event) => props.onChange(event.target.value)}>
        {props.options.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function PlanListSheet(props: {
  open: boolean;
  plans: WatchPlan[];
  selectedPlan: WatchPlan | null;
  goToPlan: (planId: string) => void;
  refreshPlans: () => Promise<WatchPlan[]>;
  handleClearPlans: () => void;
  showToast: (text: string) => void;
  close: () => void;
}) {
  return (
    <aside className={`watch-sheet ${props.open ? "open" : ""}`} role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
      <div className="watch-sheet-head">
        <div>
          <h3>我的预案列表</h3>
          <p>这里会保留已经生成的预案，方便你随时切换查看。</p>
        </div>
        <button type="button" aria-label="关闭预案列表" onClick={props.close}>
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="watch-sheet-body">
        {props.plans.length ? (
          <div className="watch-plan-list-drawer">
            {props.plans.map((plan) => (
              <button className={`watch-plan-list-item ${props.selectedPlan?.plan_id === plan.plan_id ? "active" : ""}`} type="button" key={plan.plan_id} onClick={() => props.goToPlan(plan.plan_id)}>
                <div>
                  <b>
                    {plan.name} <small>{plan.code}</small>
                  </b>
                  <span>{plan.watch_date || "未设置观察日"} · {plan.position || "仓位待补全"}</span>
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
        <button className="button secondary" type="button" onClick={() => props.refreshPlans().catch((error) => props.showToast(error instanceof Error ? error.message : "刷新失败"))}>
          <RefreshCcw className="h-4 w-4" />
          刷新列表
        </button>
        <button className="button secondary" type="button" onClick={props.handleClearPlans}>
          清空全部预案
        </button>
      </div>
    </aside>
  );
}
