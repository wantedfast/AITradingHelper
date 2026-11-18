import { expect, test, type Page, type Route } from "@playwright/test";

// Membership payment reliability: the checkout must never show a QR code
// without a persisted order, must survive API outages without making the user
// pay twice, and the admin must be able to tell "unreported" from "to verify".

const memberUser = {
  id: 7,
  phone: "13800000007",
  username: "renewing-member",
  email: "member@example.test",
  email_verified: true,
  email_binding_required: false,
  update_emails_enabled: true,
  role: "user",
  invite_code: "MEMBER07",
  credits: 0,
  membership_plan: "月度会员",
  membership_status: "expired",
  membership_expires_at: "2026-10-18T10:00:00+08:00",
  membership_active: false,
  referral_count: 0,
  created_at: "2026-07-15T00:00:00Z",
};

const adminUser = { ...memberUser, id: 1, username: "admin-user", role: "admin", invite_code: "ADMIN001" };

const membershipPlans = [
  { id: "monthly_membership", plan_name: "月度会员", amount_cents: 5900, duration_days: 31, wechat_qr_url: "/pay/wechat-qr.jpg" },
  { id: "annual_membership", plan_name: "年度会员", amount_cents: 39900, duration_days: 365, wechat_qr_url: "/pay/wechat-qr.jpg" },
];

const pendingOrder = {
  id: 501,
  order_no: "YMRECOVER501",
  plan_name: "月度会员",
  package_id: "monthly_membership",
  amount_cents: 5900,
  duration_days: 31,
  status: "pending",
  created_at: "2026-11-18T09:00:00+08:00",
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function seedSession(page: Page, user: typeof memberUser) {
  await page.addInitScript((seed) => {
    window.localStorage.setItem("ai_trade_token", "payment-token");
    window.localStorage.setItem("ai_trade_user", JSON.stringify(seed));
  }, user);
}

type BillingHandlers = {
  latest?: () => unknown;
  create?: (route: Route) => Promise<void> | void;
  submit?: (route: Route) => Promise<void> | void;
  order?: () => unknown;
};

async function installBillingFixtures(page: Page, handlers: BillingHandlers) {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (path === "/api/public/membership/plans") return json(route, { plans: membershipPlans, checkout: {} });
    if (path === "/api/update-notices/pending") return json(route, { notices: [] });
    if (path === "/api/pay/membership/orders/latest") {
      return json(route, { plans: membershipPlans, checkout: {}, user: memberUser, order: null, ...(handlers.latest?.() as object) });
    }
    if (path === "/api/pay/membership/orders" && method === "POST" && handlers.create) return handlers.create(route);
    if (/^\/api\/pay\/membership\/orders\/\d+\/submit$/.test(path) && method === "POST" && handlers.submit) return handlers.submit(route);
    if (/^\/api\/orders\/\d+$/.test(path)) return json(route, { order: handlers.order?.() || pendingOrder, user: memberUser });
    return json(route, {});
  });
}

test.describe("membership checkout recovery", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("a failed order creation never shows a payment QR code", async ({ page }) => {
    await seedSession(page, memberUser);
    await installBillingFixtures(page, {
      create: (route) => json(route, { error: "internal error" }, 503),
    });
    await page.goto("/billing?plan_id=monthly_membership", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "创建月度会员订单" }).click();
    await expect(page.locator(".billing-message")).toContainText("订单未创建成功，请不要付款");
    await expect(page.getByAltText("微信收款二维码")).toHaveCount(0);
    await expect(page.locator(".billing-order")).toHaveCount(0);
  });

  test("double click and retry after a failure send one idempotency key", async ({ page }) => {
    const requestIds: string[] = [];
    let attempts = 0;
    await seedSession(page, memberUser);
    await installBillingFixtures(page, {
      create: async (route) => {
        attempts += 1;
        requestIds.push(String(route.request().postDataJSON()?.client_request_id || ""));
        await new Promise((resolve) => setTimeout(resolve, 250));
        if (attempts === 1) return json(route, { error: "gateway" }, 502);
        return json(route, { order: pendingOrder, plans: membershipPlans, checkout: {}, user: memberUser });
      },
    });
    await page.goto("/billing?plan_id=monthly_membership", { waitUntil: "domcontentloaded" });
    const create = page.getByRole("button", { name: "创建月度会员订单" });
    await create.dblclick();
    await expect(page.locator(".billing-message")).toContainText("订单未创建成功");
    expect(attempts).toBe(1);
    await page.getByRole("button", { name: "创建月度会员订单" }).click();
    await expect(page.getByAltText("微信收款二维码")).toBeVisible();
    expect(attempts).toBe(2);
    expect(requestIds[0]).toMatch(/^mco-/);
    expect(requestIds[1]).toBe(requestIds[0]);
    // The QR code is always shown together with the order number and amount.
    await expect(page.getByTestId("billing-pay-hint")).toContainText("付款备注请填写订单号：YMRECOVER501");
    await expect(page.getByTestId("billing-pay-hint")).toContainText("¥59.00");
  });

  test("an expired member whose last order was paid is offered a new order, not the old QR", async ({ page }) => {
    await seedSession(page, memberUser);
    // Old backends return the paid order as `order`; the page must not resume it.
    await installBillingFixtures(page, {
      latest: () => ({ order: { ...pendingOrder, id: 400, order_no: "YMOLDPAID", status: "paid" } }),
    });
    await page.goto("/billing", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("button", { name: /创建.*订单/ })).toBeEnabled();
    await expect(page.getByAltText("微信收款二维码")).toHaveCount(0);
    await expect(page.getByText("YMOLDPAID")).toHaveCount(0);
  });

  test("pending order and typed payment info survive a reload, and an outage asks not to pay again", async ({ page }) => {
    let submitAttempts = 0;
    let lastSubmit: Record<string, unknown> = {};
    await seedSession(page, memberUser);
    await installBillingFixtures(page, {
      latest: () => ({ order: pendingOrder }),
      submit: (route) => {
        submitAttempts += 1;
        lastSubmit = route.request().postDataJSON() as Record<string, unknown>;
        if (submitAttempts === 1) return json(route, { error: "down" }, 503);
        return json(route, { order: { ...pendingOrder, status: "submitted", payer_name: lastSubmit.payer_name }, user: memberUser });
      },
    });
    await page.goto("/billing", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".billing-order")).toContainText("YMRECOVER501");
    await page.getByLabel("付款人昵称或姓名").fill("微信小王");
    await page.getByLabel("付款时间").fill("2026-11-18T09:15");

    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.locator(".billing-order")).toContainText("YMRECOVER501");
    await expect(page.getByLabel("付款人昵称或姓名")).toHaveValue("微信小王");
    await expect(page.getByLabel("付款时间")).toHaveValue("2026-11-18T09:15");

    await page.getByRole("button", { name: "我已付款，通知管理员" }).click();
    const alert = page.locator(".billing-payment-form [role='alert']");
    await expect(alert).toContainText("请不要重复付款");
    await expect(alert).toContainText("YMRECOVER501");
    await page.getByRole("button", { name: "重新提交付款信息" }).click();
    await expect.poll(() => submitAttempts).toBe(2);
    expect(lastSubmit).toMatchObject({ payment_method: "wechat", payer_name: "微信小王", submitted_amount_cents: 5900, payer_note: "YMRECOVER501" });
    await expect(page.locator(".billing-message")).toContainText("付款信息已提交");
  });

  // Regression: the page used to submit the amount of the default/URL plan,
  // so a restored monthly order went out as ¥399 and an annual one as ¥59.
  for (const scenario of [
    { name: "monthly order restored on the default (annual) page", url: "/billing", order: pendingOrder, expected: 5900 },
    {
      name: "annual order restored on the post-login monthly URL",
      url: "/billing?plan_id=monthly_membership",
      order: { ...pendingOrder, id: 502, order_no: "YMANNUAL502", plan_name: "年度会员", package_id: "annual_membership", amount_cents: 39900, duration_days: 365 },
      expected: 39900,
    },
  ]) {
    test(`submits the order's own amount: ${scenario.name}`, async ({ page }) => {
      let submitted: Record<string, unknown> = {};
      await seedSession(page, memberUser);
      await installBillingFixtures(page, {
        latest: () => ({ order: scenario.order }),
        submit: (route) => {
          submitted = route.request().postDataJSON() as Record<string, unknown>;
          return json(route, { order: { ...scenario.order, status: "submitted" }, user: memberUser });
        },
        order: () => scenario.order,
      });
      await page.goto(scenario.url, { waitUntil: "domcontentloaded" });
      await expect(page.locator(".billing-order")).toContainText(scenario.order.order_no);
      await expect(page.getByLabel("实付金额")).toHaveValue((scenario.expected / 100).toFixed(2));
      await expect(page.getByLabel("付款时间")).not.toHaveValue("");
      await page.getByLabel("付款人昵称或姓名").fill("微信小王");
      await page.getByRole("button", { name: "我已付款，通知管理员" }).click();
      await expect.poll(() => submitted.submitted_amount_cents).toBe(scenario.expected);
    });
  }

  test("a pending monthly order can be cancelled to switch to the annual plan", async ({ page }) => {
    let createdPlan = "";
    let cancelled = false;
    await seedSession(page, memberUser);
    await page.route("**/api/pay/membership/orders/501/cancel", (route) => {
      cancelled = true;
      return json(route, { order: { ...pendingOrder, status: "cancelled" } });
    });
    await installBillingFixtures(page, {
      latest: () => ({ order: cancelled ? null : pendingOrder }),
      create: (route) => {
        createdPlan = String(route.request().postDataJSON()?.plan_id || "");
        return json(route, {
          order: { ...pendingOrder, id: 503, order_no: "YMANNUAL503", plan_name: "年度会员", package_id: "annual_membership", amount_cents: 39900 },
          plans: membershipPlans,
          checkout: {},
          user: memberUser,
        });
      },
    });
    await page.goto("/billing", { waitUntil: "domcontentloaded" });
    const planCards = page.locator('.billing-plan-options button[role="radio"]');
    await expect(planCards.nth(1)).toBeEnabled();
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "取消此订单 / 更换套餐" }).click();
    await expect(planCards.nth(1)).toBeEnabled();
    await planCards.nth(1).click();
    await page.getByRole("button", { name: "创建年度会员订单" }).click();
    await expect.poll(() => createdPlan).toBe("annual_membership");
    await expect(page.getByLabel("实付金额")).toHaveValue("399.00");
  });

  test("a connection failure (server unreachable) is retryable and offline reload still names the order", async ({ page }) => {
    let apiDown = false;
    let submits = 0;
    await seedSession(page, memberUser);
    await installBillingFixtures(page, {
      latest: () => ({ order: pendingOrder }),
      submit: (route) => {
        submits += 1;
        return json(route, { order: { ...pendingOrder, status: "submitted" }, user: memberUser });
      },
    });
    // Registered last so it runs first (Playwright evaluates routes LIFO).
    await page.route("**/api/**", async (route) => {
      if (apiDown) return route.abort("connectionrefused");
      return route.fallback();
    });
    await page.goto("/billing", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".billing-order")).toContainText("YMRECOVER501");
    await page.getByLabel("付款人昵称或姓名").fill("微信小王");

    apiDown = true;
    await page.getByRole("button", { name: "我已付款，通知管理员" }).click();
    const alert = page.locator(".billing-payment-form [role='alert']");
    await expect(alert).toContainText("付款信息暂未送达服务器");
    await expect(alert).toContainText("请不要重复付款");
    await expect(alert).not.toContainText("。。");
    await expect(page.getByRole("button", { name: "重新提交付款信息" })).toBeVisible();

    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.locator(".billing-message")).toContainText("你有一笔未完成的月度会员订单 YMRECOVER501");
    await expect(page.getByRole("button", { name: "重新加载" })).toBeVisible();

    apiDown = false;
    await page.getByRole("button", { name: "重新加载" }).click();
    await expect(page.getByLabel("付款人昵称或姓名")).toHaveValue("微信小王");
    await page.getByRole("button", { name: "我已付款，通知管理员" }).click();
    await expect.poll(() => submits).toBe(1);
  });

  test("checkout shows only the enabled WeChat method even for legacy Alipay orders", async ({ page }) => {
    await seedSession(page, memberUser);
    await installBillingFixtures(page, {
      latest: () => ({ order: { ...pendingOrder, status: "rejected", payment_method: "alipay", admin_note: "未查到到账" } }),
    });
    await page.goto("/billing", { waitUntil: "domcontentloaded" });
    await expect(page.getByAltText("微信收款二维码")).toBeVisible();
    await expect(page.getByLabel("付款方式")).toHaveValue("微信支付");
    await expect(page.getByText("支付宝", { exact: false })).toHaveCount(0);
    await expect(page.locator(".billing-checkout [role='alert']")).toContainText("未查到到账");
  });
});

test.describe("membership checkout usability", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("shows the member's own status, copies the order number and points at the empty field", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    let submits = 0;
    await seedSession(page, memberUser);
    await installBillingFixtures(page, {
      latest: () => ({ order: pendingOrder }),
      submit: (route) => {
        submits += 1;
        return json(route, { order: { ...pendingOrder, status: "submitted" }, user: memberUser });
      },
    });
    await page.goto("/billing", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".billing-topbar")).toContainText("你的会员已于 2026-10-18 到期");
    await page.getByRole("button", { name: "复制订单号" }).click();
    await expect(page.getByRole("button", { name: "已复制订单号" })).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("YMRECOVER501");

    await page.getByRole("button", { name: "我已付款，通知管理员" }).click();
    const nameField = page.getByLabel("付款人昵称或姓名");
    await expect(nameField).toBeFocused();
    await expect(nameField).toHaveAttribute("aria-invalid", "true");
    await expect(page.locator(".billing-payment-form")).toContainText("请填写付款人微信昵称或姓名");
    expect(submits).toBe(0);
    await nameField.fill("微信小王");
    await expect(nameField).not.toHaveAttribute("aria-invalid", "true");
    await page.getByRole("button", { name: "我已付款，通知管理员" }).click();
    await expect.poll(() => submits).toBe(1);
  });
});

test.describe("membership checkout on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("create a second monthly order and withdraw only the earlier report from history", async ({ page }) => {
    await seedSession(page, memberUser);
    const original = {...pendingOrder, status: "submitted"};
    const second = {...pendingOrder, id: 502, order_no: "YMSECOND502"};
    await installBillingFixtures(page, {latest: () => ({order: original}), create: route => json(route, {order: second})});
    await page.route("**/api/pay/membership/orders?before=0", route => json(route, {orders: [second, original], next_before: null}));
    await page.route("**/api/pay/membership/orders/501/cancel", route => {
      original.status = "cancelled";
      return json(route, {order: original});
    });
    await page.goto("/billing", {waitUntil: "domcontentloaded"});
    await page.getByRole("button", {name: "再买一份"}).click();
    await page.getByRole("button", {name: "创建月度会员订单"}).click();
    await expect(page.locator(".billing-order")).toContainText(second.order_no);
    await page.getByRole("button", {name: "我的订单", exact: true}).click();
    const history = page.getByRole("region", {name: "我的会员订单"});
    page.once("dialog", dialog => dialog.accept());
    await history.getByRole("button", {name: "我没有付款，取消订单"}).click();
    await expect(history.locator("article").filter({hasText: original.order_no})).toContainText("已取消");
    await expect(page.locator(".billing-order")).toContainText(second.order_no);
    await expect(history.locator("article").filter({hasText: second.order_no})).toContainText("待付款");
  });

  test("after scanning, the submit form is one tap away and plan switching is explained", async ({ page }) => {
    await seedSession(page, memberUser);
    await installBillingFixtures(page, { latest: () => ({ order: pendingOrder }) });
    await page.goto("/billing", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".billing-plan-locked")).toContainText("年度会员");
    await expect(page.getByRole("button", { name: "再买一份" })).toBeVisible();
    const jump = page.getByRole("button", { name: "已付款？点这里提交付款信息" });
    await jump.scrollIntoViewIfNeeded();
    await jump.click();
    await expect(page.getByLabel("付款人昵称或姓名")).toBeInViewport();
    await expect(page.getByLabel("付款人昵称或姓名")).toBeFocused();
  });
});

const orderCounts = { all: 4, attention: 3, pending: 2, pending_recent: 2, submitted: 1, paid: 1, rejected: 0, cancelled: 0, notify_failed: 1 };

const adminOrders = [
  {
    id: 601,
    user_id: 7,
    phone: "13800000007",
    username: "renewing-member",
    email: "member@example.test",
    order_no: "YMSUBMIT601",
    plan_name: "月度会员",
    package_id: "monthly_membership",
    credits: 0,
    amount_cents: 5900,
    status: "submitted",
    product_type: "membership",
    payment_method: "wechat",
    payer_name: "微信小王",
    payer_paid_at: "2026-11-18T09:15",
    submitted_amount_cents: 5900,
    payer_note: "YMSUBMIT601",
    user_membership_active: false,
    user_membership_expires_at: "2026-10-18T10:00:00+08:00",
    submitted_at: "2026-11-18T09:16:00+08:00",
    admin_notify_status: "failed",
    created_at: "2026-11-18T09:00:00+08:00",
    events: [
      { event: "created", from_status: "", to_status: "pending", actor_role: "user", note: "", created_at: "2026-11-18T09:00:00+08:00" },
      { event: "payment_submitted", from_status: "pending", to_status: "submitted", actor_role: "user", note: "", created_at: "2026-11-18T09:16:00+08:00" },
    ],
  },
  {
    id: 602,
    user_id: 8,
    phone: "13800000008",
    username: "silent-payer",
    email: "silent@example.test",
    order_no: "YMPENDING602",
    plan_name: "月度会员",
    package_id: "monthly_membership",
    credits: 0,
    amount_cents: 5900,
    status: "pending",
    product_type: "membership",
    unreported_payment: true,
    created_at: "2026-11-18T08:00:00+08:00",
    events: [],
  },
];

async function installAdminFixtures(page: Page, capture: { grantBody?: Record<string, unknown>; orderQueries: string[] }) {
  await seedSession(page, adminUser);
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();
    if (path === "/api/auth/me") return json(route, { user: adminUser });
    if (path === "/api/public/membership/plans") return json(route, { plans: membershipPlans, checkout: {} });
    if (path === "/api/admin/dashboard") {
      return json(route, {
        totals: { users: 2, credits: 0, feedback_pending: 0, orders_paid: 1 },
        usage_by_day: [],
        new_users_by_day: [],
        feedback: [],
        orders: [],
        order_counts: orderCounts,
        update_notices: [],
        analytics: {
          window: { days: 30, start_date: "2026-10-20", end_date: "2026-11-18" },
          feature_usage: { totals: [], by_day: [] },
          user_growth: { starting_users: 0, total_users: 2, by_day: [] },
          high_frequency_users: [],
          recent_usage_events: [],
        },
      });
    }
    if (path === "/api/admin/orders") {
      capture.orderQueries.push(url.search);
      const status = url.searchParams.get("status") || "all";
      const query = (url.searchParams.get("q") || "").toLowerCase();
      const items = adminOrders.filter((item) => {
        const statusMatch = status === "all" || item.status === status || (status === "attention" && ["pending", "submitted", "rejected"].includes(item.status));
        const haystack = [item.order_no, item.payer_name || "", item.payer_note || "", item.username].join(" ").toLowerCase();
        return statusMatch && (!query || haystack.includes(query));
      });
      return json(route, { items, page: 1, page_size: 20, total: items.length, total_pages: 1, status_counts: orderCounts });
    }
    if (path === "/api/admin/memberships/manual-grant" && method === "POST") {
      capture.grantBody = route.request().postDataJSON() as Record<string, unknown>;
      return json(route, {
        order: { ...adminOrders[1], status: "paid" },
        user: { membership_expires_at: "2026-12-19T10:00:00+08:00" },
        ledger_id: 9,
        request_id: capture.grantBody.request_id,
        idempotent: false,
      });
    }
    return json(route, {});
  });
}

test.describe("admin payment reconciliation", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("overview separates unreported pending orders from orders awaiting verification", async ({ page }) => {
    const capture = { orderQueries: [] as string[] };
    await installAdminFixtures(page, capture);
    // Enter via /admin: the redirect cancels the first dashboard request,
    // which used to surface as a false "网络连接失败" banner.
    await page.goto("/admin", { waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(/\/admin\/overview/);
    await expect(page.locator(".admin-priority-grid")).toBeVisible();
    await page.waitForTimeout(500);
    await expect(page.getByText("网络连接失败")).toHaveCount(0);
    const grid = page.locator(".admin-priority-grid");
    const submittedCard = grid.getByRole("button", { name: /待核款订单/ });
    const pendingCard = grid.getByRole("button", { name: /未报告付款订单/ });
    await expect(submittedCard).toContainText("1");
    await expect(submittedCard).toContainText("提醒邮件失败");
    await expect(pendingCard).toContainText("2");
    await expect(pendingCard).toContainText("不代表已付款");
    await pendingCard.click();
    await expect(page).toHaveURL(/\/admin\/orders\?status=pending/);
    await expect(page.locator(".admin-order-table .admin-list-item")).toHaveCount(1);
    await expect(page.locator(".admin-order-table")).toContainText("未报告付款");
  });

  test("orders page shows labelled counts, searches by payer nickname and records a manual grant", async ({ page }) => {
    const capture: { grantBody?: Record<string, unknown>; orderQueries: string[] } = { orderQueries: [] };
    await installAdminFixtures(page, capture);
    await page.goto("/admin/orders?status=attention", { waitUntil: "domcontentloaded" });
    const filters = page.locator(".admin-order-status-filters");
    await expect(filters.getByRole("tab", { name: /待核款/ })).toContainText("1");
    await expect(filters.getByRole("tab", { name: /未报告付款/ })).toContainText("2");
    await expect(page.locator(".admin-order-table .admin-list-item")).toHaveCount(2);
    await expect(page.locator(".admin-order-table")).toContainText("提醒邮件发送失败");

    await page.getByPlaceholder(/付款昵称/).fill("微信小王");
    await page.getByPlaceholder(/付款昵称/).press("Enter");
    await expect(page.locator(".admin-order-table .admin-list-item")).toHaveCount(1);
    expect(capture.orderQueries.some((query) => query.includes(encodeURIComponent("微信小王")))).toBe(true);
    await page.locator(".admin-order-events summary").first().click();
    await expect(page.locator(".admin-order-events")).toContainText("用户提交付款信息");

    await page.goto("/admin/orders", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("tab", {name: /待核款/})).toHaveAttribute("aria-selected", "true");
    await page.getByRole("button", { name: "确认到账并开通会员" }).click();
    const confirmDialog = page.getByRole("dialog");
    await expect(confirmDialog).toContainText("付款人：微信小王");
    await expect(confirmDialog).toContainText("当前会员已于 2026-10-18 到期，确认后从现在起算");
    await confirmDialog.getByRole("button", { name: "取消" }).click();

    await page.goto("/admin/orders?status=pending", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "核实到账后人工补录" }).click();
    const panel = page.getByRole("region", { name: "人工补录会员" });
    await expect(panel).toContainText("YMPENDING602");
    await panel.getByLabel("付款人（微信昵称）").fill("沉默付款人");
    await panel.getByLabel("付款时间").fill("2026-11-18T08:05");
    await panel.getByLabel("补录原因（必填）").fill("付款时服务器不可用，已核对微信到账");
    await panel.getByRole("button", { name: "核实到账，补录并开通" }).click();
    await page.getByRole("button", { name: "确认补录开通" }).click();
    await expect(page.locator(".admin-alert")).toContainText("人工补录完成");
    expect(capture.grantBody).toMatchObject({
      user_id: 8,
      order_id: 602,
      plan_id: "monthly_membership",
      amount_cents: 5900,
      payment_method: "wechat",
      payer_name: "沉默付款人",
      reason: "付款时服务器不可用，已核对微信到账",
    });
    expect(String(capture.grantBody?.request_id)).toMatch(/^admin-grant-/);
  });
});
