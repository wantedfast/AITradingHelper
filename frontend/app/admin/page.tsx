"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { BarChart3, CheckCircle2, CreditCard, Gift, LogOut, MessageSquare, RefreshCw, Users } from "lucide-react";
import { apiFetch, clearAuth, getStoredUser, refreshCurrentUser, type UserProfile } from "@/lib/auth-client";

type DashboardPayload = {
  totals: {
    users: number;
    credits: number;
    feedback_pending: number;
    orders_paid: number;
  };
  usage_by_day: Array<{ day: string; feature: string; count: number; credits: number }>;
  new_users_by_day: Array<{ day: string; count: number }>;
  feedback: Array<{
    id: number;
    phone: string;
    category: string;
    content: string;
    contact: string;
    status: string;
    reward_credits: number;
    created_at: string;
  }>;
  orders: Array<{
    id: number;
    phone: string;
    order_no: string;
    plan_name: string;
    credits: number;
    amount_cents: number;
    status: string;
    created_at: string;
  }>;
  top_users: Array<{ id: number; phone: string; role: string; used_count: number; credits: number; created_at: string }>;
};

export default function AdminPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserProfile | null>(() => getStoredUser());
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  useEffect(() => {
    refreshCurrentUser()
      .then((nextUser) => {
        setUser(nextUser);
        if (nextUser?.role === "admin") return loadDashboard();
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  async function loadDashboard() {
    setLoading(true);
    setMessage("");
    try {
      const payload = await apiFetch<DashboardPayload>("/api/admin/dashboard?days=14");
      setData(payload);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取统计失败");
    } finally {
      setLoading(false);
    }
  }

  async function acceptFeedback(id: number) {
    await apiFetch(`/api/admin/feedback/${id}`, {
      method: "POST",
      body: JSON.stringify({ status: "accepted", admin_note: "反馈已采纳，奖励 10 次免费机会" }),
    });
    await loadDashboard();
  }

  async function markPaid(id: number) {
    await apiFetch(`/api/admin/orders/${id}/paid`, { method: "POST" });
    await loadDashboard();
  }

  const chartMax = useMemo(() => {
    const values = data?.usage_by_day.map((item) => item.count) || [];
    return Math.max(1, ...values);
  }, [data]);

  if (!loading && user?.role !== "admin") {
    return (
      <main className="admin-page">
        <section className="admin-locked">
          <h1>管理员面板</h1>
          <p>需要管理员账号登录后查看。</p>
          <Link href="/auth?redirect=/admin">登录管理员账号</Link>
        </section>
      </main>
    );
  }

  return (
    <main className="admin-page">
      <section className="admin-shell">
        <header className="admin-topbar">
          <div>
            <Link href="/">盈航</Link>
            <h1>运营管理台</h1>
            <p>查看用户增长、功能使用、反馈奖励和订单状态。</p>
          </div>
          <div className="admin-actions">
            <button type="button" onClick={loadDashboard}>
              <RefreshCw />
              刷新
            </button>
            <button
              type="button"
              onClick={() => {
                clearAuth();
                setUser(null);
                router.push("/auth");
              }}
            >
              <LogOut />
              退出
            </button>
          </div>
        </header>

        {message && <div className="admin-alert">{message}</div>}
        {loading && <div className="admin-alert">正在读取统计数据...</div>}

        {data && (
          <>
            <section className="admin-metrics">
              <Metric icon={Users} label="普通用户" value={data.totals.users} />
              <Metric icon={Gift} label="系统剩余次数" value={data.totals.credits} />
              <Metric icon={MessageSquare} label="待审核反馈" value={data.totals.feedback_pending} />
              <Metric icon={CreditCard} label="已支付订单" value={data.totals.orders_paid} />
            </section>

            <section className="admin-grid">
              <article className="admin-panel admin-chart-panel">
                <div className="admin-panel-head">
                  <BarChart3 />
                  <h2>近 14 日功能使用</h2>
                </div>
                <div className="admin-chart">
                  {data.usage_by_day.length ? (
                    data.usage_by_day.map((item) => (
                      <div key={`${item.day}-${item.feature}`}>
                        <span>{item.day.slice(5)} · {featureLabel(item.feature)}</span>
                        <i style={{ width: `${Math.max(8, (item.count / chartMax) * 100)}%` }} />
                        <b>{item.count}</b>
                      </div>
                    ))
                  ) : (
                    <p>暂无使用记录。</p>
                  )}
                </div>
              </article>

              <article className="admin-panel">
                <div className="admin-panel-head">
                  <Users />
                  <h2>高频用户</h2>
                </div>
                <div className="admin-table">
                  {data.top_users.map((item) => (
                    <div key={item.id}>
                      <span>{item.phone}</span>
                      <b>{item.used_count} 次使用</b>
                      <em>{item.credits} 次余额</em>
                    </div>
                  ))}
                </div>
              </article>
            </section>

            <section className="admin-grid">
              <article className="admin-panel">
                <div className="admin-panel-head">
                  <MessageSquare />
                  <h2>反馈建议</h2>
                </div>
                <div className="admin-list">
                  {data.feedback.map((item) => (
                    <div className="admin-list-item" key={item.id}>
                      <header>
                        <b>{item.category}</b>
                        <span>{item.status}</span>
                      </header>
                      <p>{item.content}</p>
                      <small>{item.phone} · {formatDate(item.created_at)}</small>
                      {item.status === "pending" && (
                        <button type="button" onClick={() => acceptFeedback(item.id)}>
                          <CheckCircle2 />
                          采纳并奖励 10 次
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </article>

              <article className="admin-panel">
                <div className="admin-panel-head">
                  <CreditCard />
                  <h2>订单系统</h2>
                </div>
                <div className="admin-list">
                  {data.orders.map((item) => (
                    <div className="admin-list-item" key={item.id}>
                      <header>
                        <b>{item.plan_name}</b>
                        <span>{item.status}</span>
                      </header>
                      <p>{item.credits} 次 · ¥{(item.amount_cents / 100).toFixed(2)}</p>
                      <small>{item.phone} · {item.order_no}</small>
                      {item.status !== "paid" && (
                        <button type="button" onClick={() => markPaid(item.id)}>
                          <CheckCircle2 />
                          标记已支付
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </article>
            </section>
          </>
        )}
      </section>
    </main>
  );
}

function Metric({ icon: Icon, label, value }: { icon: typeof Users; label: string; value: number }) {
  return (
    <article>
      <Icon />
      <span>{label}</span>
      <b>{value}</b>
    </article>
  );
}

function featureLabel(value: string) {
  if (value === "review_report") return "AI 复盘";
  if (value === "watch_plan") return "AI 盯盘";
  return value;
}

function formatDate(value: string) {
  return value ? value.slice(0, 16).replace("T", " ") : "";
}
