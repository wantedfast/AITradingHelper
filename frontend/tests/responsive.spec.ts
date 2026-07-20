import { expect, test, type Page, type Route } from "@playwright/test";

const viewports = [
  { name: "360x800", width: 360, height: 800 },
  { name: "390x844", width: 390, height: 844 },
  { name: "430x932", width: 430, height: 932 },
  { name: "768x1024", width: 768, height: 1024 },
  { name: "1024x768", width: 1024, height: 768 },
  { name: "1100x800", width: 1100, height: 800 },
  { name: "1280x800", width: 1280, height: 800 },
] as const;

const shellRoutes = [
  { name: "home", path: "/" },
  { name: "auth", path: "/auth" },
  { name: "billing", path: "/billing" },
  { name: "credits", path: "/credits" },
  { name: "daily-top5", path: "/auction-strength" },
  { name: "review", path: "/review" },
  { name: "watch", path: "/watch" },
  { name: "market-day", path: "/market-day" },
  { name: "ai-research", path: "/ai-research" },
  { name: "review-report", path: "/review/report/responsive-smoke" },
  { name: "watch-report", path: "/watch/result?planId=responsive-smoke" },
  { name: "market-day-report", path: "/market-day/report/responsive-smoke" },
  { name: "ai-research-report", path: "/ai-research/report/responsive-smoke" },
  { name: "admin", path: "/admin" },
  { name: "webhook", path: "/webhook" },
] as const;

const featureRoutes = ["/auction-strength", "/review", "/watch", "/market-day", "/ai-research"];

const membershipPlans = [
  { id: "monthly_membership", plan_name: "月度会员", amount_cents: 5900, duration_days: 31, alipay_qr_url: "/pay/alipay-qr.jpg", wechat_qr_url: "/pay/wechat-qr.jpg" },
  { id: "annual_membership", plan_name: "年度会员", amount_cents: 39900, duration_days: 365, alipay_qr_url: "/pay/alipay-qr.jpg", wechat_qr_url: "/pay/wechat-qr.jpg" },
];

const creditCatalog = {
  checkout: {
    business_hours: "工作日 10:00-18:00",
    confirmation_eta: "提交付款信息后由运营人工确认到账",
    support_channel: "站内反馈或运营客服",
    policy_note: "当前为人工核款开通",
  },
  pricing: { unit_price_cents: 100, currency: "CNY" },
  rules: {
    min_credits: 5,
    max_credits: 10000,
    price_text: "1 元 / 次",
    support_text: "购买次数按服务器价格计算，客户端金额仅展示。",
  },
};

const fixtureUser = {
  id: 1,
  phone: "13800000000",
  username: "responsive-test",
  email: "responsive@example.test",
  email_verified: true,
  email_binding_required: false,
  update_emails_enabled: true,
  role: "admin",
  invite_code: "RESPONSIVE",
  credits: 100,
  referral_count: 0,
  created_at: "2026-07-15T00:00:00Z",
};

const wideMarkdownTable = [
  "| 主题 | 国内数据 | 海外数据 | 黄金 | 原油 | 汇率 | 行业 | 龙头 | 风险 | 验证条件 | 失效条件 | 备注 |",
  "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
  `| 测试主线 | CPI温和回落 | 海外利率预期变化 | 观察避险需求 | 观察供给扰动 | 观察人民币中间价 | 科技制造 | 示例股票 | 波动放大 | 成交量确认 | 跌破关键位置 | ${"LONGUNBROKENCONTENT".repeat(8)} |`,
].join("\n");

const marketDayReport = {
  run_id: "responsive-market-day",
  market_date: "2026-07-15",
  report: {
    marketDate: "2026-07-15",
    oneLineConclusion: "移动端行情报告布局验证",
    marketMood: { summary: "市场情绪保持平稳", limitUpCount: "42", limitDownCount: "3", heightBoard: "5", turnover: "1.2万亿", score: 7.2 },
    mainline: { name: "测试主线", reason: wideMarkdownTable, branches: ["分支一", "分支二"], score: 8.1 },
    strongestStocks: [],
    secondaryLines: [{ name: "次主线", reason: "用于验证手机端默认折叠" }],
    fakeOrWeakLines: [{ name: "弱方向", reason: "仅用于响应式测试" }],
    watchPoints: ["观察成交量"],
    audit: { missingEvidence: ["等待盘中确认"], sourceWarnings: ["测试数据"] },
  },
};

const aiResearchReport = {
  run_id: "responsive-ai-research",
  research_date: "2026-07-15",
  title: "移动端 AI 研报布局验证",
  summary: "包含宽表格、长文本和默认折叠内容。",
  source: "responsive-fixture",
  received_at: "2026-07-15T08:30:00+08:00",
  markdown: `# 移动端 AI 研报\n## 深度分析\n${wideMarkdownTable}`,
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function installStableApiFixtures(
  page: Page,
  options: { datedBillingStatus?: "charged" | "pending_view" } = {},
) {
  const datedBillingStatus = options.datedBillingStatus || "charged";
  await page.addInitScript((user) => {
    window.localStorage.setItem("ai_trade_token", "responsive-test-token");
    window.localStorage.setItem("ai_trade_user", JSON.stringify(user));
  }, fixtureUser);

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path === "/api/auth/me") return json(route, { user: fixtureUser });
    if (path === "/api/auth/email-preferences") return json(route, { user: fixtureUser });
    if (path === "/api/update-notices/pending") return json(route, { notices: [] });
    if (path === "/api/public/membership/plans") return json(route, { plans: membershipPlans, checkout: {} });
    if (path === "/api/pay/membership/orders/latest") return json(route, { order: null, plans: membershipPlans, user: fixtureUser });
    if (path === "/api/pay/membership/plans") return json(route, { plans: membershipPlans });
    if (path === "/api/public/credits/catalog") return json(route, creditCatalog);
    if (path === "/api/pay/credits/orders/latest") return json(route, { ...creditCatalog, order: null, user: fixtureUser });
    if (path === "/api/update-notices/latest") return json(route, { notice: null });
    if (path === "/api/webhooks") return json(route, { events: [], count: 0, total: 0 });
    if (path === "/api/auction-strength") {
      const report = {
        id: "responsive-daily-top5",
        request_id: "responsive-daily-top5",
        received_at: "2026-07-15T09:25:00+08:00",
        source_ip: "127.0.0.1",
        trade_date: "2026-07-15",
        analysis_time: "09:25",
        summary: { one_sentence: "responsive fixture", selection_logic: "fixture", data_limit: "fixture" },
        top5_strong_stocks: [],
        top5_avoid_stocks: [],
        global_conclusion: {
          strongest_stock_at_925: "--",
          strongest_theme_cluster: "--",
          most_over_expected_stock: "--",
          best_capacity_confirmation: "--",
          biggest_negative_feedback: "--",
          one_sentence_for_930: "responsive fixture",
        },
      };
      return json(route, {
        latest: report,
        reports: [report],
        count: 1,
        total: 1,
        billing_status: datedBillingStatus,
        billing_cost: datedBillingStatus === "pending_view" ? 2 : 0,
        user: fixtureUser,
      });
    }
    if (path === "/api/market-day/reports") {
      return json(route, {
        selected_date: url.searchParams.get("date"),
        available_dates: ["2026-07-15"],
        reports: [{ run_id: marketDayReport.run_id, market_date: "2026-07-15", mainline: "测试主线", one_line_conclusion: "移动端行情报告布局验证" }],
        billing_status: datedBillingStatus,
        billing_cost: datedBillingStatus === "pending_view" ? 1 : 0,
        user: fixtureUser,
      });
    }
    if (path === `/api/market-day/reports/${marketDayReport.run_id}/status`) {
      return json(route, { status: "done", stage: "done", report: marketDayReport });
    }
    if (path === "/api/ai-research/reports") {
      return json(route, {
        selected_date: url.searchParams.get("date"),
        available_dates: ["2026-07-15"],
        reports: [{ run_id: aiResearchReport.run_id, research_date: "2026-07-15", title: aiResearchReport.title, summary: aiResearchReport.summary }],
        billing_status: datedBillingStatus,
        billing_cost: datedBillingStatus === "pending_view" ? 2 : 0,
        user: fixtureUser,
      });
    }
    if (path === `/api/ai-research/reports/${aiResearchReport.run_id}/status`) {
      return json(route, { status: "done", stage: "done", billing_status: "charged", report: aiResearchReport, user: fixtureUser });
    }
    if (path === "/api/admin/dashboard") {
      return json(route, {
        totals: { users: 0, credits: 0, feedback_pending: 0, orders_paid: 0 },
        usage_by_day: [],
        new_users_by_day: [],
        feedback: [],
        orders: [],
        managed_users: [],
        top_users: [],
        credit_grant_campaigns: [],
        update_notices: [{
          id: 1,
          title: "盈航功能更新：会员服务与 AI 研报正式上线",
          version: "2026-07-15",
          items: ["新增月度会员服务", "新增 AI 研报功能"],
          status: "published",
          created_at: "2026-07-15T08:30:00+08:00",
          updated_at: "2026-07-15T08:51:00+08:00",
          published_at: "2026-07-15T08:51:00+08:00",
          email_campaign: null,
        }],
        analytics: {
          window: { days: 30, start_date: "2026-06-16", end_date: "2026-07-15" },
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
          high_frequency_users: [{
            id: 7, phone: "13800000007", username: "活跃用户", email: "active@example.com",
            total_uses: 9, credits_spent: 12, active_days: 2,
            usage_by_day: [{ day: "2026-07-14", count: 4, credits: 5 }, { day: "2026-07-15", count: 5, credits: 7 }],
          }],
        },
      });
    }
    if (path === "/api/legal/registration-agreement") {
      return json(route, {
        title: "注册协议",
        version: "responsive-test",
        effective_date: "2026-07-15",
        sections: [],
        highlights: [],
        confirmation_text: "我已阅读并同意",
        content_hash: "responsive-test",
      });
    }

    return json(route, { error: "responsive fixture has no data" }, 404);
  });
}

async function expectNoGlobalHorizontalOverflow(page: Page, routeName: string) {
  await expect
    .poll(
      async () =>
        page.evaluate(() => ({
          viewport: window.innerWidth,
          documentWidth: document.documentElement.scrollWidth,
          bodyWidth: document.body.scrollWidth,
        })),
      { message: `${routeName} must not introduce page-level horizontal scrolling` },
    )
    .toEqual(
      expect.objectContaining({
        viewport: await page.evaluate(() => window.innerWidth),
        documentWidth: await page.evaluate(() => window.innerWidth),
        bodyWidth: await page.evaluate(() => window.innerWidth),
      }),
    );
}

async function expectFeatureNavigationInViewport(page: Page, viewportHeight: number, isMobile: boolean) {
  const nav = page.locator(".review-workbench-nav");
  await expect(nav).toBeVisible();
  await expect(nav.locator("a")).toHaveCount(5);

  const box = await nav.boundingBox();
  expect(box, "feature navigation should have a measurable layout box").not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual((await page.evaluate(() => window.innerWidth)) + 1);
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewportHeight + 1);

  if (isMobile) {
    const position = await nav.evaluate((element) => getComputedStyle(element.closest("aside") || element).position);
    expect(position).toBe("fixed");
  }
}

async function expectPrimaryDockAboveNavigation(page: Page) {
  const dock = page.locator(".mobile-action-dock");
  const nav = page.locator(".review-workbench-nav");
  await expect(dock).toBeVisible();
  await expect(nav).toBeVisible();

  const [dockBox, navBox] = await Promise.all([dock.boundingBox(), nav.boundingBox()]);
  expect(dockBox, "primary action dock should have a measurable layout box").not.toBeNull();
  expect(navBox, "feature navigation should have a measurable layout box").not.toBeNull();
  expect(dockBox!.x).toBeGreaterThanOrEqual(0);
  expect(dockBox!.x + dockBox!.width).toBeLessThanOrEqual((await page.evaluate(() => window.innerWidth)) + 1);
  expect(dockBox!.y + dockBox!.height, "primary action must not sit behind the feature navigation").toBeLessThanOrEqual(navBox!.y + 1);

  const button = dock.locator("button");
  await expect(button).toBeVisible();
  const buttonBox = await button.boundingBox();
  expect(buttonBox, "primary action button should have a measurable layout box").not.toBeNull();
  expect(buttonBox!.height, "primary action button must provide a 48px touch target").toBeGreaterThanOrEqual(47);
}

for (const viewport of viewports) {
  test.describe(`responsive ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("all public and protected route shells stay inside the viewport", async ({ page }) => {
      await installStableApiFixtures(page);

      for (const target of shellRoutes) {
        await test.step(target.name, async () => {
          await page.goto(target.path, { waitUntil: "domcontentloaded" });
          await expect(page.locator("body")).toBeVisible();
          await page.waitForTimeout(150);
          await expectNoGlobalHorizontalOverflow(page, target.name);
        });
      }
    });

    test("five core features expose an unobstructed unified navigation", async ({ page }) => {
      await installStableApiFixtures(page);

      for (const path of featureRoutes) {
        await test.step(path, async () => {
          await page.goto(path, { waitUntil: "domcontentloaded" });
          await expectFeatureNavigationInViewport(page, viewport.height, viewport.width <= 767);
        });
      }
    });

    test("visible primary controls meet the mobile touch target contract", async ({ page }) => {
      await installStableApiFixtures(page);
      await page.goto("/auth", { waitUntil: "domcontentloaded" });

      const controls = page.locator("input:visible, select:visible, textarea:visible, button:visible");
      const count = await controls.count();
      expect(count).toBeGreaterThan(0);

      if (viewport.width <= 767) {
        for (let index = 0; index < count; index += 1) {
          const control = controls.nth(index);
          const box = await control.boundingBox();
          if (!box) continue;
          const style = await control.evaluate((element) => getComputedStyle(element));
          const identity = await control.evaluate((element) =>
            `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""}${element.className ? `.${String(element.className).trim().replace(/\s+/g, ".")}` : ""}`,
          );
          if (["INPUT", "SELECT", "TEXTAREA"].includes(await control.evaluate((element) => element.tagName))) {
            expect(Number.parseFloat(style.fontSize)).toBeGreaterThanOrEqual(16);
          }
          expect(box.height, `${identity} must provide a 44px touch target`).toBeGreaterThanOrEqual(43);
        }
      }
    });

    if (viewport.width <= 767) {
      test("paid report actions remain visible above the five-feature navigation", async ({ page }) => {
        await installStableApiFixtures(page, { datedBillingStatus: "pending_view" });

        for (const path of ["/auction-strength", "/market-day", "/ai-research"]) {
          await test.step(path, async () => {
            await page.goto(path, { waitUntil: "domcontentloaded" });
            await expect(page.locator(".mobile-action-dock")).toBeVisible({ timeout: 30_000 });
            await page.locator(".mobile-action-dock").scrollIntoViewIfNeeded();
            await expectPrimaryDockAboveNavigation(page);
            await expectNoGlobalHorizontalOverflow(page, `${path} pending payment action`);
          });
        }
      });

      test("wide report tables scroll locally and detailed sections start collapsed", async ({ page }) => {
        await installStableApiFixtures(page);

        await page.goto("/market-day", { waitUntil: "domcontentloaded" });
        const marketTable = page.locator(".report-pipe-table-scroll").first();
        await expect(marketTable).toBeVisible();
        await expect.poll(() => marketTable.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
        await expectNoGlobalHorizontalOverflow(page, "market-day wide table fixture");
        await expect(page.locator("details.mobile-report-disclosure").first()).not.toHaveAttribute("open", "");

        await page.goto("/ai-research", { waitUntil: "domcontentloaded" });
        const disclosureWithTable = page.locator("details.mobile-report-disclosure").filter({ has: page.locator(".report-pipe-table-scroll") }).first();
        await expect(disclosureWithTable).toBeAttached();
        await expect(disclosureWithTable).not.toHaveAttribute("open", "");
        await disclosureWithTable.locator("summary").click();
        const researchTable = disclosureWithTable.locator(".report-pipe-table-scroll").first();
        await expect(researchTable).toBeVisible();
        await expect.poll(() => researchTable.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
        await expectNoGlobalHorizontalOverflow(page, "ai-research wide table fixture");
      });
    }
  });
}

test.describe("homepage guest acquisition", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("guest start action opens the combined login and registration page", async ({ page }) => {
    await page.route("**/api/update-notices/latest", (route) => json(route, { notice: null }));
    await page.route("**/api/auction-strength/performance", (route) => json(route, { rows: [] }));
    await page.route("**/api/legal/registration-agreement", (route) =>
      json(route, {
        agreement_type: "registration",
        version: "responsive-test",
        effective_at: "2026-07-15",
        title: "注册协议",
        operator_name: "盈航运营方",
        sections: [],
        confirmation: "我已阅读并同意",
        content_hash: "responsive-test",
      }),
    );

    await page.goto("/", { waitUntil: "domcontentloaded" });

    const heroActions = page.locator(".hero .actions");
    const startLink = heroActions.getByRole("link", { name: "现在开始" });
    await expect(startLink).toBeVisible();
    await expect(startLink).toHaveAttribute("href", "/auth");
    await page.locator(".home-mobile-menu-button").click();
    await expect(page.locator(".home-mobile-account-login")).toBeVisible();
    await page.locator(".home-mobile-menu-head button").click();
    await expect(page.locator("audio, .music-toggle")).toHaveCount(0);

    await startLink.click();
    await expect(page).toHaveURL(/\/auth$/);
    await expect(page.locator(".account-mode-switch button")).toHaveCount(2);
    await expect(page.locator(".account-mode-switch button").nth(0)).toHaveClass(/active/);
  });

  test("signed-in start action opens Daily TOP5", async ({ page }) => {
    await page.addInitScript((user) => {
      window.localStorage.setItem("ai_trade_token", "homepage-start-token");
      window.localStorage.setItem("ai_trade_user", JSON.stringify(user));
    }, { ...fixtureUser, role: "user" });
    await page.route("**/api/**", (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/auth/me") return json(route, { user: { ...fixtureUser, role: "user" } });
      if (path === "/api/update-notices/latest") return json(route, { notice: null });
      if (path === "/api/auction-strength/performance") return json(route, { rows: [] });
      return json(route, {});
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    const startLink = page.locator(".hero .actions").getByRole("link", { name: "现在开始" });
    await expect(startLink).toBeVisible();
    await expect(startLink).toHaveAttribute("href", "/auction-strength");
  });

  test("360px topbar keeps membership, registration and menu in the required order", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 });
    await page.route("**/api/update-notices/latest", (route) => json(route, { notice: null }));
    await page.route("**/api/auction-strength/performance", (route) => json(route, { rows: [] }));

    await page.goto("/", { waitUntil: "domcontentloaded" });

    const membership = page.locator(".home-mobile-actions .home-mobile-membership");
    const register = page.locator(".home-mobile-actions .home-mobile-register");
    const menu = page.locator(".home-mobile-actions .home-mobile-menu-button");
    await expect(membership).toBeVisible();
    await expect(register).toBeVisible();
    await expect(menu).toBeVisible();
    const [membershipBox, registerBox, menuBox] = await Promise.all([membership.boundingBox(), register.boundingBox(), menu.boundingBox()]);
    expect(membershipBox!.x + membershipBox!.width).toBeLessThanOrEqual(registerBox!.x);
    expect(registerBox!.x + registerBox!.width).toBeLessThanOrEqual(menuBox!.x);
    await expect(page.locator(".home-mobile-actions .home-mobile-login")).toHaveCount(0);
    await expectNoGlobalHorizontalOverflow(page, "360px guest acquisition topbar");
  });

  test("expired membership status does not override the authoritative active flag", async ({ page }) => {
    const expiredUser = {
      ...fixtureUser,
      role: "user",
      membership_status: "active",
      membership_active: false,
      membership_expires_at: "2026-07-01T00:00:00+08:00",
    };
    const activeUser = {
      ...expiredUser,
      membership_active: true,
      membership_expires_at: "2027-07-15T00:00:00+08:00",
    };
    let currentUser = expiredUser;
    await page.addInitScript((user) => {
      window.localStorage.setItem("ai_trade_token", "membership-state-token");
      window.localStorage.setItem("ai_trade_user", JSON.stringify(user));
    }, expiredUser);
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/auth/me") return json(route, { user: currentUser });
      if (path === "/api/update-notices/latest") return json(route, { notice: null });
      if (path === "/api/auction-strength/performance") return json(route, { rows: [] });
      return json(route, {});
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    const membershipAction = page.locator(".home-mobile-actions .home-mobile-membership");
    await expect(membershipAction).toHaveText(/开通会员/);
    await expect(membershipAction).not.toHaveClass(/is-active/);

    currentUser = activeUser;
    await page.evaluate((user) => window.localStorage.setItem("ai_trade_user", JSON.stringify(user)), activeUser);
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(membershipAction).toHaveText(/会员已开通/);
    await expect(membershipAction).toHaveClass(/is-active/);
  });
});

test.describe("membership plan selection", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("shows monthly then annual, recommends annual and locks the API-selected order", async ({ page }) => {
    let submittedPlanId = "";
    await page.addInitScript((user) => {
      window.localStorage.setItem("ai_trade_token", "membership-test-token");
      window.localStorage.setItem("ai_trade_user", JSON.stringify(user));
    }, fixtureUser);
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/public/membership/plans") return json(route, { plans: membershipPlans, checkout: {} });
      if (path === "/api/pay/membership/orders/latest") return json(route, { order: null, plans: membershipPlans, user: fixtureUser });
      if (path === "/api/update-notices/pending") return json(route, { notices: [] });
      if (path === "/api/auth/me") return json(route, { user: fixtureUser });
      if (path === "/api/pay/membership/orders" && route.request().method() === "POST") {
        submittedPlanId = String(route.request().postDataJSON()?.plan_id || "");
        return json(route, {
          order: {
            id: 88,
            order_no: "YMRESPONSIVE",
            plan_name: "年度会员",
            amount_cents: 39900,
            status: "pending",
            package_id: "annual_membership",
            duration_days: 365,
          },
          user: fixtureUser,
        });
      }
      if (path === "/api/orders/88") return json(route, { order: { id: 88, order_no: "YMRESPONSIVE", plan_name: "年度会员", amount_cents: 39900, status: "pending" }, user: fixtureUser });
      return json(route, {});
    });

    await page.goto("/billing", { waitUntil: "domcontentloaded" });
    const planCards = page.locator('.billing-plan-options button[role="radio"]');
    await expect(planCards).toHaveCount(2);
    await expect(planCards.nth(0)).toContainText("月度会员");
    await expect(planCards.nth(1)).toContainText("年度会员");
    await expect(planCards.nth(1)).toHaveAttribute("aria-checked", "true");
    await expect(planCards.nth(1)).toContainText("比连续购买月度节省 ¥309");

    await page.locator(".billing-checkout .billing-primary").click();
    await expect.poll(() => submittedPlanId).toBe("annual_membership");
    await expect(planCards.nth(0)).toBeDisabled();
    await expect(planCards.nth(1)).toBeDisabled();
    await expect(page.locator('.billing-payment-form input').nth(2)).toHaveValue("399.00");
    await expectNoGlobalHorizontalOverflow(page, "annual membership checkout");
  });

  test("restores the existing order plan after session hydration without a guest response race", async ({ page }) => {
    let publicCatalogRequests = 0;
    await page.addInitScript((user) => {
      window.localStorage.setItem("ai_trade_token", "existing-order-token");
      window.localStorage.setItem("ai_trade_user", JSON.stringify(user));
    }, fixtureUser);
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/public/membership/plans") {
        publicCatalogRequests += 1;
        await new Promise((resolve) => setTimeout(resolve, 150));
        return json(route, { plans: membershipPlans, checkout: {} });
      }
      if (path === "/api/pay/membership/orders/latest") return json(route, {
        plans: membershipPlans,
        checkout: {},
        user: fixtureUser,
        order: {
          id: 91,
          order_no: "MEM-MONTHLY-EXISTING",
          plan_name: "月度会员",
          package_id: "monthly_membership",
          amount_cents: 5900,
          status: "pending",
        },
      });
      if (path === "/api/update-notices/pending") return json(route, { notices: [] });
      if (path === "/api/orders/91") return json(route, {
        order: {
          id: 91,
          order_no: "MEM-MONTHLY-EXISTING",
          plan_name: "月度会员",
          package_id: "monthly_membership",
          amount_cents: 5900,
          status: "pending",
        },
        user: fixtureUser,
      });
      return json(route, {});
    });

    await page.goto("/billing", { waitUntil: "domcontentloaded" });
    const monthlyPlan = page.locator('.billing-plan-options button[role="radio"]').first();
    await expect(monthlyPlan).toHaveAttribute("aria-checked", "true");
    await expect(page.getByText("MEM-MONTHLY-EXISTING", { exact: true })).toBeVisible();
    expect(publicCatalogRequests).toBe(1);
  });
});

test.describe("public pricing and mandatory notices", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("guest can inspect plans and keeps the selected plan in the auth redirect", async ({ page }) => {
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/public/membership/plans") return json(route, {
        plans: membershipPlans,
        checkout: {
          business_hours: "工作日 10:00-18:00",
          confirmation_eta: "客服工作时间内人工核对",
          support_channel: "请联系站内反馈",
          policy_note: "退款与发票按人工客服规则处理",
        },
      });
      return json(route, {});
    });
    await page.goto("/billing?plan_id=monthly_membership", { waitUntil: "domcontentloaded" });
    await expect(page.getByText("正在读取会员套餐...")).toHaveCount(0);
    const planCards = page.locator('.billing-plan-options button[role="radio"]');
    await expect(planCards).toHaveCount(2);
    await expect(planCards.nth(0)).toHaveAttribute("aria-checked", "true");
    await expect(page.getByText("人工核对", { exact: false })).toBeVisible();
    await page.locator(".billing-checkout .billing-primary").click();
    await expect(page).toHaveURL(/\/auth\?.*plan_id=monthly_membership/);
    await expect(page).toHaveURL(/source=pricing/);
    const directQrResponse = await page.request.get("/pay/alipay-qr.jpg");
    expect(directQrResponse.status()).not.toBe(200);
  });

  test("guest never requests pending notices", async ({ page }) => {
    let pendingRequests = 0;
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/update-notices/pending") pendingRequests += 1;
      if (path === "/api/auth/me") return json(route, { user: null });
      return json(route, {});
    });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(300);
    expect(pendingRequests).toBe(0);
    await expect(page.locator(".site-update-notice-modal")).toHaveCount(0);
  });

  test("expired browser session returns to guest pricing without a notice error", async ({ page }) => {
    let pendingRequests = 0;
    await page.addInitScript((user) => {
      window.localStorage.setItem("ai_trade_token", "expired-token");
      window.localStorage.setItem("ai_trade_user", JSON.stringify(user));
    }, fixtureUser);
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/public/membership/plans") return json(route, { plans: membershipPlans, checkout: {} });
      if (path === "/api/update-notices/pending") {
        pendingRequests += 1;
        return json(route, { error: "请先登录后再使用" }, 401);
      }
      if (path === "/api/pay/membership/orders/latest") return json(route, { error: "请先登录后再使用" }, 401);
      return json(route, {});
    });
    await page.goto("/billing", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(300);
    expect(pendingRequests).toBe(0);
    await expect(page.locator(".site-update-notice-modal")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "登录后创建订单" })).toBeEnabled();
  });

  test("action-time 401 clears an expired session and restores guest checkout", async ({ page }) => {
    await page.addInitScript((user) => {
      window.localStorage.setItem("ai_trade_token", "expires-after-load-token");
      window.localStorage.setItem("ai_trade_user", JSON.stringify(user));
    }, fixtureUser);
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/public/membership/plans") return json(route, { plans: membershipPlans, checkout: {} });
      if (path === "/api/pay/membership/orders/latest") return json(route, {
        order: null,
        plans: membershipPlans,
        checkout: {},
        user: fixtureUser,
      });
      if (path === "/api/update-notices/pending") return json(route, { notices: [] });
      if (path === "/api/pay/membership/orders" && route.request().method() === "POST") {
        return json(route, { error: "请先登录后再使用" }, 401);
      }
      return json(route, {});
    });

    await page.goto("/billing", { waitUntil: "domcontentloaded" });
    const checkout = page.locator(".billing-checkout .billing-primary");
    await checkout.click();
    await expect.poll(() => page.evaluate(() => window.localStorage.getItem("ai_trade_token"))).toBeNull();
    await expect(page.getByRole("button", { name: "登录后创建订单" })).toBeEnabled();
    await expect(page.locator(".billing-order")).toHaveCount(0);
  });

  test("logged-in user only requests pending notices on homepage", async ({ page }) => {
    let pendingRequests = 0;
    await page.addInitScript((user) => {
      window.localStorage.setItem("ai_trade_token", "notice-home-token");
      window.localStorage.setItem("ai_trade_user", JSON.stringify(user));
    }, { ...fixtureUser, role: "user" });
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/update-notices/pending") {
        pendingRequests += 1;
        return json(route, {
          notices: [{ id: 2, title: "Newest notice", version: "v2", items: ["Newest item"], published_at: "2026-07-19T10:00:00+08:00" }],
        });
      }
      if (path === "/api/auth/me") return json(route, { user: { ...fixtureUser, role: "user" } });
      if (path === "/api/public/membership/plans") return json(route, { plans: membershipPlans, checkout: {} });
      if (path === "/api/pay/membership/orders/latest") return json(route, { order: null, plans: membershipPlans });
      if (path === "/api/admin/dashboard") {
        return json(route, {
          totals: { users: 0, credits: 0, feedback_pending: 0, orders_paid: 0 },
          usage_by_day: [],
          new_users_by_day: [],
          feedback: [],
          orders: [],
          top_users: [],
          credit_grant_campaigns: [],
          update_notices: [],
          analytics: {
            window: { days: 30, start_date: "2026-06-16", end_date: "2026-07-15" },
            feature_usage: { totals: [], by_day: [] },
            user_growth: { starting_users: 0, total_users: 0, by_day: [] },
            high_frequency_users: [],
            recent_usage_events: [],
          },
        });
      }
      return json(route, {});
    });
    await page.goto("/billing", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(300);
    expect(pendingRequests).toBe(0);
    await expect(page.locator(".site-update-notice-modal")).toHaveCount(0);

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect.poll(() => pendingRequests).toBe(1);
    await expect(page.locator(".site-update-notice-modal")).toContainText("Newest notice");
    await page.waitForTimeout(500);
    expect(pendingRequests).toBe(1);

    await page.goto("/admin", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(300);
    expect(pendingRequests).toBe(1);
    await expect(page.locator(".site-update-notice-modal")).toHaveCount(0);
  });

  test("admin never requests pending notices on homepage", async ({ page }) => {
    let pendingRequests = 0;
    await page.addInitScript((user) => {
      window.localStorage.setItem("ai_trade_token", "admin-notice-token");
      window.localStorage.setItem("ai_trade_user", JSON.stringify(user));
    }, fixtureUser);
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/update-notices/pending") pendingRequests += 1;
      if (path === "/api/auth/me") return json(route, { user: fixtureUser });
      if (path === "/api/update-notices/latest") return json(route, { notice: null });
      if (path === "/api/auction-strength/performance") return json(route, { rows: [] });
      if (path === "/api/legal/registration-agreement") {
        return json(route, {
          agreement_type: "registration",
          version: "responsive-test",
          effective_at: "2026-07-15",
          title: "Agreement",
          operator_name: "Responsive test",
          sections: [],
          confirmation: "I agree",
        });
      }
      return json(route, {});
    });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(300);
    expect(pendingRequests).toBe(0);
    await expect(page.locator(".site-update-notice-modal")).toHaveCount(0);
  });

  test("logged-in user sees only the newest notice and acknowledgement clears without old backlog", async ({ page }) => {
    let pendingRequests = 0;
    const newestNotice = { id: 2, title: "Newest notice", version: "v2", items: ["Newest item"], published_at: "2026-07-19T10:00:00+08:00" };
    await page.addInitScript((user) => {
      window.localStorage.setItem("ai_trade_token", "notice-single-token");
      window.localStorage.setItem("ai_trade_user", JSON.stringify(user));
    }, { ...fixtureUser, role: "user" });
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/update-notices/pending") {
        pendingRequests += 1;
        return json(route, { notices: [newestNotice] });
      }
      if (path === "/api/auth/me") return json(route, { user: { ...fixtureUser, role: "user" } });
      if (path === "/api/update-notices/2/ack") return json(route, { remaining: [] });
      if (path === "/api/public/membership/plans") return json(route, { plans: membershipPlans, checkout: {} });
      if (path === "/api/pay/membership/orders/latest") return json(route, { order: null, plans: membershipPlans });
      return json(route, {});
    });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect.poll(() => pendingRequests).toBe(1);
    const dialog = page.locator(".site-update-notice-modal");
    await expect(dialog).toContainText("Newest notice");
    const backdrop = page.locator(".site-update-notice-backdrop");
    await expect(backdrop).toHaveCSS("position", "fixed");
    await expect(backdrop).toHaveCSS("display", "grid");
    const dialogBox = await dialog.boundingBox();
    const viewport = page.viewportSize();
    expect(dialogBox).not.toBeNull();
    expect(viewport).not.toBeNull();
    expect(dialogBox!.width).toBeLessThanOrEqual(681);
    expect(dialogBox!.x).toBeGreaterThan(0);
    expect(Math.abs(dialogBox!.x + dialogBox!.width / 2 - viewport!.width / 2)).toBeLessThanOrEqual(2);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button").click();
    await expect(dialog).toHaveCount(0);
    expect(pendingRequests).toBe(1);
  });

  test("notice check stays invisible while loading and does not block homepage on failure", async ({ page }) => {
    let pendingRequests = 0;
    let releasePending: (() => void) | undefined;
    const pendingResponse = new Promise<void>((resolve) => {
      releasePending = resolve;
    });
    await page.addInitScript((user) => {
      window.localStorage.setItem("ai_trade_token", "notice-token");
      window.localStorage.setItem("ai_trade_user", JSON.stringify(user));
    }, { ...fixtureUser, role: "user" });
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/update-notices/pending") {
        pendingRequests += 1;
        await pendingResponse;
        return json(route, { error: "temporary failure" }, 503);
      }
      if (path === "/api/auth/me") return json(route, { user: { ...fixtureUser, role: "user" } });
      return json(route, {});
    });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect.poll(() => pendingRequests).toBe(1);
    await expect(page.locator(".site-update-notice-modal")).toHaveCount(0);
    await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
    releasePending?.();
    await page.waitForTimeout(100);
    await expect(page.locator(".site-update-notice-modal")).toHaveCount(0);
    expect(pendingRequests).toBe(1);
  });

  test("invalid requested plan blocks checkout until a valid plan is selected", async ({ page }) => {
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/public/membership/plans") return json(route, { plans: membershipPlans, checkout: {} });
      return json(route, {});
    });
    await page.goto("/billing?plan_id=retired_membership", { waitUntil: "domcontentloaded" });
    await expect(page.getByText("所选套餐已失效，请重新选择有效套餐。")).toBeVisible();
    const checkout = page.locator(".billing-checkout .billing-primary");
    await expect(checkout).toBeDisabled();
    await page.locator('.billing-plan-options button[role="radio"]').first().click();
    await expect(checkout).toBeEnabled();
  });

  test("rejected membership order shows the admin reason and recovery guidance", async ({ page }) => {
    await page.addInitScript((user) => {
      window.localStorage.setItem("ai_trade_token", "membership-token");
      window.localStorage.setItem("ai_trade_user", JSON.stringify(user));
    }, { ...fixtureUser, role: "user" });
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/update-notices/pending") return json(route, { notices: [] });
      if (path === "/api/public/membership/plans") return json(route, { plans: membershipPlans, checkout: {} });
      if (path === "/api/pay/membership/orders/latest") return json(route, {
        plans: membershipPlans,
        checkout: {},
        user: fixtureUser,
        order: {
          id: 88,
          order_no: "MEM-REJECTED",
          plan_name: "月度会员",
          package_id: "monthly_membership",
          amount_cents: 5900,
          status: "rejected",
          admin_note: "付款金额未到账，请核对交易记录",
        },
      });
      if (path === "/api/orders/88") return json(route, { order: null });
      return json(route, {});
    });
    await page.goto("/billing", { waitUntil: "domcontentloaded" });
    await expect(page.getByText("付款核对未通过：付款金额未到账，请核对交易记录")).toBeVisible();
    await expect(page.getByText("请根据原因核对付款信息", { exact: false })).toBeVisible();
  });
  test("guest credits purchase redirects to auth while preserving the requested quantity", async ({ page }) => {
    await page.route("**/api/public/credits/catalog", (route) => json(route, creditCatalog));
    await page.goto("/credits?credits=12", { waitUntil: "domcontentloaded" });
    await expect(page.locator('input[type="number"]')).toHaveValue("12");
    await page.getByRole("button", { name: "登录后创建订单" }).click();
    await expect(page).toHaveURL(/\/auth\?/);
    const authUrl = new URL(page.url());
    expect(authUrl.searchParams.get("credits")).toBe("12");
    expect(decodeURIComponent(authUrl.searchParams.get("redirect") || "")).toContain("/credits?credits=12");
  });
});

test.describe("dated report access controls", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("guest cannot open historical Daily TOP5 data", async ({ page }) => {
    let reportRequests = 0;
    await page.route("**/api/auction-strength?**", (route) => {
      reportRequests += 1;
      return json(route, { reports: [], latest: null, billing_status: "no_data" });
    });
    await page.goto("/auction-strength?date=2026-07-01", { waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(/\/auth\?redirect=%2Fauction-strength|\/auth\?redirect=\/auction-strength/);
    expect(reportRequests).toBe(0);
  });

  test("Daily TOP5 keeps a disabled waiting action until today's data arrives", async ({ page }) => {
    await installStableApiFixtures(page);
    await page.route("**/api/auction-strength?**", (route) => json(route, {
      latest: null,
      reports: [],
      count: 0,
      total: 0,
      billing_status: "no_data",
      billing_cost: 0,
      user: fixtureUser,
    }));
    await page.goto("/auction-strength", { waitUntil: "domcontentloaded" });
    const waitingButton = page.locator(".auction-waiting-panel").getByRole("button", { name: "等待今日数据" });
    await expect(waitingButton).toBeVisible();
    await expect(waitingButton).toBeDisabled();
    await expect(page.locator(".auction-waiting-panel .auction-confirm-actions span")).toHaveText("页面每 10 秒自动检查一次；无数据时不会扣除使用次数。");
    await expectNoGlobalHorizontalOverflow(page, "Daily TOP5 waiting action");
  });

  test("Daily TOP5 email links open the requested date without charging", async ({ page }) => {
    await installStableApiFixtures(page);
    const requestedDates: string[] = [];
    let acknowledgementCount = 0;
    await page.route("**/api/auction-strength/ack", (route) => {
      acknowledgementCount += 1;
      return json(route, { ok: true });
    });
    await page.route("**/api/auction-strength?**", (route) => {
      requestedDates.push(new URL(route.request().url()).searchParams.get("date") || "");
      return json(route, {
        latest: null,
        reports: [],
        count: 0,
        total: 0,
        billing_status: "no_data",
        billing_cost: 0,
        user: fixtureUser,
      });
    });
    await page.goto("/auction-strength?date=2026-07-14", { waitUntil: "domcontentloaded" });
    await expect(page.locator('.auction-date-picker input[type="date"]')).toHaveValue("2026-07-14");
    await expect.poll(() => requestedDates).toContain("2026-07-14");
    expect(acknowledgementCount).toBe(0);
  });

  test("AI report date fields use the native calendar without suggestion dropdowns", async ({ page }) => {
    await installStableApiFixtures(page);
    for (const path of ["/market-day", "/ai-research"]) {
      await test.step(path, async () => {
        await page.goto(path, { waitUntil: "domcontentloaded" });
        const input = page.locator('.auction-date-picker input[type="date"]');
        await expect(input).toBeVisible();
        await expect(input).not.toHaveAttribute("list", /.+/);
        await expect(page.locator("datalist")).toHaveCount(0);
      });
    }
  });

  test("an already unlocked AI research report opens directly without another charge button", async ({ page }) => {
    await installStableApiFixtures(page, { datedBillingStatus: "charged" });
    await page.goto("/ai-research", { waitUntil: "domcontentloaded" });
    await expect(page.locator("#ai-research-inline-report")).toBeVisible();
    await expect(page.getByRole("button", { name: /确认查看并扣除/ })).toHaveCount(0);
  });
});

test.describe("independent admin access", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("ordinary auth has no admin mode or administrator fields", async ({ page }) => {
    let loginPath = "";
    await page.route("**/api/legal/registration-agreement", (route) => json(route, { agreement_type: "registration", version: "test", effective_at: "2026-07-15", title: "注册协议", operator_name: "盈航", sections: [], confirmation: "同意", content_hash: "test" }));
    await page.route("**/api/auth/password-login", (route) => {
      loginPath = new URL(route.request().url()).pathname;
      return json(route, { token: "user-token", user: { ...fixtureUser, role: "user" } });
    });
    for (const unsafeRedirect of ["javascript:alert(1)", "/\\evil.example", "/admin?section=users"]) {
      loginPath = "";
      await page.goto(`/auth?redirect=${encodeURIComponent(unsafeRedirect)}`, { waitUntil: "domcontentloaded" });
      await page.waitForLoadState("networkidle");
      await expect(page.getByText("管理员入口")).toHaveCount(0);
      await expect(page.locator('input[placeholder="请输入管理员账号"]')).toHaveCount(0);
      await expect(page.locator(".account-mode-switch button")).toHaveCount(2);
      await page.locator(".account-form input").nth(0).fill("ordinary-user");
      await page.locator(".account-form input").nth(1).fill("safe-password");
      await page.locator('.account-form button[type="submit"]').click({ noWaitAfter: true });
      await expect.poll(() => loginPath).toBe("/api/auth/password-login");
      await expect(page).toHaveURL(/\/$/);
    }
  });

  test("admin section query persists and mobile switcher changes the URL", async ({ page }) => {
    await installStableApiFixtures(page);
    await page.goto("/admin?section=orders", { waitUntil: "domcontentloaded" });
    const switcher = page.locator(".admin-mobile-section-switcher");
    await expect(switcher).toBeVisible();
    await expect(switcher.getByRole("button", { name: "会员订单" })).toHaveAttribute("aria-current", "page");
    await switcher.getByRole("button", { name: "反馈建议" }).click();
    await expect(page).toHaveURL(/\/admin\?section=feedback&days=30$/);
    await expect(switcher.getByRole("button", { name: "反馈建议" })).toHaveAttribute("aria-current", "page");
    await expectNoGlobalHorizontalOverflow(page, "admin section switcher");
  });

  test("admin analytics visualizations and time window remain usable on mobile", async ({ page }) => {
    await installStableApiFixtures(page);
    await page.goto("/admin?section=overview&days=30", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "近 30 天功能使用趋势" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "功能使用构成" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "用户增长" })).toBeVisible();
    await expect(page.locator(".admin-echart canvas").first()).toBeVisible();
    await page.getByRole("button", { name: "7 天" }).click();
    await expect(page).toHaveURL(/\/admin\?section=overview&days=7$/);
    await page.locator(".admin-mobile-section-switcher").getByRole("button", { name: "用户与次数" }).click();
    await expect(page.getByRole("heading", { name: "高频用户趋势" })).toBeVisible();
    await expect(page.getByText("总使用次数")).toBeVisible();
    await expect(page.getByText("活跃天数")).toBeVisible();
    await expectNoGlobalHorizontalOverflow(page, "admin analytics");
  });

  test("admin analytics treats zero-filled feature series as empty", async ({ page }) => {
    await installStableApiFixtures(page);
    await page.route("**/api/admin/dashboard**", (route) => json(route, {
      totals: { users: 0, credits: 0, feedback_pending: 0, orders_paid: 0 },
      usage_by_day: [], new_users_by_day: [], feedback: [], orders: [], top_users: [], credit_grant_campaigns: [], update_notices: [],
      analytics: {
        window: { days: 30, start_date: "2026-06-16", end_date: "2026-07-15" },
        feature_usage: {
          totals: [{ feature: "auction_strength_view", count: 0, credits: 0, share: 0 }],
          by_day: [{ day: "2026-07-15", feature: "auction_strength_view", count: 0, credits: 0 }],
        },
        user_growth: { starting_users: 0, total_users: 0, by_day: [{ day: "2026-07-15", new_users: 0, cumulative_users: 0 }] },
        high_frequency_users: [],
      },
    }));
    await page.goto("/admin?section=overview&days=30", { waitUntil: "domcontentloaded" });
    await expect(page.getByText("这段时间还没有功能使用记录。")).toBeVisible();
    await expect(page.getByText("暂无可统计的功能使用。")).toBeVisible();
    await expect(page.getByText("这段时间还没有用户增长数据。")).toBeVisible();
  });

  test("admin can see credit-order actions and pause a manageable user", async ({ page }) => {
    let managedUserStatus: "active" | "disabled" = "active";
    let requestedStatus = "";
    let confirmedCreditOrderId = "";
    await installStableApiFixtures(page);
    await page.route("**/api/admin/dashboard**", (route) => json(route, {
      totals: { users: 2, credits: 20, feedback_pending: 0, orders_paid: 0 },
      usage_by_day: [],
      new_users_by_day: [],
      feedback: [],
      orders: [{
        id: 18,
        phone: "13800000008",
        username: "credit-user",
        order_no: "CREDIT-001",
        plan_name: "购买次数",
        credits: 12,
        amount_cents: 1200,
        status: "submitted",
        product_type: "credits",
        payment_method: "alipay",
        payer_name: "tester",
        payer_paid_at: "2026-07-20T10:00",
        submitted_amount_cents: 1200,
        created_at: "2026-07-20T10:00:00+08:00",
      }],
      managed_users: [{
        id: 8,
        phone: "13800000008",
        username: "credit-user",
        role: "user",
        status: managedUserStatus,
        used_count: 3,
        credits: 9,
        created_at: "2026-07-18T10:00:00+08:00",
        last_login_at: "2026-07-20T09:30:00+08:00",
      }],
      top_users: [],
      credit_grant_campaigns: [],
      update_notices: [],
      analytics: {
        window: { days: 30, start_date: "2026-06-20", end_date: "2026-07-20" },
        feature_usage: { totals: [], by_day: [] },
        user_growth: { starting_users: 2, total_users: 2, by_day: [] },
        high_frequency_users: [],
        recent_usage_events: [],
      },
    }));
    await page.route("**/api/admin/users/8/status", async (route) => {
      const payload = JSON.parse(route.request().postData() || "{}");
      requestedStatus = String(payload.status || "");
      managedUserStatus = payload.status === "disabled" ? "disabled" : "active";
      return json(route, { ok: true });
    });
    await page.route("**/api/admin/orders/18/confirm-credits", async (route) => {
      confirmedCreditOrderId = new URL(route.request().url()).pathname.split("/")[4] || "";
      return json(route, { ok: true });
    });

    await page.goto("/admin?section=users&days=30", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("button", { name: "暂停账号" })).toBeVisible();
    await page.getByRole("button", { name: "暂停账号" }).click();
    await expect.poll(() => requestedStatus).toBe("disabled");
    await expect(page.getByText("账号已暂停，现有 session 已失效。")).toBeVisible();

    await page.locator(".admin-mobile-section-switcher").getByRole("button", { name: "订单处理" }).click();
    const confirmCredits = page.getByRole("button", { name: "确认到账并增加次数" });
    await expect(confirmCredits).toBeVisible();
    await confirmCredits.click();
    await expect.poll(() => confirmedCreditOrderId).toBe("18");
  });

  test("admin user search filters by partial username, falls back to email, and shows an empty state", async ({ page }) => {
    await installStableApiFixtures(page);
    await page.route("**/api/admin/dashboard**", (route) => json(route, {
      totals: { users: 3, credits: 20, feedback_pending: 0, orders_paid: 0 },
      usage_by_day: [],
      new_users_by_day: [],
      feedback: [],
      orders: [],
      managed_users: [
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
          username: "BetaSwing",
          email: "beta@example.com",
          role: "user",
          status: "active",
          used_count: 5,
          credits: 4,
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
      ],
      top_users: [],
      credit_grant_campaigns: [],
      update_notices: [],
      analytics: {
        window: { days: 30, start_date: "2026-06-20", end_date: "2026-07-20" },
        feature_usage: { totals: [], by_day: [] },
        user_growth: { starting_users: 3, total_users: 3, by_day: [] },
        high_frequency_users: [],
        recent_usage_events: [],
      },
    }));

    await page.goto("/admin?section=users&days=30", { waitUntil: "domcontentloaded" });

    const search = page.locator(".admin-user-search input");
    const cards = page.locator(".admin-user-card");

    await expect(cards).toHaveCount(3);

    await search.fill("trade");
    await expect(cards).toHaveCount(1);
    await expect(page.getByText("AlphaTrader")).toBeVisible();
    await expect(page.getByText("BetaSwing")).toHaveCount(0);

    await search.fill("OPS-TEAM");
    await expect(cards).toHaveCount(1);
    await expect(page.getByText("GammaDesk")).toBeVisible();

    await search.fill("missing-user");
    await expect(cards).toHaveCount(0);
    await expect(page.locator(".admin-section--users.is-active .admin-filter-empty")).toBeVisible();
    await expect(page.locator(".admin-user-search-meta")).toContainText("0 / 3");
  });

  test("admin shows Daily TOP5 mail delivery counts and retries failures", async ({ page }) => {
    await installStableApiFixtures(page);
    let retriedCampaignId = "";
    await page.route("**/api/admin/daily-top5-email-campaigns/*/retry", (route) => {
      retriedCampaignId = new URL(route.request().url()).pathname.split("/").at(-2) || "";
      return json(route, { email_campaign: { id: 17, status: "pending" } });
    });
    await page.route("**/api/admin/dashboard**", (route) => json(route, {
      totals: { users: 2, credits: 20, feedback_pending: 0, orders_paid: 0 },
      usage_by_day: [], new_users_by_day: [], feedback: [], orders: [], top_users: [], credit_grant_campaigns: [], update_notices: [],
      daily_top5_email_failed_count: 1,
      daily_top5_email_campaigns: [{
        id: 17, trade_date: "2026-07-16", report_id: "report-17", status: "partial_failed",
        total: 6, pending: 0, sending: 0, sent: 4, failed: 1, skipped: 1, full: 2, teaser: 4,
        created_at: "2026-07-16T09:26:00+08:00", started_at: null, finished_at: null,
      }],
    }));
    await page.goto("/admin?section=updates&days=30", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "每日 TOP5 邮件推送" })).toBeVisible();
    await expect(page.getByText("会员完整版 2 · 普通用户摘要版 4")).toBeVisible();
    await expect(page.getByText("成功 4 · 待发送 0 · 失败 1 · 跳过 1")).toBeVisible();
    await page.getByRole("button", { name: "重试失败邮件" }).click();
    await expect.poll(() => retriedCampaignId).toBe("17");
    await expectNoGlobalHorizontalOverflow(page, "Daily TOP5 email campaigns");
  });

  test("update notice actions use a spaced equal-width mobile layout", async ({ page }) => {
    await installStableApiFixtures(page);
    await page.goto("/admin?section=updates&days=30", { waitUntil: "domcontentloaded" });
    const actions = page.locator(".admin-notice-item-actions").first();
    await expect(actions).toBeVisible();
    await expect(actions.getByRole("button", { name: "编辑" })).toBeVisible();
    await expect(actions.getByRole("button", { name: "下线" })).toBeVisible();
    const layout = await actions.evaluate((element) => {
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
    await expectNoGlobalHorizontalOverflow(page, "update notice actions");
  });

  test("admin login uses the dedicated endpoint and rejects external redirects", async ({ page }) => {
    test.setTimeout(30_000);
    let loginPath = "";
    await page.route("**/api/auth/admin-login", async (route) => {
      loginPath = new URL(route.request().url()).pathname;
      return json(route, { token: "admin-token", user: fixtureUser });
    });
    await page.route("**/api/auth/me", (route) => json(route, { user: fixtureUser }));
    await page.route("**/api/admin/dashboard**", (route) => json(route, {
      totals: { users: 0, credits: 0, feedback_pending: 0, orders_paid: 0 },
      usage_by_day: [], new_users_by_day: [], feedback: [], orders: [], top_users: [], credit_grant_campaigns: [], update_notices: [],
    }));
    for (const unsafeRedirect of ["https://example.com", "/\\evil.example"]) {
      loginPath = "";
      await page.goto(`/admin/login?redirect=${encodeURIComponent(unsafeRedirect)}`, { waitUntil: "domcontentloaded" });
      await page.waitForLoadState("networkidle");
      await page.locator('input[autocomplete="username"]').fill("admin");
      await page.locator('input[autocomplete="current-password"]').fill("secret");
      await page.locator('button[type="submit"]').click({ noWaitAfter: true });
      await expect.poll(() => loginPath).toBe("/api/auth/admin-login");
      await expect(page).toHaveURL(/\/admin\?section=overview&days=30$/);
    }
  });
});
