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
    if (path === "/api/pay/membership/plans") return json(route, { plans: [] });
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
        top_users: [],
        credit_grant_campaigns: [],
        update_notices: [],
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
