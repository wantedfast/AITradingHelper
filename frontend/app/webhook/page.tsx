"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { ArrowLeft, BellDot, Braces, Clock3, Loader2, Radio, RefreshCcw, Send, ServerCog } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8600" : "");

type WebhookEvent = {
  id: string;
  request_id: string;
  received_at: string;
  source_ip: string;
  source: string;
  event_type: string;
  title: string;
  summary: string;
  payload: unknown;
  headers: Record<string, string>;
};

type WebhookPayload = {
  events?: WebhookEvent[];
  count?: number;
  total?: number;
};

const SAMPLE_PAYLOAD = JSON.stringify(
  {
    source: "external-system",
    event_type: "trade.signal",
    title: "长电科技触发观察信号",
    summary: "外部系统推送：价格突破观察位，等待前端确认。",
    code: "600584",
    price: 34.56,
  },
  null,
  2,
);

function formatJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value ?? "");
  }
}

function short(value: string, limit = 96) {
  return value.length > limit ? `${value.slice(0, limit - 3)}...` : value;
}

export default function WebhookPage() {
  const [events, setEvents] = useState<WebhookEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [payloadText, setPayloadText] = useState(SAMPLE_PAYLOAD);
  const [secret, setSecret] = useState("");
  const [message, setMessage] = useState("");

  const selectedEvent = useMemo(() => {
    if (!events.length) return null;
    return events.find((event) => event.id === selectedId) || events[0];
  }, [events, selectedId]);

  async function loadEvents(silent = false) {
    if (!silent) setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/webhooks?limit=50`, { cache: "no-store" });
      const text = await response.text();
      const payload = text ? (JSON.parse(text) as WebhookPayload) : {};
      if (!response.ok) throw new Error((payload as { error?: string }).error || `读取失败：HTTP ${response.status}`);
      const nextEvents = payload.events || [];
      setEvents(nextEvents);
      setTotal(payload.total || nextEvents.length);
      setSelectedId((current) => current || nextEvents[0]?.id || "");
      if (!silent) setMessage("已刷新 webhook 收件箱。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取 webhook 失败");
    } finally {
      setLoading(false);
    }
  }

  async function sendTestWebhook(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSending(true);
    setMessage("");
    try {
      const parsed = JSON.parse(payloadText);
      const headers = new Headers({ "Content-Type": "application/json" });
      if (secret.trim()) headers.set("X-Webhook-Secret", secret.trim());
      const response = await fetch(`${API_BASE}/api/webhooks`, {
        method: "POST",
        headers,
        body: JSON.stringify(parsed),
      });
      const text = await response.text();
      const payload = text ? (JSON.parse(text) as { error?: string }) : {};
      if (!response.ok) throw new Error(payload.error || `发送失败：HTTP ${response.status}`);
      setMessage("测试 webhook 已写入后端。");
      await loadEvents(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "发送测试 webhook 失败");
    } finally {
      setSending(false);
    }
  }

  useEffect(() => {
    loadEvents();
    const timer = window.setInterval(() => loadEvents(true), 8000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <main className="webhook-page">
      <aside className="webhook-rail">
        <Link className="webhook-brand" href="/">
          <span className="brand-mark">
            <Radio className="h-5 w-5" />
          </span>
          <span>
            <b>Webhook</b>
            <small>外部消息收件箱</small>
          </span>
        </Link>
        <nav className="webhook-nav" aria-label="webhook navigation">
          <Link href="/">
            <ArrowLeft className="h-5 w-5" />
            <span>
              <b>返回首页</b>
              <small>回到盈航主界面</small>
            </span>
          </Link>
          <button type="button" onClick={() => loadEvents()} disabled={loading}>
            {loading ? <Loader2 className="spin-icon" /> : <RefreshCcw className="h-5 w-5" />}
            <span>
              <b>刷新事件</b>
              <small>读取最新 webhook</small>
            </span>
          </button>
        </nav>
      </aside>

      <section className="webhook-main">
        <header className="webhook-topbar">
          <div>
            <span>RECEIVER</span>
            <b>Webhook 数据映射</b>
          </div>
          <code>{API_BASE || "当前域名"}/api/webhooks</code>
        </header>

        <section className="webhook-hero">
          <div>
            <p className="webhook-kicker">
              <BellDot className="h-4 w-4" />
              实时接收外部推送
            </p>
            <h1>把别人发来的 webhook 信息接进后端，并映射到前端。</h1>
            <p>
              后端保存原始 payload，同时提取来源、事件类型、标题和摘要。页面每 8 秒自动刷新，方便你确认外部系统是否成功推送。
            </p>
          </div>
          <div className="webhook-stats">
            <article>
              <span>当前展示</span>
              <b>{events.length}</b>
            </article>
            <article>
              <span>累计接收</span>
              <b>{total}</b>
            </article>
            <article>
              <span>状态</span>
              <b>{loading ? "同步中" : "在线"}</b>
            </article>
          </div>
        </section>

        <section className="webhook-grid">
          <form className="webhook-panel webhook-test-form" onSubmit={sendTestWebhook}>
            <div className="webhook-panel-head">
              <ServerCog className="h-5 w-5" />
              <div>
                <h2>测试发送</h2>
                <p>本地模拟外部系统向后端推送 JSON。</p>
              </div>
            </div>
            <label>
              <span>Webhook Secret</span>
              <input value={secret} onChange={(event) => setSecret(event.target.value)} placeholder="生产环境设置 WEBHOOK_SECRET 时填写" />
            </label>
            <label>
              <span>JSON Payload</span>
              <textarea value={payloadText} onChange={(event) => setPayloadText(event.target.value)} rows={12} spellCheck={false} />
            </label>
            <button type="submit" disabled={sending}>
              {sending ? <Loader2 className="spin-icon" /> : <Send className="h-4 w-4" />}
              {sending ? "正在发送" : "发送测试 webhook"}
            </button>
            {message ? <p className="webhook-message">{message}</p> : null}
          </form>

          <section className="webhook-panel webhook-events">
            <div className="webhook-panel-head">
              <Clock3 className="h-5 w-5" />
              <div>
                <h2>最近事件</h2>
                <p>点击事件查看原始 payload 和请求头。</p>
              </div>
            </div>
            <div className="webhook-event-list">
              {events.length ? (
                events.map((event) => (
                  <button className={selectedEvent?.id === event.id ? "active" : ""} type="button" key={event.id} onClick={() => setSelectedId(event.id)}>
                    <span>
                      <b>{event.title}</b>
                      <small>{event.source} · {event.event_type}</small>
                    </span>
                    <em>{event.received_at}</em>
                    <p>{short(event.summary || formatJson(event.payload))}</p>
                  </button>
                ))
              ) : (
                <div className="webhook-empty">
                  <b>还没有收到 webhook</b>
                  <span>先用左侧测试表单发送一条，或让外部系统 POST 到后端地址。</span>
                </div>
              )}
            </div>
          </section>
        </section>

        <section className="webhook-panel webhook-detail">
          <div className="webhook-panel-head">
            <Braces className="h-5 w-5" />
            <div>
              <h2>事件详情</h2>
              <p>{selectedEvent ? `${selectedEvent.source_ip || "unknown ip"} · ${selectedEvent.request_id}` : "等待事件进入收件箱"}</p>
            </div>
          </div>
          {selectedEvent ? (
            <div className="webhook-detail-grid">
              <article>
                <span>映射结果</span>
                <dl>
                  <div><dt>标题</dt><dd>{selectedEvent.title}</dd></div>
                  <div><dt>来源</dt><dd>{selectedEvent.source}</dd></div>
                  <div><dt>类型</dt><dd>{selectedEvent.event_type}</dd></div>
                  <div><dt>时间</dt><dd>{selectedEvent.received_at}</dd></div>
                </dl>
              </article>
              <article>
                <span>原始 Payload</span>
                <pre>{formatJson(selectedEvent.payload)}</pre>
              </article>
              <article>
                <span>安全后的 Headers</span>
                <pre>{formatJson(selectedEvent.headers)}</pre>
              </article>
            </div>
          ) : (
            <div className="webhook-empty">
              <b>暂无详情</b>
              <span>收到事件后，这里会展示后端保存的数据。</span>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}
