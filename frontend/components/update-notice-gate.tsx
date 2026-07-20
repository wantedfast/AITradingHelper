"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { ApiError, apiFetch, getAuthToken, getStoredUser, storeUser, type UserProfile } from "@/lib/auth-client";

type UpdateNotice = {
  id: number;
  title: string;
  version: string;
  items: string[];
  summary?: string;
  content_markdown?: string;
  published_at?: string | null;
};

export function UpdateNoticeGate() {
  const pathname = usePathname();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [notices, setNotices] = useState<UpdateNotice[]>([]);
  const [loading, setLoading] = useState(false);
  const [noticeStatus, setNoticeStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [message, setMessage] = useState("");
  const [loadFailed, setLoadFailed] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const confirmButtonRef = useRef<HTMLButtonElement>(null);
  const excludedPage = pathname === "/auth";

  useEffect(() => {
    // A profile without a session token is stale browser state, not a logged-in
    // user. In particular, it must not make a guest call the protected notice API.
    setUser(getAuthToken() ? getStoredUser() : null);
    function handleAuth(event: Event) {
      setUser((event as CustomEvent<UserProfile | null>).detail || null);
      setNoticeStatus("idle");
    }
    window.addEventListener("ai-trade-auth", handleAuth);
    return () => window.removeEventListener("ai-trade-auth", handleAuth);
  }, []);

  useEffect(() => {
    if (!user || excludedPage) {
      setNotices([]);
      setMessage("");
      setLoadFailed(false);
      setNoticeStatus("idle");
      return;
    }
    let active = true;
    async function loadPending() {
      setLoading(true);
      setNoticeStatus("loading");
      setLoadFailed(false);
      setMessage("");
      try {
        const payload = await apiFetch<{ notices: UpdateNotice[]; user?: UserProfile | null }>("/api/update-notices/pending");
        if (!active) return;
        if (payload.user) storeUser(payload.user);
        setNotices(Array.isArray(payload.notices) ? payload.notices : []);
        setNoticeStatus("ready");
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          return;
        }
        setNotices((current) => current);
        setLoadFailed(true);
        setNoticeStatus("error");
        setMessage(error instanceof Error ? error.message : "更新公告加载失败，请重试");
      } finally {
        if (active) setLoading(false);
      }
    }
    void loadPending();
    return () => {
      active = false;
    };
  }, [excludedPage, retryKey, user]);

  useEffect(() => {
    if (!user || excludedPage || (noticeStatus === "ready" && !notices.length)) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const frame = window.requestAnimationFrame(() => confirmButtonRef.current?.focus());
    return () => {
      window.cancelAnimationFrame(frame);
      document.body.style.overflow = previousOverflow;
    };
  }, [excludedPage, noticeStatus, notices.length, user]);

  const activeNotice = notices[0] || null;
  const markdownLines = useMemo(
    () =>
      (activeNotice?.content_markdown || "")
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean),
    [activeNotice],
  );

  async function acknowledge() {
    if (!activeNotice || loading) return;
    setLoading(true);
    setMessage("");
    try {
      const payload = await apiFetch<{ remaining: UpdateNotice[] }>(`/api/update-notices/${activeNotice.id}/ack`, {
        method: "POST",
      });
      setNotices(Array.isArray(payload.remaining) ? payload.remaining : []);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "确认公告失败，请重试");
    } finally {
      setLoading(false);
    }
  }

  if (!user || excludedPage) return null;

  if (noticeStatus === "ready" && !activeNotice) return null;

  if (!activeNotice) {
    return (
      <div className="site-update-notice-backdrop" role="presentation">
        <section
          className="site-update-notice-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="site-update-notice-status-title"
          aria-busy={noticeStatus === "loading"}
        >
          <div className="site-update-notice-kicker">平台更新</div>
          <h2 id="site-update-notice-status-title">
            {noticeStatus === "error" ? "更新公告加载失败" : "正在检查更新公告"}
          </h2>
          <p className="site-update-notice-summary">
            {noticeStatus === "error"
              ? message || "无法确认是否有待阅公告，请重试。"
              : "请稍候，确认完成后即可进入网站。"}
          </p>
          {noticeStatus === "error" ? (
            <div className="site-update-notice-recovery-actions">
              <button className="site-update-notice-confirm" type="button" onClick={() => setRetryKey((value) => value + 1)} disabled={loading}>
                {loading ? "正在重试..." : "重试加载公告"}
              </button>
            </div>
          ) : (
            <div className="site-update-notice-loading" role="status">正在加载...</div>
          )}
        </section>
      </div>
    );
  }

  return (
    <div className="site-update-notice-backdrop" role="presentation">
      <section
        className="site-update-notice-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="site-update-notice-title"
      >
        <div className="site-update-notice-kicker">平台更新</div>
        <h2 id="site-update-notice-title">{activeNotice.title}</h2>
        <p className="site-update-notice-meta">
          版本 {activeNotice.version}
          {activeNotice.published_at ? ` · 发布时间 ${String(activeNotice.published_at).slice(0, 16).replace("T", " ")}` : ""}
        </p>
        {activeNotice.summary ? <p className="site-update-notice-summary">{activeNotice.summary}</p> : null}
        {markdownLines.length ? (
          <div className="site-update-notice-body">
            {markdownLines.map((line, index) => (
              <p key={`${activeNotice.id}-${index}`}>{line.replace(/^[-*]\s*/, "")}</p>
            ))}
          </div>
        ) : (
          <ul className="site-update-notice-list">
            {activeNotice.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
        {message ? <div className="site-update-notice-error">{message}</div> : null}
        {loadFailed ? (
          <button className="billing-secondary" type="button" onClick={() => setRetryKey((value) => value + 1)}>
            重试加载公告
          </button>
        ) : null}
        <button className="site-update-notice-confirm" type="button" onClick={acknowledge} disabled={loading || loadFailed} ref={confirmButtonRef}>
          {loading ? "正在确认..." : "知道了，进入网站"}
        </button>
      </section>
    </div>
  );
}
