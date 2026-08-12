import { expect, test, type Page, type Route } from "@playwright/test";

const fixtureUser = {
  id: 1,
  phone: "13800000000",
  username: "admin-user",
  email: "admin@example.test",
  email_verified: true,
  email_binding_required: false,
  update_emails_enabled: true,
  role: "admin",
  invite_code: "ADMIN001",
  credits: 100,
  referral_count: 0,
  created_at: "2026-07-20T10:00:00+08:00",
};

const defaultUsers = [
  {
    id: 8,
    phone: "13800000008",
    username: "AlphaTrader",
    email: "alpha@example.com",
    role: "user",
    status: "active",
    used_count: 3,
    credits: 9,
    created_at: "2026-07-18T10:00:00+08:00",
    last_login_at: "2026-07-20T09:30:00+08:00",
  },
  {
    id: 9,
    phone: "13800000009",
    username: "AlphaSignal",
    email: "alpha-signal@example.com",
    role: "user",
    status: "active",
    used_count: 6,
    credits: 14,
    created_at: "2026-07-17T10:00:00+08:00",
    last_login_at: "2026-07-20T08:15:00+08:00",
  },
  {
    id: 10,
    phone: "13800000010",
    username: "GammaDesk",
    email: "ops-team@example.com",
    role: "user",
    status: "disabled",
    used_count: 1,
    credits: 12,
    created_at: "2026-07-16T10:00:00+08:00",
    last_login_at: "2026-07-19T20:00:00+08:00",
  },
];

const defaultOrders = [
  {
    id: 18,
    phone: "13800000008",
    username: "credit-user",
    email: "credit-user@example.com",
    order_no: "CREDIT-001",
    plan_name: "Credit Pack",
    credits: 12,
    amount_cents: 1200,
    status: "submitted",
    product_type: "credits",
    payment_method: "alipay",
    payer_name: "Tester",
    payer_paid_at: "2026-07-20T10:00:00+08:00",
    submitted_amount_cents: 1200,
    created_at: "2026-07-20T10:00:00+08:00",
  },
];

const defaultNotices = [
  {
    id: 21,
    title: "Route Draft Notice",
    version: "2026-07-21",
    items: ["Draft item one", "Draft item two"],
    summary: "Draft summary",
    status: "draft",
    created_at: "2026-07-21T10:00:00+08:00",
    updated_at: "2026-07-21T10:20:00+08:00",
    published_at: null,
    email_campaign: null,
  },
  {
    id: 22,
    title: "Route Published Notice",
    version: "2026-07-20",
    items: ["Published item one", "Published item two"],
    summary: "Published summary",
    status: "published",
    created_at: "2026-07-20T09:00:00+08:00",
    updated_at: "2026-07-20T09:30:00+08:00",
    published_at: "2026-07-20T09:30:00+08:00",
    email_campaign: {
      id: 501,
      status: "partial_failed",
      total: 6,
      pending: 0,
      sending: 0,
      sent: 4,
      failed: 1,
      skipped: 1,
    },
  },
];

const defaultEmails = [
  {
    id: 41,
    kind: "daily_top5",
    retry_type: "daily_top5",
    title: "Daily Top5 2026-07-16",
    summary: "Terminal failed daily top5 campaign",
    status: "partial_failed",
    total: 6,
    pending: 0,
    sending: 0,
    sent: 4,
    failed: 1,
    skipped: 1,
    created_at: "2026-07-16T09:26:00+08:00",
    next_retry_at: null,
    full: 2,
    teaser: 4,
  },
  {
    id: 44,
    kind: "daily_top5_close",
    retry_type: "daily_top5_close",
    title: "Daily Top5 Close 2026-07-16",
    summary: "Terminal failed daily top5 close campaign",
    status: "partial_failed",
    total: 6,
    pending: 0,
    sending: 0,
    sent: 5,
    failed: 1,
    skipped: 0,
    created_at: "2026-07-16T15:12:00+08:00",
    next_retry_at: null,
    full: 6,
    teaser: 0,
  },
  {
    id: 42,
    kind: "market_day",
    retry_type: "ai_report",
    title: "Market Day 2026-07-16",
    summary: "Automatic retry pending",
    status: "pending",
    total: 5,
    pending: 2,
    sending: 0,
    sent: 2,
    failed: 0,
    skipped: 1,
    created_at: "2026-07-16T16:00:00+08:00",
    next_retry_at: "2026-07-16T16:30:00+08:00",
    full: 1,
    teaser: 3,
  },
  {
    id: 43,
    kind: "ai_research",
    retry_type: "ai_report",
    title: "AI Research 2026-07-16",
    summary: "Terminal failed AI research campaign",
    status: "partial_failed",
    total: 5,
    pending: 0,
    sending: 0,
    sent: 3,
    failed: 1,
    skipped: 1,
    created_at: "2026-07-16T07:30:00+08:00",
    next_retry_at: null,
    full: 1,
    teaser: 3,
  },
];

const defaultDashboard = {
  totals: { users: 4, credits: 32, feedback_pending: 1, orders_paid: 2 },
  usage_by_day: [],
  new_users_by_day: [],
  feedback: [{ status: "pending" }],
  orders: [{ status: "submitted" }],
  update_notices: [defaultNotices[1]],
  daily_top5_email_failed_count: 1,
  daily_top5_close_email_failed_count: 2,
  ai_report_email_failed_count: 1,
  analytics: {
    feature_usage: {
      totals: [
        { feature: "auction_strength_view", count: 8, credits: 16, share: 0.5 },
        { feature: "market_day_report", count: 5, credits: 5, share: 0.3125 },
        { feature: "ai_research_view", count: 3, credits: 6, share: 0.1875 },
      ],
      by_day: [
        { day: "2026-07-14", feature: "auction_strength_view", count: 3, credits: 6 },
        { day: "2026-07-15", feature: "auction_strength_view", count: 5, credits: 10 },
        { day: "2026-07-14", feature: "market_day_report", count: 2, credits: 2 },
        { day: "2026-07-15", feature: "market_day_report", count: 3, credits: 3 },
        { day: "2026-07-15", feature: "ai_research_view", count: 3, credits: 6 },
      ],
    },
    user_growth: {
      starting_users: 18,
      total_users: 21,
      by_day: [
        { day: "2026-07-14", new_users: 1, cumulative_users: 19 },
        { day: "2026-07-15", new_users: 2, cumulative_users: 21 },
      ],
    },
    recent_usage_events: [
      {
        user_id: 8,
        display_name: "AlphaTrader",
        feature: "review_report",
        status: "charged",
        credits_spent: 2,
        related_id: "report-001",
        used_at: "2026-07-20T09:26:15+08:00",
        market_session: "before_open",
      },
    ],
  },
};

type AdminCapture = {
  adminLoginBodies?: Array<Record<string, unknown>>;
  statusActionBody?: Record<string, unknown>;
  statusActionPath?: string;
  orderActionBody?: Record<string, unknown>;
  orderActionPath?: string;
  noticeCreateBody?: Record<string, unknown>;
  noticePublishBody?: Record<string, unknown>;
  noticeRetryPath?: string;
  emailRetryPaths?: string[];
  emailProviderSelectBody?: Record<string, unknown>;
  emailProviderTestBody?: Record<string, unknown>;
};

type FixtureOptions = {
  seedAuth?: boolean;
  capture?: AdminCapture;
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function readJson(route: Route) {
  const body = route.request().postData();
  return body ? JSON.parse(body) as Record<string, unknown> : {};
}

function paginate<T>(items: T[], page: number, pageSize: number) {
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(page, 1), totalPages);
  const start = (safePage - 1) * pageSize;
  return {
    items: items.slice(start, start + pageSize),
    page: safePage,
    page_size: pageSize,
    total,
    total_pages: totalPages,
  };
}

function inDateRange(value: string, from: string, to: string) {
  const date = value.slice(0, 10);
  if (from && date < from) return false;
  if (to && date > to) return false;
  return true;
}

async function installAdminFixtures(page: Page, options: FixtureOptions = {}) {
  const capture = options.capture;
  const state = {
    users: clone(defaultUsers),
    orders: clone(defaultOrders),
    notices: clone(defaultNotices),
    emails: clone(defaultEmails),
    emailProvider: {
      provider: "smtp",
      worker_count: 1,
      smtp: { configured: true, from_masked: "no****@qq.com" },
      outlook: {
        configured: true,
        connected: true,
        account_masked: "wa****************@hotmail.com",
        connected_at: "2026-08-10T22:00:00+08:00",
        updated_at: "2026-08-10T22:00:00+08:00",
        reconnect_required: false,
        last_error: "",
      },
    },
  };

  if (options.seedAuth !== false) {
    await page.addInitScript((user) => {
      window.localStorage.setItem("ai_trade_token", "admin-token");
      window.localStorage.setItem("ai_trade_user", JSON.stringify(user));
    }, fixtureUser);
  }

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path === "/api/auth/me") return json(route, { user: fixtureUser });

    if (path === "/api/auth/admin-login" && method === "POST") {
      capture?.adminLoginBodies?.push(readJson(route));
      return json(route, { token: "admin-token", user: fixtureUser });
    }

    if (path === "/api/admin/dashboard") return json(route, defaultDashboard);

    if (path === "/api/admin/users") {
      const status = url.searchParams.get("status") || "all";
      const query = (url.searchParams.get("q") || "").toLowerCase();
      const requestedPage = Number(url.searchParams.get("page") || "1");
      const filtered = state.users.filter((item) => {
        const statusMatch = status === "all" || item.status === status;
        const queryMatch = !query
          || item.username.toLowerCase().includes(query)
          || item.email.toLowerCase().includes(query)
          || item.phone.includes(query)
          || String(item.id) === query;
        return statusMatch && queryMatch;
      });
      const pageSize = query.includes("alpha") ? 1 : 25;
      return json(route, {
        ...paginate(filtered, requestedPage, pageSize),
        campaigns: [{
          id: 1,
          request_id: "credit-campaign-001",
          credits: 5,
          reason: "批量补偿",
          status: "completed",
          eligible_count: 2,
          granted_count: 2,
          created_at: "2026-07-20T10:00:00+08:00",
          completed_at: "2026-07-20T10:00:00+08:00",
        }],
      });
    }

    if (/^\/api\/admin\/users\/\d+\/credits$/.test(path) && method === "POST") {
      return json(route, { email_notification: { sent: true } });
    }

    if (/^\/api\/admin\/users\/\d+\/status$/.test(path) && method === "POST") {
      const body = readJson(route);
      const target = state.users.find((item) => path === `/api/admin/users/${item.id}/status`);
      if (!target) return json(route, { error: "missing user" }, 404);
      capture!.statusActionBody = body;
      capture!.statusActionPath = path;
      const nextStatus = String(body.status || target.status);
      target.status = nextStatus;
      return json(route, { user: { id: target.id, display_name: target.username, status: target.status } });
    }

    if (path === "/api/admin/credits/grant-all" && method === "POST") {
      return json(route, { campaign: { granted_count: 2, credits: 5 } });
    }

    if (path === "/api/admin/orders") {
      const status = url.searchParams.get("status") || "all";
      const query = (url.searchParams.get("q") || "").toLowerCase();
      const requestedPage = Number(url.searchParams.get("page") || "1");
      const filtered = state.orders.filter((item) => {
        const statusMatch = status === "all" || item.status === status;
        const haystacks = [item.order_no, item.username || "", item.email || "", item.phone].map((value) => value.toLowerCase());
        return statusMatch && (!query || haystacks.some((value) => value.includes(query)));
      });
      return json(route, paginate(filtered, requestedPage, 20));
    }

    if (/^\/api\/admin\/orders\/\d+\/(paid|confirm-membership|confirm-credits|reject-membership|reject-credits)$/.test(path) && method === "POST") {
      capture!.orderActionBody = readJson(route);
      capture!.orderActionPath = path;
      return json(route, { order: { id: 18, status: "paid" } });
    }

    if (path === "/api/admin/feedback") {
      return json(route, { items: [], page: 1, page_size: 20, total: 0, total_pages: 1 });
    }

    if (/^\/api\/admin\/feedback\/\d+$/.test(path) && method === "POST") {
      return json(route, { feedback: { id: 1, status: "accepted" } });
    }

    if (path === "/api/admin/update-notices" && method === "GET") {
      const status = url.searchParams.get("status") || "all";
      const requestedPage = Number(url.searchParams.get("page") || "1");
      const filtered = status === "all" ? state.notices : state.notices.filter((item) => item.status === status);
      return json(route, paginate(filtered, requestedPage, 12));
    }

    if (path === "/api/admin/update-notices" && method === "POST") {
      const body = readJson(route);
      capture!.noticeCreateBody = body;
      const notice = {
        id: 99,
        title: String(body.title || "Created notice"),
        version: String(body.version || "2026-07-23"),
        items: String(body.items_text || "").split(/\r?\n/).filter(Boolean),
        summary: String(body.summary || ""),
        content_markdown: String(body.content_markdown || ""),
        status: String(body.status || "draft"),
        created_at: "2026-07-23T10:00:00+08:00",
        updated_at: "2026-07-23T10:00:00+08:00",
        published_at: body.status === "published" ? "2026-07-23T10:00:00+08:00" : null,
        email_campaign: body.send_email
          ? { id: 777, status: "pending", total: 2, pending: 2, sending: 0, sent: 0, failed: 0, skipped: 0 }
          : null,
      };
      state.notices.unshift(notice);
      return json(route, { notice, email_campaign: notice.email_campaign }, 201);
    }

    if (/^\/api\/admin\/update-notices\/\d+$/.test(path) && method === "POST") {
      return json(route, { notice: { id: Number(path.split("/")[4]), status: "draft" } });
    }

    if (/^\/api\/admin\/update-notices\/\d+\/publish$/.test(path) && method === "POST") {
      capture!.noticePublishBody = readJson(route);
      return json(route, { notice: { id: Number(path.split("/")[4]), status: "published" }, email_campaign: null });
    }

    if (/^\/api\/admin\/update-notices\/\d+\/unpublish$/.test(path) && method === "POST") {
      return json(route, { notice: { id: Number(path.split("/")[4]), status: "archived" } });
    }

    if (/^\/api\/admin\/update-email-campaigns\/\d+\/retry$/.test(path) && method === "POST") {
      capture!.noticeRetryPath = path;
      return json(route, { email_campaign: { id: Number(path.split("/")[4]), status: "pending" } });
    }

    if (/^\/api\/admin\/(daily-top5-email-campaigns|daily-top5-close-email-campaigns|ai-report-email-campaigns)\/\d+\/retry$/.test(path) && method === "POST") {
      capture!.emailRetryPaths?.push(path);
      return json(route, { email_campaign: { id: Number(path.split("/")[4]), status: "pending" } });
    }

    if (path === "/api/admin/email-provider" && method === "GET") {
      return json(route, state.emailProvider);
    }

    if (path === "/api/admin/email-provider/select" && method === "POST") {
      const body = readJson(route);
      capture!.emailProviderSelectBody = body;
      state.emailProvider.provider = String(body.provider || "smtp");
      return json(route, state.emailProvider);
    }

    if (path === "/api/admin/email-provider/test" && method === "POST") {
      const body = readJson(route);
      capture!.emailProviderTestBody = body;
      return json(route, { sent: true, provider: state.emailProvider.provider, email: "te**@example.com" });
    }

    if (path === "/api/admin/email-provider/outlook/connect" && method === "POST") {
      return json(route, { authorization_url: "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize" }, 201);
    }

    if (path === "/api/admin/email-provider/outlook/disconnect" && method === "POST") {
      state.emailProvider.outlook.connected = false;
      state.emailProvider.provider = "smtp";
      return json(route, state.emailProvider);
    }

    if (/^\/api\/admin\/emails\/(update_notice|daily_top5|daily_top5_close|market_day|ai_research)\/\d+$/.test(path)) {
      return json(route, {
        kind: path.split("/")[4],
        campaign: { status: "partial_failed", total: 6, pending: 0, sending: 0, sent: 4, failed: 1, skipped: 1 },
        failed_deliveries: [{
          email: "failed-recipient@example.com",
          status: "failed",
          attempt_count: 3,
          last_error: "SMTP mailbox unavailable",
          next_attempt_at: null,
          updated_at: "2026-07-16T09:30:00+08:00",
        }],
      });
    }

    if (path === "/api/admin/emails") {
      const kind = url.searchParams.get("kind") || "all";
      const status = url.searchParams.get("status") || "all";
      const dateFrom = url.searchParams.get("date_from") || "";
      const dateTo = url.searchParams.get("date_to") || "";
      const requestedPage = Number(url.searchParams.get("page") || "1");
      const filtered = state.emails.filter((item) => {
        const kindMatch = kind === "all" || item.kind === kind;
        const statusMatch = status === "all" || item.status === status || (status === "failed" && item.status === "partial_failed");
        const dateMatch = inDateRange(item.created_at, dateFrom, dateTo);
        return kindMatch && statusMatch && dateMatch;
      });
      return json(route, {
        ...paginate(filtered, requestedPage, 20),
        delivery_totals: {
          sent: filtered.reduce((sum, item) => sum + item.sent, 0),
          pending: filtered.reduce((sum, item) => sum + item.pending, 0),
          sending: filtered.reduce((sum, item) => sum + item.sending, 0),
          failed: filtered.reduce((sum, item) => sum + item.failed, 0),
          skipped: filtered.reduce((sum, item) => sum + item.skipped, 0),
        },
      });
    }

    return json(route, { error: `unhandled fixture ${method} ${path}` }, 404);
  });
}

test.describe("admin routing", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("admin root redirects to overview and inactive sections unmount on navigation", async ({ page }) => {
    await installAdminFixtures(page, { capture: {} });

    await page.goto("/admin", { waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(/\/admin\/overview$/);
    await expect(page.locator(".admin-priority-grid")).toBeVisible();

    await page.locator(".admin-mobile-section-switcher a[href='/admin/users']").click();
    await expect(page).toHaveURL(/\/admin\/users$/);
    await expect(page.locator(".admin-user-card").first()).toBeVisible();
    await expect(page.locator(".admin-priority-grid")).toHaveCount(0);
  });

  test("overview keeps analytics days in the URL and mobile route links change sections", async ({ page }) => {
    await installAdminFixtures(page, { capture: {} });

    await page.goto("/admin?days=30", { waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(/\/admin\/overview\?days=30$/);
    await expect(page.locator(".admin-analytics-window button.active")).toHaveText(/30/);

    await page.locator(".admin-analytics-window button").first().click();
    await expect(page).toHaveURL(/\/admin\/overview\?days=7$/);
    await expect(page.locator(".admin-analytics-window button.active")).toHaveText(/7/);

    const switcher = page.locator(".admin-mobile-section-switcher");
    await switcher.locator("a[href='/admin/orders']").click();
    await expect(page).toHaveURL(/\/admin\/orders$/);
    await expect(switcher.locator("a[href='/admin/orders']")).toHaveAttribute("aria-current", "page");
  });

  test("users route restores URL-backed filters and pagination across navigation history", async ({ page }) => {
    await installAdminFixtures(page, { capture: {} });

    await page.goto("/admin/users", { waitUntil: "domcontentloaded" });
    const search = page.getByPlaceholder("搜索用户名、邮箱、手机号或用户 ID");

    await search.fill("alpha");
    await search.press("Enter");
    await expect(page).toHaveURL(/\/admin\/users\?q=alpha&status=all&page=1$/);
    await expect(page.getByText("AlphaTrader")).toBeVisible();
    await expect(page.getByText("AlphaSignal")).toHaveCount(0);

    await page.getByRole("button", { name: "下一页" }).click();
    await expect(page).toHaveURL(/\/admin\/users\?q=alpha&status=all&page=2$/);
    await expect(page.getByText("AlphaSignal")).toBeVisible();
    await expect(page.getByText("AlphaTrader")).toHaveCount(0);

    await page.goBack();
    await expect(page).toHaveURL(/\/admin\/users\?q=alpha&status=all&page=1$/);
    await expect(search).toHaveValue("alpha");
    await expect(page.getByText("AlphaTrader")).toBeVisible();
    await expect(page.getByText("AlphaSignal")).toHaveCount(0);

    await page.locator(".admin-mobile-section-switcher a[href='/admin/overview']").click();
    await expect(page).toHaveURL(/\/admin\/overview$/);
    await page.goBack();
    await expect(page).toHaveURL(/\/admin\/users\?q=alpha&status=all&page=1$/);
    await expect(search).toHaveValue("alpha");
  });

  test("users deep links restore search state and keep page bounds to the current result window", async ({ page }) => {
    await installAdminFixtures(page, { capture: {} });

    await page.goto("/admin/users?q=alpha&status=all&page=2", { waitUntil: "domcontentloaded" });
    await expect(page.getByPlaceholder("搜索用户名、邮箱、手机号或用户 ID")).toHaveValue("alpha");
    await expect(page.locator(".admin-user-card")).toHaveCount(1);
    await expect(page.getByText("AlphaSignal")).toBeVisible();
    await expect(page.getByText("AlphaTrader")).toHaveCount(0);
    await expect(page.locator(".admin-pagination")).toContainText("2 / 2");

    await page.getByRole("button", { name: "清空搜索" }).click();
    await expect(page).toHaveURL(/\/admin\/users\?status=all&page=1$/);
    await expect(page.locator(".admin-user-card")).toHaveCount(3);
  });

  test("users detail controls mount on demand and dangerous status changes post the confirmed target", async ({ page }) => {
    const capture: AdminCapture = { adminLoginBodies: [], emailRetryPaths: [] };
    await installAdminFixtures(page, { capture });

    await page.goto("/admin/users", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("button", { name: "暂停账号" })).toHaveCount(0);

    await page.getByRole("button", { name: "查看详情" }).first().click();
    await expect(page.getByRole("button", { name: "暂停账号" })).toBeVisible();

    await page.getByRole("button", { name: "暂停账号" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("对象：AlphaTrader")).toBeVisible();
    await expect(dialog.getByText("用户 ID：8")).toBeVisible();
    await page.getByRole("button", { name: "确认暂停" }).click();

    expect(capture.statusActionPath).toBe("/api/admin/users/8/status");
    expect(capture.statusActionBody).toEqual({ status: "disabled", expected_identity: "AlphaTrader" });
    await expect(page.getByText("账号“AlphaTrader”（用户 ID：8）已暂停，现有 session 已失效。")).toBeVisible();
  });

  test("orders confirm a credit top-up through the confirmation dialog before posting", async ({ page }) => {
    const capture: AdminCapture = { adminLoginBodies: [], emailRetryPaths: [] };
    await installAdminFixtures(page, { capture });

    await page.goto("/admin/orders?status=submitted", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".admin-order-table .admin-list-item")).toHaveCount(1);

    await page.locator(".admin-order-actions button").first().click();
    await expect(page.getByRole("dialog")).toBeVisible();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("订单：CREDIT-001")).toBeVisible();
    await expect(dialog.getByText("用户：credit-user")).toBeVisible();
    await page.getByRole("button", { name: "确认增加次数" }).click();

    expect(capture.orderActionPath).toBe("/api/admin/orders/18/confirm-credits");
    expect(capture.orderActionBody).toEqual({ admin_note: "已人工核对到账，增加次数" });
    await expect(page.getByText("订单已更新。")).toBeVisible();
  });

  test("emails distinguish auto-retry from terminal failures and retry only terminal tasks", async ({ page }) => {
    const capture: AdminCapture = { adminLoginBodies: [], emailRetryPaths: [] };
    await installAdminFixtures(page, { capture });

    await page.goto("/admin/emails", { waitUntil: "domcontentloaded" });

    const waitingItem = page.locator(".admin-list-item").filter({ has: page.getByText("Market Day 2026-07-16") });
    await expect(waitingItem.getByText(/16:30/)).toBeVisible();
    await expect(waitingItem.getByRole("button", { name: "重试失败邮件" })).toHaveCount(0);

    const retryableItem = page.locator(".admin-list-item").filter({ has: page.getByText("Daily Top5 2026-07-16") });
    await retryableItem.getByRole("button", { name: "查看失败详情" }).click();
    const detailDialog = page.getByRole("dialog", { name: "失败邮件详情" });
    await expect(detailDialog.getByText("failed-recipient@example.com")).toBeVisible();
    await expect(detailDialog.getByText("SMTP mailbox unavailable")).toBeVisible();
    await detailDialog.getByRole("button", { name: "关闭失败邮件详情" }).click();
    await expect(retryableItem.getByRole("button", { name: "重试失败邮件" })).toBeVisible();
    await retryableItem.getByRole("button", { name: "重试失败邮件" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "重试失败邮件" }).click();

    expect(capture.emailRetryPaths).toEqual(["/api/admin/daily-top5-email-campaigns/41/retry"]);
    await expect(page.getByText("失败邮件已重新加入发送队列。")).toBeVisible();
  });

  test("emails manage the active provider and send a safe test message", async ({ page }) => {
    const capture: AdminCapture = { adminLoginBodies: [], emailProviderSelectBody: {}, emailProviderTestBody: {} };
    await installAdminFixtures(page, { capture });

    await page.goto("/admin/emails", { waitUntil: "domcontentloaded" });
    await expect(page.getByText("邮件 worker：1")).toBeVisible();
    await expect(page.getByText("wa****************@hotmail.com", { exact: false })).toBeVisible();

    await page.getByRole("button", { name: "使用 Outlook" }).click();
    expect(capture.emailProviderSelectBody).toEqual({ provider: "outlook_graph" });
    await expect(page.getByText("已切换为 Outlook Graph 发件。")).toBeVisible();

    await page.getByRole("textbox", { name: "测试邮件收件邮箱" }).fill("tester@example.com");
    await page.getByRole("button", { name: "发送测试邮件" }).click();
    expect(capture.emailProviderTestBody).toEqual({ email: "tester@example.com" });
    await expect(page.getByText(/测试邮件已通过 outlook_graph/)).toBeVisible();
  });

  test("emails support the daily_top5_close kind filter, detail route, and close-campaign retry endpoint", async ({ page }) => {
    const capture: AdminCapture = { adminLoginBodies: [], emailRetryPaths: [] };
    await installAdminFixtures(page, { capture });

    await page.goto("/admin/emails?kind=daily_top5_close", { waitUntil: "domcontentloaded" });

    await expect(page.getByRole("combobox").first()).toHaveValue("daily_top5_close");
    await expect(page.getByText("Daily Top5 Close 2026-07-16")).toBeVisible();
    await expect(page.getByText("Daily Top5 2026-07-16")).toHaveCount(0);

    const closeItem = page.locator(".admin-list-item").filter({ has: page.getByText("Daily Top5 Close 2026-07-16") });
    await closeItem.getByRole("button", { name: "查看失败详情" }).click();
    const detailDialog = page.getByRole("dialog", { name: "失败邮件详情" });
    await expect(detailDialog.getByText("failed-recipient@example.com")).toBeVisible();
    await detailDialog.getByRole("button", { name: "关闭失败邮件详情" }).click();

    await closeItem.getByRole("button", { name: "重试失败邮件" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "重试失败邮件" }).click();

    expect(capture.emailRetryPaths).toEqual(["/api/admin/daily-top5-close-email-campaigns/44/retry"]);
  });

  test("overview exposes failed daily Top5 close emails and opens the matching failed filter", async ({ page }) => {
    await installAdminFixtures(page);

    await page.goto("/admin/overview", { waitUntil: "domcontentloaded" });

    const closeCard = page.getByRole("button", { name: /失败 TOP5 收盘邮件/ });
    await expect(closeCard).toContainText("2");
    await closeCard.click();

    await expect(page).toHaveURL(/\/admin\/emails\?status=failed&kind=daily_top5_close#email-tasks$/);
    await expect(page.getByRole("combobox").nth(0)).toHaveValue("daily_top5_close");
    await expect(page.getByRole("combobox").nth(1)).toHaveValue("failed");
    await expect(page.getByRole("heading", { name: "每日 TOP5 收盘失败邮件" })).toBeVisible();
    await expect(page.getByText("失败涉及 1 个任务")).toBeVisible();
    await expect(page.getByText("成功 5 · 失败 1 · 跳过 0")).toBeVisible();
    await expect(page.getByText("Daily Top5 Close 2026-07-16")).toBeVisible();
  });

  test("overview opens ordinary Top5 failures with dated campaign totals and recipient detail", async ({ page }) => {
    await installAdminFixtures(page);

    await page.goto("/admin/overview", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: /失败 TOP5 邮件/ }).click();

    await expect(page).toHaveURL(/\/admin\/emails\?status=failed&kind=daily_top5#email-tasks$/);
    await expect(page.getByRole("heading", { name: "每日 TOP5 失败邮件" })).toBeVisible();
    await expect(page.getByText("失败涉及 1 个任务")).toBeVisible();
    await expect(page.getByText("成功 4 · 失败 1 · 跳过 1")).toBeVisible();
    const campaign = page.locator(".admin-list-item").filter({ has: page.getByText("Daily Top5 2026-07-16") });
    await expect(campaign.getByText("成功 4 · 待发送 0 · 发送中 0 · 失败 1 · 跳过 1")).toBeVisible();
    await campaign.getByRole("button", { name: "查看失败详情" }).click();
    await expect(page.getByRole("dialog", { name: "失败邮件详情" }).getByText("failed-recipient@example.com")).toBeVisible();
  });

  test("updates publish with email from the simple form and keep mobile notice actions evenly laid out", async ({ page }) => {
    const capture: AdminCapture = { adminLoginBodies: [], emailRetryPaths: [] };
    await installAdminFixtures(page, { capture });

    await page.goto("/admin/updates?status=all", { waitUntil: "domcontentloaded" });
    await page.getByPlaceholder("公告标题，例如：本周更新").fill("Route Publish Notice");
    await page.getByPlaceholder("公告摘要（可选，会显示在正文前）").fill("路由发布摘要");
    await page.getByPlaceholder(/^Markdown 正文（必填）/).fill("## 更新\n- 修复路由\n- 增加邮件发布");
    await page.getByRole("button", { name: "保存并发布" }).click();

    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByText("Route Publish Notice")).toBeVisible();
    await page.getByRole("button", { name: "发布并推送" }).click();

    expect(capture.noticeCreateBody).toMatchObject({
      title: "Route Publish Notice",
      summary: "路由发布摘要",
      content_markdown: "## 更新\n- 修复路由\n- 增加邮件发布",
      status: "published",
      send_email: true,
    });
    expect(typeof capture.noticeCreateBody?.request_id).toBe("string");
    await expect(page.getByText("公告已发布，邮件任务已创建。")).toBeVisible();

    const layout = await page.locator(".admin-notice-item-actions").first().evaluate((element) => {
      const style = getComputedStyle(element);
      const buttons = Array.from(element.querySelectorAll("button")).map((button) => button.getBoundingClientRect());
      return {
        display: style.display,
        gap: parseFloat(style.columnGap),
        widths: buttons.map((button) => button.width),
        horizontalSpace: buttons.length === 2 ? buttons[1].left - buttons[0].right : 0,
      };
    });
    expect(layout.display).toBe("grid");
    expect(layout.gap).toBeGreaterThanOrEqual(8);
    expect(Math.abs(layout.widths[0] - layout.widths[1])).toBeLessThan(1);
    expect(layout.horizontalSpace).toBeGreaterThanOrEqual(8);
  });

  test("admin login keeps safe internal redirects and collapses unsafe redirects to the admin root", async ({ page }) => {
    const capture: AdminCapture = { adminLoginBodies: [], emailRetryPaths: [] };
    await installAdminFixtures(page, { seedAuth: false, capture });

    await page.goto("/admin/login?redirect=%2Fadmin%2Fusers%3Fq%3Dalpha%26status%3Dall%26page%3D2", { waitUntil: "networkidle" });
    await page.locator('input[autocomplete="username"]').fill("admin");
    await page.locator('input[autocomplete="current-password"]').fill("secret");
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/admin\/users\?q=alpha&status=all&page=2$/);
    await expect(page.getByPlaceholder("搜索用户名、邮箱、手机号或用户 ID")).toHaveValue("alpha");

    await page.evaluate(() => window.localStorage.clear());
    await page.goto(`/admin/login?redirect=${encodeURIComponent("https://example.com")}`, { waitUntil: "networkidle" });
    await page.locator('input[autocomplete="username"]').fill("admin");
    await page.locator('input[autocomplete="current-password"]').fill("secret");
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/admin\/overview$/);

    expect(capture.adminLoginBodies).toEqual([
      { account: "admin", password: "secret" },
      { account: "admin", password: "secret" },
    ]);
  });
});
