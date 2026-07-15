"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  KeyRound,
  LogIn,
  Mail,
  MessageSquareText,
  ShieldCheck,
  Sparkles,
  UserPlus,
  UserRound,
  X,
} from "lucide-react";
import { apiFetch, storeAuth, type AuthResult } from "@/lib/auth-client";

type Mode = "password-login" | "password-register";

type AgreementSection = {
  id: string;
  title: string;
  paragraphs: string[];
  important: boolean;
};

type RegistrationAgreement = {
  agreement_type: string;
  version: string;
  effective_at: string;
  title: string;
  operator_name: string;
  sections: AgreementSection[];
  confirmation: string;
  content_hash: string;
};

export default function AuthPage() {
  return (
    <Suspense fallback={<main className="account-page" />}>
      <AuthContent />
    </Suspense>
  );
}

function AuthContent() {
  const router = useRouter();
  const params = useSearchParams();
  const inviteFromUrl = normalizeInviteCode(params.get("invite") || params.get("invite_code") || params.get("ref") || "");
  const registerFromUrl = ["register", "password-register"].includes(params.get("mode") || "");
  const redirect = safeUserRedirect(params.get("redirect"));
  const [mode, setMode] = useState<Mode>(inviteFromUrl || registerFromUrl ? "password-register" : "password-login");
  const [account, setAccount] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [emailCode, setEmailCode] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState(inviteFromUrl);
  const [loading, setLoading] = useState(false);
  const [sendingEmail, setSendingEmail] = useState(false);
  const [emailCountdown, setEmailCountdown] = useState(0);
  const [message, setMessage] = useState("");
  const [agreement, setAgreement] = useState<RegistrationAgreement | null>(null);
  const [agreementLoading, setAgreementLoading] = useState(false);
  const [agreementError, setAgreementError] = useState("");
  const [agreementAccepted, setAgreementAccepted] = useState(false);
  const [agreementOpen, setAgreementOpen] = useState(false);
  const [agreementReadToEnd, setAgreementReadToEnd] = useState(false);
  const [agreementReload, setAgreementReload] = useState(0);
  const agreementBodyRef = useRef<HTMLDivElement>(null);

  const isRegister = mode === "password-register";
  const title = titleForMode(mode);
  const actionLabel = actionForMode(mode);
  const helper = useMemo(() => helperForMode(mode), [mode]);

  useEffect(() => {
    if (!inviteFromUrl && !registerFromUrl) return;
    if (inviteFromUrl) setInviteCode(inviteFromUrl);
    setMode("password-register");
  }, [inviteFromUrl, registerFromUrl]);

  useEffect(() => {
    if (!isRegister) return;
    const controller = new AbortController();
    setAgreementLoading(true);
    setAgreementError("");
    setAgreement(null);
    setAgreementAccepted(false);
    setAgreementOpen(false);
    setAgreementReadToEnd(false);

    apiFetch<RegistrationAgreement>("/api/legal/registration-agreement", { signal: controller.signal })
      .then((result) => setAgreement(result))
      .catch((error) => {
        if (controller.signal.aborted) return;
        setAgreementError(error instanceof Error ? error.message : "协议加载失败，请重试");
      })
      .finally(() => {
        if (!controller.signal.aborted) setAgreementLoading(false);
      });

    return () => controller.abort();
  }, [isRegister, agreementReload]);

  useEffect(() => {
    if (!agreementOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setAgreementOpen(false);
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);
    const frame = window.requestAnimationFrame(() => {
      agreementBodyRef.current?.focus();
      updateAgreementScrollState(agreementBodyRef.current, setAgreementReadToEnd);
    });
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [agreementOpen]);

  async function sendEmailCode() {
    setSendingEmail(true);
    setMessage("");
    try {
      const result = await apiFetch<{ resend_after?: number }>("/api/auth/send-email-code", {
        method: "POST",
        body: JSON.stringify({ email, purpose: "register" }),
      });
      startCountdown(result.resend_after || 60, setEmailCountdown);
      setMessage("邮箱验证码已发送，请查看收件箱。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "邮箱验证码发送失败");
    } finally {
      setSendingEmail(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mode === "password-register" && (!agreement || !agreementAccepted)) {
      setMessage("请先完整阅读并同意用户注册协议与风险揭示书");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      let result: AuthResult;
      if (mode === "password-register") {
        result = await apiFetch<AuthResult>("/api/auth/password-register", {
          method: "POST",
          body: JSON.stringify({
            username,
            email,
            password,
            email_code: emailCode,
            invite_code: inviteCode,
            agreement_accepted: true,
            agreement_version: agreement!.version,
          }),
        });
      } else {
        result = await apiFetch<AuthResult>("/api/auth/password-login", {
          method: "POST",
          body: JSON.stringify({ account, password }),
        });
      }
      storeAuth(result);
      const target = redirect;
      router.push(result.user.role !== "admin" && target === "/admin" ? "/" : target);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "操作失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="account-page">
      <div className="account-shell">
        <section className="account-hero">
          <Link className="account-brand" href="/">
            <span>盈</span>
            <b>盈航</b>
          </Link>
          <div>
            <p className="account-kicker">
              <Sparkles />
              USER ACCESS
            </p>
            <h1>把复盘能力，绑定到每一次真实使用。</h1>
            <p>
              仅支持邮箱注册。注册时设置账号名和密码，后续可使用邮箱或账号名登录。
            </p>
          </div>
          <div className="account-rules">
            <article>
              <ShieldCheck />
              <span>首次注册赠送 5 次免费使用</span>
            </article>
            <article>
              <UserPlus />
              <span>成功邀请新用户注册登录，奖励 5 次</span>
            </article>
            <article>
              <KeyRound />
              <span>反馈被采纳，奖励 10 次</span>
            </article>
          </div>
        </section>

        <section className="account-panel">
          <div className="account-mobile-intro">
            <Link href="/">盈航 AI TRADING</Link>
            <b>{isRegister ? "注册并领取免费次数" : "登录后继续使用"}</b>
            <span>{isRegister ? "使用邮箱完成注册，已有账号可直接登录。" : "查看你的报告、预案和剩余使用次数。"}</span>
          </div>
          <div className="account-mode-switch">
            <button className={mode === "password-login" ? "active" : ""} type="button" onClick={() => setMode("password-login")}>
              密码登录
            </button>
            <button className={isRegister ? "active" : ""} type="button" onClick={() => setMode("password-register")}>
              邮箱注册
            </button>
          </div>
          <h2>{title}</h2>
          <p>{helper}</p>
          <form className="account-form" onSubmit={submit}>
            {mode === "password-login" && (
              <>
                <label>
                  <span>账号或邮箱</span>
                  <i>
                    <UserRound />
                    <input value={account} onChange={(event) => setAccount(event.target.value)} placeholder="账号名或邮箱" />
                  </i>
                </label>
                <PasswordField value={password} onChange={setPassword} placeholder="请输入密码" />
              </>
            )}

            {mode === "password-register" && (
              <>
                <label>
                  <span>账号名</span>
                  <i>
                    <UserRound />
                    <input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="例如 yinghang_user" />
                  </i>
                </label>
                <label>
                  <span>注册邮箱</span>
                  <i>
                    <Mail />
                    <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@example.com" />
                  </i>
                </label>
                <CodeField
                  label="邮箱验证码"
                  value={emailCode}
                  onChange={setEmailCode}
                  onSend={sendEmailCode}
                  sending={sendingEmail}
                  countdown={emailCountdown}
                />
                <PasswordField value={password} onChange={setPassword} placeholder="至少 8 位密码" />
              </>
            )}

            {isRegister && (
              <label>
                <span>邀请码</span>
                <i>
                  <UserPlus />
                  <input value={inviteCode} onChange={(event) => setInviteCode(normalizeInviteCode(event.target.value))} placeholder="选填" />
                </i>
                <small className="account-invite-hint">
                  填入邀请码并完成注册后，邀请方增加 5 次使用机会；被邀请方在注册赠送 5 次基础上，再额外增加 2 次。
                </small>
              </label>
            )}
            {isRegister && (
              <div className="account-agreement-consent">
                {agreementLoading && <p>正在加载用户协议…</p>}
                {agreementError && (
                  <div className="account-agreement-load-error" role="alert">
                    <span>用户协议加载失败，暂时无法注册。</span>
                    <button type="button" onClick={() => setAgreementReload((value) => value + 1)}>重新加载</button>
                  </div>
                )}
                {agreement && (
                  <label>
                    <input
                      type="checkbox"
                      checked={agreementAccepted}
                      onChange={(event) => {
                        if (event.target.checked) {
                          setAgreementReadToEnd(false);
                          setAgreementOpen(true);
                        } else {
                          setAgreementAccepted(false);
                        }
                      }}
                    />
                    <span>
                      我已阅读并同意
                      <button type="button" onClick={() => {
                        setAgreementReadToEnd(false);
                        setAgreementOpen(true);
                      }}>
                        《{agreement.title}》
                      </button>
                    </span>
                  </label>
                )}
              </div>
            )}
            {message && <div className="account-error">{message}</div>}
            <button
              className="account-submit"
              type="submit"
              disabled={loading || (isRegister && (agreementLoading || !!agreementError || !agreement || !agreementAccepted))}
            >
              {loading ? "处理中..." : actionLabel}
              {isRegister ? <ArrowRight /> : <LogIn />}
            </button>
          </form>
          <div className="account-note">
            邮箱验证码用于确认本人操作。请勿向任何人泄露验证码，平台工作人员不会索要你的验证码或密码。
          </div>
        </section>
      </div>
      {agreementOpen && agreement && (
        <div className="account-agreement-backdrop" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setAgreementOpen(false);
        }}>
          <section
            className="account-agreement-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="registration-agreement-title"
          >
            <header>
              <div>
                <span>注册前必读 · {agreement.operator_name}</span>
                <h2 id="registration-agreement-title">{agreement.title}</h2>
                <small>版本 {agreement.version} · 生效日期 {agreement.effective_at}</small>
              </div>
              <button type="button" className="account-agreement-close" onClick={() => setAgreementOpen(false)} aria-label="关闭协议">
                <X />
              </button>
            </header>
            <div
              className="account-agreement-body"
              ref={agreementBodyRef}
              onScroll={(event) => updateAgreementScrollState(event.currentTarget, setAgreementReadToEnd)}
              tabIndex={0}
            >
              {agreement.sections.map((section) => (
                <article key={section.id} className={section.important ? "important" : ""}>
                  <h3>{section.title}</h3>
                  {section.paragraphs.map((paragraph, index) => <p key={`${section.id}-${index}`}>{paragraph}</p>)}
                </article>
              ))}
              <blockquote>{agreement.confirmation}</blockquote>
            </div>
            <footer>
              <span>{agreementReadToEnd ? "已阅读至协议末尾" : "请滚动阅读至协议末尾"}</span>
              <button
                type="button"
                disabled={!agreementReadToEnd}
                onClick={() => {
                  setAgreementAccepted(true);
                  setAgreementOpen(false);
                  setMessage("");
                }}
              >
                同意并关闭
              </button>
            </footer>
          </section>
        </div>
      )}
    </main>
  );
}

function CodeField({
  label,
  value,
  onChange,
  onSend,
  sending,
  countdown,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  sending: boolean;
  countdown: number;
}) {
  return (
    <label>
      <span>{label}</span>
      <div className="account-code-row">
        <i>
          <MessageSquareText />
          <input value={value} onChange={(event) => onChange(event.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="6 位验证码" inputMode="numeric" />
        </i>
        <button type="button" onClick={onSend} disabled={sending || countdown > 0}>
          {countdown > 0 ? `${countdown}s` : sending ? "发送中" : "获取验证码"}
        </button>
      </div>
    </label>
  );
}

function PasswordField({ value, onChange, placeholder }: { value: string; onChange: (value: string) => void; placeholder: string }) {
  return (
    <label>
      <span>密码</span>
      <i>
        <KeyRound />
        <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} type="password" />
      </i>
    </label>
  );
}

function titleForMode(mode: Mode) {
  if (mode === "password-login") return "账号或邮箱登录";
  return "账号密码注册";
}

function actionForMode(mode: Mode) {
  if (mode === "password-login") return "密码登录";
  return "账号注册并领取 5 次免费机会";
}

function helperForMode(mode: Mode) {
  if (mode === "password-login") return "可以使用账号名或注册邮箱登录。";
  return "填写账号名、注册邮箱和密码；邮箱验证码通过后即可创建账号。";
}

function safeUserRedirect(value: string | null) {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes(":") || value.includes("\\") || /[\u0000-\u001f\u007f]/.test(value)) return "/";
  if (value === "/admin" || value.startsWith("/admin/") || value.startsWith("/admin?") || value.startsWith("/admin#")) return "/";
  return value;
}

function normalizeInviteCode(value: string) {
  return value.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 32).toUpperCase();
}

function startCountdown(seconds: number, setter: (value: number | ((value: number) => number)) => void) {
  setter(seconds);
  const timer = window.setInterval(() => {
    setter((value: number) => {
      if (value <= 1) {
        window.clearInterval(timer);
        return 0;
      }
      return value - 1;
    });
  }, 1000);
}

function updateAgreementScrollState(element: HTMLDivElement | null, setter: (value: boolean) => void) {
  if (!element) return;
  setter(element.scrollHeight - element.scrollTop - element.clientHeight <= 8);
}
