"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ExternalLink, LogOut } from "lucide-react";
import { useEffect, useState } from "react";
import { clearAuth, getAuthToken, getStoredUser, refreshCurrentUser, type UserProfile } from "@/lib/auth-client";
import { AdminEmailsPage, AdminFeedbackPage, AdminOrdersPage, AdminOverviewPage, AdminUpdatesPage, AdminUsersPage } from "@/components/admin/admin-pages";
import { AdminNavigation, adminSections, type AdminSection } from "@/components/admin/admin-navigation";

export function AdminConsole({ section }: { section: AdminSection }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserProfile | null>(() => getStoredUser());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getAuthToken()) {
      setLoading(false);
      const redirect = `${pathname}${window.location.search}`;
      router.replace(`/admin/login?redirect=${encodeURIComponent(redirect)}`);
      return;
    }
    refreshCurrentUser()
      .then((nextUser) => {
        setUser(nextUser);
        setLoading(false);
      })
      .catch(() => {
        clearAuth();
        setLoading(false);
        const redirect = `${pathname}${window.location.search}`;
        router.replace(`/admin/login?redirect=${encodeURIComponent(redirect)}`);
      });
  }, [pathname, router]);

  if (!loading && user?.role !== "admin") {
    return (
      <main className="admin-page">
        <section className="admin-locked">
          <h1>管理员面板</h1>
          <p>当前登录账号没有运营管理权限。</p>
          <Link href="/">返回网站</Link>
        </section>
      </main>
    );
  }

  const currentLabel = adminSections.find((item) => item.key === section)?.label || "运营管理台";

  return (
    <main className="admin-page">
      <div className="admin-layout">
        <aside className="admin-sidebar">
          <Link className="admin-sidebar-brand" href="/">盈航运营台</Link>
          <AdminNavigation active={section} />
        </aside>
        <section className="admin-shell">
          <header className="admin-topbar">
            <div>
              <h1>{currentLabel}</h1>
            </div>
            <div className="admin-actions">
              <Link href="/"><ExternalLink aria-hidden="true" />返回网站</Link>
              <button
                type="button"
                onClick={() => {
                  clearAuth();
                  setUser(null);
                  router.push("/admin/login");
                }}
              >
                <LogOut aria-hidden="true" />
                退出
              </button>
            </div>
          </header>

          <div className="admin-mobile-section-switcher">
            <AdminNavigation active={section} />
          </div>

          {loading ? <div className="admin-alert">正在校验管理员身份...</div> : null}
          {!loading && user?.role === "admin" ? <AdminSectionContent section={section} /> : null}
        </section>
      </div>
    </main>
  );
}

function AdminSectionContent({ section }: { section: AdminSection }) {
  if (section === "users") return <AdminUsersPage />;
  if (section === "orders") return <AdminOrdersPage />;
  if (section === "feedback") return <AdminFeedbackPage />;
  if (section === "updates") return <AdminUpdatesPage />;
  if (section === "emails") return <AdminEmailsPage />;
  return <AdminOverviewPage />;
}
