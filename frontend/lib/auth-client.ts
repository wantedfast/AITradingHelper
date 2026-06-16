"use client";

export type UserProfile = {
  id: number;
  phone: string;
  username?: string | null;
  email?: string | null;
  role: "user" | "admin";
  invite_code: string;
  credits: number;
  referral_count: number;
  created_at: string;
};

export type AuthResult = {
  token: string;
  user: UserProfile;
};

const TOKEN_KEY = "ai_trade_token";
const USER_KEY = "ai_trade_user";
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

export function getAuthToken() {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_KEY) || "";
}

export function getStoredUser(): UserProfile | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserProfile;
  } catch {
    return null;
  }
}

export function storeAuth(result: AuthResult) {
  window.localStorage.setItem(TOKEN_KEY, result.token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(result.user));
  window.dispatchEvent(new CustomEvent("ai-trade-auth", { detail: result.user }));
}

export function storeUser(user: UserProfile | null) {
  if (user) {
    window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  } else {
    window.localStorage.removeItem(USER_KEY);
  }
  window.dispatchEvent(new CustomEvent("ai-trade-auth", { detail: user }));
}

export function clearAuth() {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
  window.dispatchEvent(new CustomEvent("ai-trade-auth", { detail: null }));
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getAuthToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers, cache: "no-store" });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(payload?.error || payload?.detail || "请求失败");
  }
  return payload as T;
}

export async function refreshCurrentUser() {
  const payload = await apiFetch<{ user: UserProfile | null }>("/api/auth/me");
  storeUser(payload.user);
  return payload.user;
}

export function inviteUrl(user: UserProfile | null) {
  if (typeof window === "undefined" || !user?.invite_code) return "";
  const inviteCode = String(user.invite_code).replace(/[^A-Za-z0-9_-]/g, "").slice(0, 32);
  if (!inviteCode) return "";
  const url = new URL("/auth", window.location.origin);
  url.searchParams.set("invite", inviteCode);
  return url.toString();
}
