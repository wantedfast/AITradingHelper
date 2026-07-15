"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Mail, ShieldCheck, X } from "lucide-react";
import { apiFetch, storeUser, type UserProfile } from "@/lib/auth-client";

type SendCodeResult = { resend_after?: number; message?: string };
type BindResult = { user: UserProfile; message?: string };

export function EmailBindingReminder() {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [binding, setBinding] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const emailRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleLogin = (event: Event) => {
      const user = (event as CustomEvent<UserProfile | null>).detail;
      const shouldPrompt = user?.role !== "admin" && user?.email_binding_required === true;
      setOpen(shouldPrompt);
      if (shouldPrompt) {
        setEmail(user?.email || "");
        setCode("");
        setMessage("");
        setCountdown(0);
      }
    };
    window.addEventListener("ai-trade-login", handleLogin);
    return () => window.removeEventListener("ai-trade-login", handleLogin);
  }, []);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);
    const frame = window.requestAnimationFrame(() => emailRef.current?.focus());
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = window.setTimeout(() => setCountdown((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [countdown]);

  async function sendCode() {
    if (!email.trim()) {
      setMessage("请先填写要绑定的邮箱");
      return;
    }
    setSending(true);
    setMessage("");
    try {
      const result = await apiFetch<SendCodeResult>("/api/auth/email-binding/code", {
        method: "POST",
        body: JSON.stringify({ email: email.trim() }),
      });
      setCountdown(result.resend_after || 60);
      setMessage(result.message || "验证码已发送，请查看邮箱。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "验证码发送失败，请稍后重试");
    } finally {
      setSending(false);
    }
  }

  async function bindEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBinding(true);
    setMessage("");
    try {
      const result = await apiFetch<BindResult>("/api/auth/email-binding", {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), email_code: code }),
      });
      storeUser(result.user);
      setOpen(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "邮箱绑定失败，请稍后重试");
    } finally {
      setBinding(false);
    }
  }

  if (!open) return null;
  return (
    <div className="email-binding-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) setOpen(false);
    }}>
      <section className="email-binding-modal" role="dialog" aria-modal="true" aria-labelledby="email-binding-title">
        <header>
          <span><Mail /></span>
          <div><small>账号安全提醒</small><h2 id="email-binding-title">绑定常用邮箱</h2></div>
          <button type="button" onClick={() => setOpen(false)} aria-label="稍后绑定并关闭"><X /></button>
        </header>
        <p>绑定邮箱后可以接收验证码和产品更新。你也可以稍后处理，下次登录时我们会再次提醒。</p>
        <form onSubmit={bindEmail}>
          <label>
            <span>邮箱地址</span>
            <input ref={emailRef} type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@example.com" autoComplete="email" required />
          </label>
          <label>
            <span>邮箱验证码</span>
            <div className="email-binding-code-row">
              <input value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="6 位验证码" inputMode="numeric" autoComplete="one-time-code" required />
              <button type="button" onClick={sendCode} disabled={sending || countdown > 0}>{countdown > 0 ? `${countdown}s` : sending ? "发送中" : "获取验证码"}</button>
            </div>
          </label>
          {message ? <div className="email-binding-message" role="status">{message}</div> : null}
          <div className="email-binding-actions">
            <button type="button" onClick={() => setOpen(false)}>稍后绑定</button>
            <button type="submit" disabled={binding || code.length !== 6}>{binding ? "绑定中..." : "确认绑定"}</button>
          </div>
        </form>
        <footer><ShieldCheck />邮箱仅用于账号安全和你允许接收的服务通知。</footer>
      </section>
    </div>
  );
}
