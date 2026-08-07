"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
  const [message, setMessage] = useState("");
  const confirmButtonRef = useRef<HTMLButtonElement>(null);
  const userId = user?.id || 0;
  const userRole = user?.role || "";
  const homepageGateEnabled = pathname === "/" && userRole === "user";

  useEffect(() => {
    // A profile without a session token is stale browser state, not a logged-in
    // user. In particular, it must not make a guest call the protected notice API.
    setUser(getAuthToken() ? getStoredUser() : null);
    function handleAuth(event: Event) {
      setUser((event as CustomEvent<UserProfile | null>).detail || null);
    }
    window.addEventListener("ai-trade-auth", handleAuth);
    return () => window.removeEventListener("ai-trade-auth", handleAuth);
  }, []);

  useEffect(() => {
    if (!homepageGateEnabled) {
      setNotices([]);
      setMessage("");
      return;
    }
    let active = true;
    async function loadPending() {
      setLoading(true);
      setMessage("");
      try {
        const payload = await apiFetch<{ notices: UpdateNotice[]; user?: UserProfile | null }>("/api/update-notices/pending");
        if (!active) return;
        if (payload.user) storeUser(payload.user);
        setNotices(Array.isArray(payload.notices) ? payload.notices : []);
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          setUser(null);
          setNotices([]);
          setMessage("");
          return;
        }
        // The check is silent: a transient request failure must not flash or
        // block the homepage when no notice has actually been returned.
        setNotices([]);
      } finally {
        if (active) setLoading(false);
      }
    }
    void loadPending();
    return () => {
      active = false;
    };
  }, [homepageGateEnabled, userId, userRole]);

  useEffect(() => {
    if (!homepageGateEnabled || !notices.length) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const frame = window.requestAnimationFrame(() => confirmButtonRef.current?.focus());
    return () => {
      window.cancelAnimationFrame(frame);
      document.body.style.overflow = previousOverflow;
    };
  }, [homepageGateEnabled, notices.length]);

  const activeNotice = notices[0] || null;
  const markdownBlocks = useMemo(
    () => renderNoticeMarkdown(activeNotice?.content_markdown || "", activeNotice?.id || 0),
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

  if (!homepageGateEnabled) return null;

  if (!activeNotice) return null;

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
        {markdownBlocks.length ? (
          <div className="site-update-notice-body">
            {markdownBlocks}
          </div>
        ) : (
          <ul className="site-update-notice-list">
            {activeNotice.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
        {message ? <div className="site-update-notice-error">{message}</div> : null}
        <button className="site-update-notice-confirm" type="button" onClick={acknowledge} disabled={loading} ref={confirmButtonRef}>
          {loading ? "正在确认..." : "知道了，进入网站"}
        </button>
      </section>
    </div>
  );
}

const INLINE_MARKDOWN_RE = /(`[^`\n]+`|\[[^\]\n]+\]\(https?:\/\/[^\s)]+\)|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|_[^_\n]+_)/g;

function renderMarkdownInline(value: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  INLINE_MARKDOWN_RE.lastIndex = 0;
  while ((match = INLINE_MARKDOWN_RE.exec(value)) !== null) {
    if (match.index > cursor) nodes.push(value.slice(cursor, match.index));
    const token = match[0];
    const key = `${keyPrefix}-${match.index}`;
    if (token.startsWith("`")) {
      nodes.push(<code key={key}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith("[")) {
      const separator = token.indexOf("](");
      const label = token.slice(1, separator);
      const href = token.slice(separator + 2, -1);
      nodes.push(<a key={key} href={href} target="_blank" rel="noreferrer">{label}</a>);
    } else if (token.startsWith("**") || token.startsWith("__")) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else {
      nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    }
    cursor = match.index + token.length;
  }
  if (cursor < value.length) nodes.push(value.slice(cursor));
  return nodes;
}

function renderNoticeMarkdown(markdown: string, noticeId: number): ReactNode[] {
  const lines = markdown.split(/\r?\n/);
  const blocks: ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const trimmed = lines[index].trim();
    if (!trimmed) {
      index += 1;
      continue;
    }
    if (trimmed.startsWith("```")) {
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push(<pre key={`${noticeId}-code-${index}`}><code>{code.join("\n")}</code></pre>);
      continue;
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (heading) {
      const content = renderMarkdownInline(heading[2], `${noticeId}-heading-${index}`);
      blocks.push(heading[1].length === 1
        ? <h3 key={`${noticeId}-heading-${index}`}>{content}</h3>
        : <h4 key={`${noticeId}-heading-${index}`}>{content}</h4>);
      index += 1;
      continue;
    }
    const unordered = /^\s*[-*+]\s+(.+)$/.exec(lines[index]);
    const ordered = /^\s*\d+[.)]\s+(.+)$/.exec(lines[index]);
    if (unordered || ordered) {
      const isOrdered = Boolean(ordered);
      const items: ReactNode[] = [];
      while (index < lines.length) {
        const item = (isOrdered ? /^\s*\d+[.)]\s+(.+)$/.exec(lines[index]) : /^\s*[-*+]\s+(.+)$/.exec(lines[index]));
        if (!item) break;
        items.push(<li key={`${noticeId}-item-${index}`}>{renderMarkdownInline(item[1], `${noticeId}-item-${index}`)}</li>);
        index += 1;
      }
      blocks.push(isOrdered
        ? <ol key={`${noticeId}-list-${index}`}>{items}</ol>
        : <ul key={`${noticeId}-list-${index}`}>{items}</ul>);
      continue;
    }
    const quote = /^>\s?(.*)$/.exec(trimmed);
    if (quote) {
      blocks.push(<blockquote key={`${noticeId}-quote-${index}`}>{renderMarkdownInline(quote[1], `${noticeId}-quote-${index}`)}</blockquote>);
      index += 1;
      continue;
    }
    const paragraph: string[] = [trimmed];
    index += 1;
    while (index < lines.length && lines[index].trim() && !/^(#{1,3})\s+|^```|^\s*[-*+]\s+|^\s*\d+[.)]\s+|^>/.test(lines[index])) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(<p key={`${noticeId}-paragraph-${index}`}>{renderMarkdownInline(paragraph.join(" "), `${noticeId}-paragraph-${index}`)}</p>);
  }
  return blocks;
}
