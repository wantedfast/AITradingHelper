"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";
import { ArrowLeft, KeyRound, Loader2, LockKeyhole, UserRound } from "lucide-react";
import { apiFetch, storeAuth, type AuthResult } from "@/lib/auth-client";

export default function AdminLoginPage() {
  return <Suspense fallback={<main className="admin-login-page" />}><AdminLoginForm /></Suspense>;
}

function AdminLoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage("");
    try {
      const result = await apiFetch<AuthResult>("/api/auth/admin-login", {
        method: "POST",
        body: JSON.stringify({ account, password }),
      });
      if (result.user.role !== "admin") throw new Error("当前账号没有运营管理权限");
      storeAuth(result);
      router.replace(safeAdminRedirect(params.get("redirect")));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "登录失败，请检查管理员账号和密码");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="admin-login-page">
      <section className="admin-login-card">
        <Link href="/"><ArrowLeft />返回网站</Link>
        <div className="admin-login-mark"><LockKeyhole /></div>
        <span>YINGHANG OPERATIONS</span>
        <h1>运营管理登录</h1>
        <p>此入口仅供运营管理员使用，普通用户请从网站登录页进入。</p>
        <form onSubmit={submit}>
          <label><span>管理员账号</span><i><UserRound /><input autoComplete="username" value={account} onChange={(event) => setAccount(event.target.value)} /></i></label>
          <label><span>管理员密码</span><i><KeyRound /><input autoComplete="current-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></i></label>
          {message ? <div className="admin-login-error" role="alert">{message}</div> : null}
          <button type="submit" disabled={loading || !account.trim() || !password}>{loading ? <Loader2 className="spin-icon" /> : <LockKeyhole />}{loading ? "正在验证" : "进入运营管理台"}</button>
        </form>
      </section>
    </main>
  );
}

function safeAdminRedirect(value: string | null) {
  if (!value || !value.startsWith("/admin") || value.startsWith("//") || value.includes(":") || value.includes("\\") || /[\u0000-\u001f\u007f]/.test(value)) return "/admin";
  return value;
}
