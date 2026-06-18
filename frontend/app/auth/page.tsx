"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useMemo, useState } from "react";
import {
  ArrowRight,
  AtSign,
  KeyRound,
  LogIn,
  Mail,
  MessageSquareText,
  Phone,
  ShieldCheck,
  Sparkles,
  UserPlus,
  UserRound,
} from "lucide-react";
import { apiFetch, storeAuth, type AuthResult } from "@/lib/auth-client";

type Mode = "sms-login" | "password-login" | "sms-register" | "password-register" | "admin";

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
  const inviteFromUrl = params.get("invite") || "";
  const redirect = params.get("redirect") || "/review";
  const [mode, setMode] = useState<Mode>(inviteFromUrl ? "sms-register" : "sms-login");
  const [phone, setPhone] = useState("");
  const [smsCode, setSmsCode] = useState("");
  const [account, setAccount] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [emailCode, setEmailCode] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState(inviteFromUrl);
  const [loading, setLoading] = useState(false);
  const [sendingSms, setSendingSms] = useState(false);
  const [sendingEmail, setSendingEmail] = useState(false);
  const [smsCountdown, setSmsCountdown] = useState(0);
  const [emailCountdown, setEmailCountdown] = useState(0);
  const [message, setMessage] = useState("");

  const isRegister = mode === "sms-register" || mode === "password-register";
  const title = titleForMode(mode);
  const actionLabel = actionForMode(mode);
  const helper = useMemo(() => helperForMode(mode), [mode]);

  async function sendSmsCode() {
    setSendingSms(true);
    setMessage("");
    try {
      const result = await apiFetch<{ debug_code?: string; resend_after?: number }>("/api/auth/send-code", {
        method: "POST",
        body: JSON.stringify({ phone, purpose: "login" }),
      });
      startCountdown(result.resend_after || 60, setSmsCountdown);
      setMessage(result.debug_code ? `本地测试短信验证码：${result.debug_code}` : "短信验证码已发送。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "短信验证码发送失败");
    } finally {
      setSendingSms(false);
    }
  }

  async function sendEmailCode() {
    setSendingEmail(true);
    setMessage("");
    try {
      const result = await apiFetch<{ debug_code?: string; resend_after?: number }>("/api/auth/send-email-code", {
        method: "POST",
        body: JSON.stringify({ email, purpose: "register" }),
      });
      startCountdown(result.resend_after || 60, setEmailCountdown);
      setMessage(result.debug_code ? `本地测试邮箱验证码：${result.debug_code}` : "邮箱验证码已发送，请查看收件箱。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "邮箱验证码发送失败");
    } finally {
      setSendingEmail(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage("");
    try {
      let result: AuthResult;
      if (mode === "sms-login") {
        result = await apiFetch<AuthResult>("/api/auth/login", {
          method: "POST",
          body: JSON.stringify({ phone, code: smsCode }),
        });
      } else if (mode === "sms-register") {
        result = await apiFetch<AuthResult>("/api/auth/register", {
          method: "POST",
          body: JSON.stringify({ phone, code: smsCode, password, invite_code: inviteCode }),
        });
      } else if (mode === "password-register") {
        result = await apiFetch<AuthResult>("/api/auth/password-register", {
          method: "POST",
          body: JSON.stringify({ username, email, password, email_code: emailCode, invite_code: inviteCode }),
        });
      } else {
        result = await apiFetch<AuthResult>("/api/auth/password-login", {
          method: "POST",
          body: JSON.stringify({ account, password }),
        });
      }
      storeAuth(result);
      const target = mode === "admin" && !params.get("redirect") ? "/admin" : redirect;
      router.push(result.user.role !== "admin" && target === "/admin" ? "/review" : target);
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
              支持短信验证码登录，也支持手机号、账号或邮箱密码登录。注册时设置密码，方便后续直接登录。
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
          <div className="account-mode-switch account-mode-switch--triple">
            <button className={mode === "sms-login" ? "active" : ""} type="button" onClick={() => setMode("sms-login")}>
              短信登录
            </button>
            <button className={mode === "password-login" ? "active" : ""} type="button" onClick={() => setMode("password-login")}>
              密码登录
            </button>
            <button className={isRegister ? "active" : ""} type="button" onClick={() => setMode("sms-register")}>
              注册
            </button>
          </div>
          <div className="account-submode-row">
            {isRegister && (
              <>
                <button className={mode === "sms-register" ? "active" : ""} type="button" onClick={() => setMode("sms-register")}>
                  手机号注册
                </button>
                <button className={mode === "password-register" ? "active" : ""} type="button" onClick={() => setMode("password-register")}>
                  账号密码注册
                </button>
              </>
            )}
            {!isRegister && (
              <button className={mode === "admin" ? "active" : ""} type="button" onClick={() => setMode(mode === "admin" ? "password-login" : "admin")}>
                {mode === "admin" ? "返回普通密码登录" : "管理员入口"}
              </button>
            )}
          </div>
          <h2>{title}</h2>
          <p>{helper}</p>
          <form className="account-form" onSubmit={submit}>
            {(mode === "sms-login" || mode === "sms-register") && (
              <>
                <label>
                  <span>手机号</span>
                  <i>
                    <Phone />
                    <input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="请输入手机号" />
                  </i>
                </label>
                <CodeField
                  label="短信验证码"
                  value={smsCode}
                  onChange={setSmsCode}
                  onSend={sendSmsCode}
                  sending={sendingSms}
                  countdown={smsCountdown}
                />
                {mode === "sms-register" && <PasswordField value={password} onChange={setPassword} placeholder="至少 8 位密码" />}
              </>
            )}

            {mode === "password-login" && (
              <>
                <label>
                  <span>手机号、账号或邮箱</span>
                  <i>
                    <UserRound />
                    <input value={account} onChange={(event) => setAccount(event.target.value)} placeholder="手机号、账号名或邮箱" />
                  </i>
                </label>
                <PasswordField value={password} onChange={setPassword} placeholder="请输入密码" />
              </>
            )}

            {mode === "admin" && (
              <>
                <label>
                  <span>管理员账号</span>
                  <i>
                    <UserRound />
                    <input value={account} onChange={(event) => setAccount(event.target.value)} placeholder="请输入管理员账号" />
                  </i>
                </label>
                <PasswordField value={password} onChange={setPassword} placeholder="请输入管理员密码" />
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
                  <input value={inviteCode} onChange={(event) => setInviteCode(event.target.value.toUpperCase())} placeholder="选填" />
                </i>
              </label>
            )}
            {message && <div className="account-error">{message}</div>}
            <button className="account-submit" type="submit" disabled={loading}>
              {loading ? "处理中..." : actionLabel}
              {isRegister ? <ArrowRight /> : <LogIn />}
            </button>
          </form>
          <div className="account-note">
            验证码用于确认本人操作。请勿向任何人泄露验证码，平台工作人员不会索要你的验证码或密码。
          </div>
        </section>
      </div>
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
  if (mode === "sms-login") return "短信验证码登录";
  if (mode === "password-login") return "手机号、账号或邮箱登录";
  if (mode === "sms-register") return "手机号注册";
  if (mode === "password-register") return "账号密码注册";
  return "管理员登录";
}

function actionForMode(mode: Mode) {
  if (mode === "sms-login") return "验证码登录";
  if (mode === "password-login") return "密码登录";
  if (mode === "sms-register") return "手机号注册并领取 5 次免费机会";
  if (mode === "password-register") return "账号注册并领取 5 次免费机会";
  return "登录管理台";
}

function helperForMode(mode: Mode) {
  if (mode === "sms-login") return "输入手机号并获取短信验证码，无需密码即可登录。";
  if (mode === "password-login") return "可以使用手机号、账号名或注册邮箱登录。";
  if (mode === "sms-register") return "手机号验证码注册适合快速开始，设置密码后赠送 5 次免费使用机会。";
  if (mode === "password-register") return "填写账号名、注册邮箱和密码；邮箱验证码通过后即可创建账号。";
  return "管理员保留密码登录，避免短信或邮件服务异常时无法进入后台。";
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
