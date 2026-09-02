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
  { name: "stock-research", path: "/stock-research" },
  { name: "review-report", path: "/review/report/responsive-smoke" },
  { name: "watch-report", path: "/watch/result?planId=responsive-smoke" },
  { name: "market-day-report", path: "/market-day/report/responsive-smoke" },
  { name: "ai-research-report", path: "/ai-research/report/responsive-smoke" },
  { name: "admin", path: "/admin" },
  { name: "webhook", path: "/webhook" },
] as const;

const featureRoutes = ["/auction-strength", "/review", "/watch", "/market-day", "/ai-research", "/stock-research"];

const membershipPlans = [
  { id: "monthly_membership", plan_name: "月度会员", amount_cents: 5900, duration_days: 31, wechat_qr_url: "/pay/wechat-qr.jpg" },
  { id: "annual_membership", plan_name: "年度会员", amount_cents: 39900, duration_days: 365, wechat_qr_url: "/pay/wechat-qr.jpg" },
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

const creditPaymentAssets = {
  wechat_qr_url: "/pay/wechat-qr.jpg",
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

const marketDayV2Report = {
  run_id: "responsive-market-day",
  market_date: "2026-07-15",
  report: {
    schema_version: 2,
    marketDate: "2026-07-15",
    oneLineConclusion: "今天是修复，不等于明天已经有一条可以直接跟随的强主线。",
    marketMood: {
      summary: "涨停增多、跌停较少，但缩量和分散并存。",
      limitUpCount: "42",
      limitDownCount: "3",
      heightBoard: "5",
      turnover: "1.2万亿",
      score: 6.2,
      scoreReason: "公开数据支持修复，但不足以把明天定义成单一主线延续。",
    },
    mainline: {
      name: "没有明确单一主线",
      reason: wideMarkdownTable,
      branches: ["设备", "电网", "地产链"],
      confidence: 5,
      isClearMainline: false,
      riskOrDivergence: "如果明天继续缩量且热点切换过快，这种修复容易失去持续性。",
      scoreReason: "主线判断更多建立在排除法，而不是单线确认。",
    },
    previousDayComparison: {
      continuity: "待确认",
      previousCoreFeedback: "今天比昨天更强的是封板质量和指数表现，但缩量没有解决。",
    },
    strongestStocks: [
      {
        rank: 1,
        name: "示例样本A",
        code: "000001",
        leaderType: "高度样本",
        theme: "设备",
        strengthReason: "连板高度最突出，但不足以单独代表主线。",
        evidence: [{ content: "收盘时仍维持连板结构。" }],
        riskOrDivergence: "板块广度与成交没有同步确认。",
        score: 8,
      },
    ],
    watchPoints: ["看明天 09:35 是否只剩一个方向还能维持强势。"],
    audit: { missingEvidence: ["统一全市场广度仍待补充"], sourceWarnings: ["测试数据用于响应式验证"] },
    beginner_decision: {
      stance: "cautious",
      headline: "今天是修复，不等于明天已经有一条可以直接跟的强主线。",
      what_changed: ["相比昨天，涨停更多了。", "相比昨天，跌停更少了。", "相比昨天，成交额没有同步放大。"],
      primary_focus: { name: "设备链修复", reason: "它是今天相对集中、但还没完全确认的观察方向。" },
      continue_conditions: [
        { time: "09:35", observation: "设备链里不止一只样本还能维持强势。", action: "只继续观察这一个方向。" },
      ],
      stop_conditions: [
        { time: "09:35", observation: "开盘热度很快分散到多个不相关方向。", action: "停止关注，不临时换题材。" },
        { time: "10:30", observation: "样本冲高后回落，而且没有重新稳住。", action: "明天暂不行动。" },
      ],
      timeline: [
        { time: "09:25", observation: "看修复方向是不是普遍高开。", action: "先记录，不急着扩大判断。", if_unmet: "继续等待 09:35 再确认。" },
        { time: "09:35", observation: "看是否只剩一个方向还能保持强势。", action: "只有满足时才继续观察。", if_unmet: "立即停止。" },
        { time: "10:30", observation: "看回落后有没有重新稳住。", action: "重新稳住再维持原判断。", if_unmet: "明天暂不行动。" },
      ],
      backup_focus: null,
      avoid_actions: ["不要把今天最热的单只样本当成明天主线。"],
      term_explanations: [{ term: "承接", plain: "下跌后还能重新稳住并继续有人愿意参与。" }],
    },
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

const aiResearchV2Report = {
  ...aiResearchReport,
  schema_version: 2,
  run_id: "responsive-ai-research-v2",
  beginner_decision: {
    stance: "cautious",
    headline: "今天先观察 AI 硬件，但不要因为开盘热闹就急着行动。",
    primary_focus: { name: "AI 硬件", reason: "多个相关方向需要一起保持强势。" },
    continue_conditions: [
      { time: "09:35", observation: "至少两个相关方向仍在上涨。", action: "只保留观察。" },
    ],
    stop_conditions: [
      { time: "10:30", observation: "相关方向冲高后持续下跌。", action: "停止关注。" },
    ],
    timeline: [
      { time: "09:25", observation: "看是否普遍大幅高开。", action: "先记录。", if_unmet: "继续等待。" },
      { time: "09:35", observation: "看多个方向是否保持强势。", action: "满足才继续观察。", if_unmet: "停止关注。" },
      { time: "10:30", observation: "看下跌后是否重新上涨。", action: "维持原判断。", if_unmet: "今天不操作。" },
    ],
    backup_focus: null,
    avoid_actions: ["开盘直接追着热度行动。"],
    term_explanations: [{ term: "宽度", plain: "上涨覆盖的股票数量。" }],
  },
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
  options: { datedBillingStatus?: "charged" | "pending_view"; beginnerV2?: boolean; marketDayBeginnerV2?: boolean } = {},
) {
  const datedBillingStatus = options.datedBillingStatus || "charged";
  const researchReport = options.beginnerV2 ? aiResearchV2Report : aiResearchReport;
  const currentMarketDayReport = options.marketDayBeginnerV2 ? marketDayV2Report : marketDayReport;
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
        reports: [{ run_id: currentMarketDayReport.run_id, market_date: "2026-07-15", mainline: "测试主线", one_line_conclusion: "移动端行情报告布局验证" }],
        billing_status: datedBillingStatus,
        billing_cost: datedBillingStatus === "pending_view" ? 1 : 0,
        user: fixtureUser,
      });
    }
    if (path === `/api/market-day/reports/${currentMarketDayReport.run_id}/status`) {
      return json(route, { status: "done", stage: "done", report: currentMarketDayReport });
    }
    if (path === `/api/market-day/reports/${currentMarketDayReport.run_id}/ack`) {
      return json(route, { billing_status: "charged", user: fixtureUser });
    }
    if (path === "/api/ai-research/reports") {
      return json(route, {
        selected_date: url.searchParams.get("date"),
        available_dates: ["2026-07-15"],
        reports: [{ run_id: researchReport.run_id, research_date: "2026-07-15", title: researchReport.title, summary: researchReport.summary }],
        billing_status: datedBillingStatus,
        billing_cost: datedBillingStatus === "pending_view" ? 2 : 0,
        user: fixtureUser,
      });
    }
    if (path === `/api/ai-research/reports/${researchReport.run_id}/status`) {
      return json(route, { status: "done", stage: "done", billing_status: "charged", report: researchReport, user: fixtureUser });
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
  // Some shells render a desktop sidebar and a mobile bottom nav together;
  // only the breakpoint-appropriate navigation participates in layout.
  const nav = page.locator(":is(.review-workbench-nav, .mobile-only-feature-nav):visible");
  await expect(nav).toBeVisible();
  await expect(nav.locator("a")).toHaveCount(6);

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

    test("six core features expose an unobstructed unified navigation", async ({ page }) => {
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
      test("paid report actions remain visible above the six-feature navigation", async ({ page }) => {
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

test.describe("AI research beginner decision layer", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("shows the decision first and keeps professional research collapsed", async ({ page }) => {
    await installStableApiFixtures(page, { beginnerV2: true });
    await page.goto("/ai-research", { waitUntil: "domcontentloaded" });

    const dashboard = page.locator(".ai-beginner-dashboard");
    await expect(dashboard).toBeVisible();
    await expect(dashboard.getByText("谨慎观察")).toBeVisible();
    await expect(dashboard.getByText("AI 硬件", { exact: true })).toBeVisible();
    await expect(dashboard.getByRole("heading", { name: "继续观察" })).toBeVisible();
    await expect(dashboard.getByRole("heading", { name: "立即放弃" })).toBeVisible();
    await expect(dashboard.getByRole("heading", { name: "我该怎么做" })).toBeVisible();
    await expect(dashboard.getByText("开盘直接追着热度行动。")).toBeVisible();

    const research = page.locator("details.mobile-report-disclosure").filter({ hasText: "研究依据与术语解释" }).first();
    await expect(research).not.toHaveAttribute("open", "");
    await expectNoGlobalHorizontalOverflow(page, "AI research beginner decision layer");
  });
});

test.describe("Market Day v2 beginner decision layer", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("shows what changed first, keeps professional content collapsed, and avoids mobile overflow", async ({ page }) => {
    await installStableApiFixtures(page, { marketDayBeginnerV2: true });
    await page.goto("/market-day", { waitUntil: "domcontentloaded" });
    await page.locator('input[type="date"]').fill("2026-07-15");

    const dashboard = page.locator(".ai-beginner-dashboard");
    await expect(dashboard).toBeVisible();
    await expect(dashboard.getByText("今天发生了什么 / 相比昨天")).toBeVisible();
    await expect(dashboard.getByText("相比昨天，涨停更多了。")).toBeVisible();
    await expect(dashboard.getByText("明天只观察：")).toBeVisible();
    await expect(dashboard.getByText("设备链修复", { exact: true })).toBeVisible();
    await expect(dashboard.getByRole("heading", { name: "继续观察" })).toBeVisible();
    await expect(dashboard.getByRole("heading", { name: "立即停止" })).toBeVisible();
    await expect(dashboard.getByRole("heading", { name: "明天开盘后怎么观察" })).toBeVisible();
    const timeline = dashboard.locator(".action-flow ol");
    await expect(timeline.getByText("09:25", { exact: true })).toBeVisible();
    await expect(timeline.getByText("09:35", { exact: true })).toBeVisible();
    await expect(timeline.getByText("10:30", { exact: true })).toBeVisible();

    const researchToggle = dashboard.locator(".research-details > button");
    await expect(researchToggle).toHaveAttribute("aria-expanded", "false");
    await expect(dashboard.getByText("市场热度样本（不是推荐）")).toHaveCount(0);
    await expectNoGlobalHorizontalOverflow(page, "Market Day v2 beginner decision layer");
  });
});

test.describe("homepage guest acquisition", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("financial disclaimer links users to the rewarded feedback form", async ({ page }) => {
    await page.route("**/api/**", (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/update-notices/latest") return json(route, { notice: null });
      if (path === "/api/auction-strength/performance") return json(route, { rows: [] });
      return json(route, {});
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    const disclaimer = page.locator(".financial-disclaimer").first();
    await disclaimer.locator("summary").click();
    await expect(disclaimer.getByText("有效反馈被采纳后，可获赠 10 次使用次数。")).toBeVisible();
    const feedbackLink = disclaimer.getByRole("link", { name: "提交反馈" });
    await expect(feedbackLink).toHaveAttribute("href", "/#feedback");
    await feedbackLink.click();
    await expect(page).toHaveURL(/\/#feedback$/);
    await expect(page.locator("#feedback")).toBeVisible();
  });

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

  test("temporary auth API failure preserves the cached signed-in identity", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.addInitScript((user) => {
      window.localStorage.setItem("ai_trade_token", "still-valid-token");
      window.localStorage.setItem("ai_trade_user", JSON.stringify(user));
    }, { ...fixtureUser, role: "user" });
    await page.route("**/api/**", (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/auth/me") {
        return route.fulfill({ status: 502, contentType: "text/html", body: "<html><h1>Bad Gateway</h1></html>" });
      }
      if (path === "/api/update-notices/latest") return json(route, { notice: null });
      if (path === "/api/auction-strength/performance") return json(route, { rows: [] });
      return json(route, {});
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".home-user-pill")).toContainText("账号已保留 · responsive-test");
    await expect.poll(() => page.evaluate(() => window.localStorage.getItem("ai_trade_token"))).toBe("still-valid-token");
    await expect(page.locator(".nav-links").getByRole("link", { name: "登录" })).toHaveCount(0);
  });

  test("homepage navigation exposes the value investing feature", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.route("**/api/**", (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/auth/me") return json(route, { user: null });
      if (path === "/api/update-notices/latest") return json(route, { notice: null });
      if (path === "/api/auction-strength/performance") return json(route, { rows: [] });
      return json(route, {});
    });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".nav-links").getByRole("link", { name: "价值投资" })).toHaveAttribute("href", "/stock-research");
  });

  test("feedback form sends an optional screenshot as multipart data", async ({ page }) => {
    let contentType = "";
    let requestBody = "";
    await page.addInitScript((user) => {
      window.localStorage.setItem("ai_trade_token", "feedback-token");
      window.localStorage.setItem("ai_trade_user", JSON.stringify(user));
    }, { ...fixtureUser, role: "user" });
    await page.route("**/api/**", (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/auth/me") return json(route, { user: { ...fixtureUser, role: "user" } });
      if (path === "/api/feedback") {
        contentType = route.request().headers()["content-type"] || "";
        requestBody = route.request().postData() || "";
        return json(route, { feedback: { id: 1, status: "pending" }, user: fixtureUser });
      }
      if (path === "/api/update-notices/latest") return json(route, { notice: null });
      if (path === "/api/auction-strength/performance") return json(route, { rows: [] });
      return json(route, {});
    });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.locator("#feedback textarea").fill("TOP5 页面无法加载，请查看截图");
    await page.locator("#feedback input[type=file]").setInputFiles({
      name: "top5-error.png",
      mimeType: "image/png",
      buffer: Buffer.from("89504e470d0a1a0a", "hex"),
    });
    await page.locator("#feedback button[type=submit]").click();
    await expect(page.getByText("反馈已提交。若被采纳，管理员会为你发放 10 次免费机会。")).toBeVisible();
    expect(contentType).toContain("multipart/form-data");
    expect(requestBody).toContain("top5-error.png");
    expect(requestBody).toContain("TOP5 页面无法加载，请查看截图");
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

  test("shows monthly then annual and uses only WeChat for the selected order", async ({ page }) => {
    let submittedPlanId = "";
    let submittedPaymentMethod = "";
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
      if (path === "/api/pay/membership/orders/88/submit" && route.request().method() === "POST") {
        submittedPaymentMethod = String(route.request().postDataJSON()?.payment_method || "");
        return json(route, {
          order: {
            id: 88,
            order_no: "YMRESPONSIVE",
            plan_name: "年度会员",
            amount_cents: 39900,
            status: "submitted",
            package_id: "annual_membership",
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
    await expect(page.getByText("支付宝", { exact: false })).toHaveCount(0);
    await expect(page.getByAltText("微信收款二维码")).toBeVisible();
    await expect(page.getByLabel("付款方式")).toHaveValue("微信支付");
    await expect(page.getByLabel("实付金额")).toHaveValue("399.00");
    await page.getByRole("button", { name: "我已付款，通知管理员" }).click();
    await expect.poll(() => submittedPaymentMethod).toBe("wechat");
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
    const newestNotice = {
      id: 2,
      title: "Newest notice",
      version: "v2",
      items: ["Newest item"],
      content_markdown: "## 本次更新\n- 支持 **Markdown**\n- 查看 [说明](https://example.test/docs)\n<script>alert(1)</script>",
      published_at: "2026-07-19T10:00:00+08:00",
    };
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
    await expect(dialog.getByRole("heading", { name: "本次更新" })).toBeVisible();
    await expect(dialog.locator("strong")).toHaveText("Markdown");
    await expect(dialog.getByRole("link", { name: "说明" })).toHaveAttribute("href", "https://example.test/docs");
    await expect(dialog.locator("script")).toHaveCount(0);
    await expect(dialog).toContainText("<script>alert(1)</script>");
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

  test("authenticated credits order renders only the configured WeChat payment QR code", async ({ page }) => {
    await page.addInitScript((user) => {
      window.localStorage.setItem("ai_trade_token", "credits-order-token");
      window.localStorage.setItem("ai_trade_user", JSON.stringify(user));
    }, fixtureUser);
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/update-notices/pending") return json(route, { notices: [] });
      if (path === "/api/public/credits/catalog") return json(route, creditCatalog);
      if (path === "/api/pay/credits/orders/latest") return json(route, {
        ...creditCatalog,
        payment_assets: creditPaymentAssets,
        user: fixtureUser,
        order: {
          id: 91,
          order_no: "CREDIT-PENDING",
          plan_name: "12 次使用",
          credits: 12,
          amount_cents: 1200,
          status: "pending",
        },
      });
      if (path === "/api/orders/91") return json(route, { order: null });
      return json(route, {});
    });
    await page.goto("/credits", { waitUntil: "domcontentloaded" });
    const wechatQr = page.getByAltText("微信收款二维码");
    await expect(page.getByText("支付宝", { exact: false })).toHaveCount(0);
    await expect(wechatQr).toBeVisible();
    await expect(page.getByLabel("付款方式")).toHaveValue("微信支付");
    const wechatBox = await wechatQr.evaluate((node) => {
      const rect = node.getBoundingClientRect();
      return { width: rect.width, height: rect.height };
    });
    expect(wechatBox.width).toBeGreaterThanOrEqual(300);
    expect(wechatBox.height / wechatBox.width).toBeCloseTo(1124 / 828, 2);
    await expect(page.getByText("收款码暂未配置")).toHaveCount(0);
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

  test("Daily TOP5 shows a retry action for an HTML 502 instead of a false empty state", async ({ page }) => {
    await installStableApiFixtures(page);
    await page.route("**/api/auction-strength?**", (route) =>
      route.fulfill({ status: 502, contentType: "text/html", body: "<html><h1>Bad Gateway</h1></html>" }),
    );
    await page.goto("/auction-strength", { waitUntil: "domcontentloaded" });
    const alert = page.locator(".auction-load-error");
    await expect(alert).toContainText("每日 TOP5 暂时无法加载");
    await expect(alert).toContainText("服务暂时不可用，请稍后重试。");
    await expect(alert.getByRole("button", { name: "重新加载" })).toBeVisible();
    await expect(page.locator(".auction-waiting-panel")).toHaveCount(0);
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

// Route-based admin coverage moved to admin-routing.spec.ts. Keeping this legacy
// query-section suite skipped prevents duplicate assertions against the removed
// single-page admin architecture while preserving the historical scenarios.
test.describe.skip("legacy query-section admin access", () => {
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
    let requestedIdentity = "";
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
      requestedIdentity = String(payload.expected_identity || "");
      managedUserStatus = payload.status === "disabled" ? "disabled" : "active";
      return json(route, { user: { id: 8, display_name: "credit-user", status: managedUserStatus } });
    });
    await page.route("**/api/admin/orders/18/confirm-credits", async (route) => {
      confirmedCreditOrderId = new URL(route.request().url()).pathname.split("/")[4] || "";
      return json(route, { ok: true });
    });

    await page.goto("/admin?section=users&days=30", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("button", { name: "暂停账号" })).toBeVisible();
    page.once("dialog", async (dialog) => {
      expect(dialog.message()).toContain("credit-user");
      expect(dialog.message()).toContain("用户 ID：8");
      await dialog.accept();
    });
    await page.getByRole("button", { name: "暂停账号" }).click();
    await expect.poll(() => requestedStatus).toBe("disabled");
    expect(requestedIdentity).toBe("credit-user");
    await expect(page.getByText("账号“credit-user”（用户 ID：8）已暂停，现有 session 已失效。")).toBeVisible();

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

  test("admin separates automated email campaigns from update notices and retries terminal failures", async ({ page }) => {
    await installStableApiFixtures(page);
    let retriedTop5CampaignId = "";
    let retriedAiCampaignId = "";
    await page.route("**/api/admin/daily-top5-email-campaigns/*/retry", (route) => {
      retriedTop5CampaignId = new URL(route.request().url()).pathname.split("/").at(-2) || "";
      return json(route, { email_campaign: { id: 17, status: "pending" } });
    });
    await page.route("**/api/admin/ai-report-email-campaigns/*/retry", (route) => {
      retriedAiCampaignId = new URL(route.request().url()).pathname.split("/").at(-2) || "";
      return json(route, { email_campaign: { id: 19, status: "pending" } });
    });
    await page.route("**/api/admin/dashboard**", (route) => json(route, {
      totals: { users: 2, credits: 20, feedback_pending: 0, orders_paid: 0 },
      usage_by_day: [], new_users_by_day: [], feedback: [], orders: [], managed_users: [], top_users: [], credit_grant_campaigns: [], update_notices: [],
      daily_top5_email_failed_count: 1,
      daily_top5_close_email_failed_count: 2,
      ai_report_email_failed_count: 1,
      daily_top5_email_campaigns: [
        {
          id: 17, trade_date: "2026-07-16", report_id: "report-17", status: "partial_failed",
          total: 6, pending: 0, sending: 0, sent: 4, failed: 1, permanent_failed: 0, retryable_failed: 1,
          skipped: 1, full: 2, teaser: 4,
          created_at: "2026-07-16T09:26:00+08:00", next_retry_at: null, started_at: null, finished_at: null,
        },
        {
          id: 16, trade_date: "2026-07-15", report_id: "report-16", status: "partial_failed",
          total: 6, pending: 0, sending: 0, sent: 4, failed: 1, permanent_failed: 1, retryable_failed: 0,
          skipped: 1, full: 2, teaser: 4,
          created_at: "2026-07-15T09:26:00+08:00", next_retry_at: null, started_at: null, finished_at: null,
        },
      ],
      ai_report_email_campaigns: [
        {
          id: 18, report_type: "market_day", run_id: "market-18", report_date: "2026-07-16", status: "pending",
          total: 5, pending: 2, sending: 0, sent: 2, failed: 0, skipped: 1, full: 1, teaser: 3,
          created_at: "2026-07-16T16:00:00+08:00", next_retry_at: "2026-07-16T16:30:00+08:00",
        },
        {
          id: 19, report_type: "ai_research", run_id: "research-19", report_date: "2026-07-16", status: "partial_failed",
          total: 5, pending: 0, sending: 0, sent: 3, failed: 1, skipped: 1, full: 1, teaser: 3,
          created_at: "2026-07-16T07:30:00+08:00", next_retry_at: null,
        },
      ],
    }));
    await page.goto("/admin?section=emails&days=30", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("button", { name: "邮件推送" }).first()).toHaveAttribute("aria-current", "page");

    const top5Panel = page.locator("article").filter({ has: page.getByRole("heading", { name: "每日 TOP5 邮件任务" }) });
    const marketPanel = page.locator("article").filter({ has: page.getByRole("heading", { name: "市场日报邮件任务" }) });
    const researchPanel = page.locator("article").filter({ has: page.getByRole("heading", { name: "AI 复盘邮件任务" }) });
    const retryableFailure = top5Panel.locator(".admin-list-item").filter({ hasText: "2026-07-16" });
    await expect(retryableFailure.getByText("完整版 2 · 摘要版 4")).toBeVisible();
    await expect(retryableFailure.getByText("成功 4 · 待发送 0 · 发送中 0 · 失败 1 · 跳过 1")).toBeVisible();
    const permanentFailure = top5Panel.locator(".admin-list-item").filter({ hasText: "2026-07-15" });
    await expect(permanentFailure.getByText("成功 4 · 待发送 0 · 发送中 0 · 永久失败 1 · 跳过 1")).toBeVisible();
    await expect(permanentFailure.getByRole("button", { name: "重试失败邮件" })).toHaveCount(0);
    await expect(marketPanel.getByText("等待自动重试：2026-07-16 16:30")).toBeVisible();
    await expect(marketPanel.getByRole("button", { name: "重试失败邮件" })).toHaveCount(0);
    await expect(researchPanel.getByRole("button", { name: "重试失败邮件" })).toBeVisible();

    await retryableFailure.getByRole("button", { name: "重试失败邮件" }).click();
    await expect.poll(() => retriedTop5CampaignId).toBe("17");
    await researchPanel.getByRole("button", { name: "重试失败邮件" }).click();
    await expect.poll(() => retriedAiCampaignId).toBe("19");

    await page.getByRole("button", { name: "总览" }).first().click();
    await page.getByRole("button", { name: /失败 TOP5 邮件/ }).click();
    await expect(page.getByRole("heading", { name: "每日 TOP5 邮件任务" })).toBeVisible();
    await page.getByRole("button", { name: "总览" }).first().click();
    await page.getByRole("button", { name: /失败公告邮件/ }).click();
    await expect(page.getByRole("heading", { name: "公告列表" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "每日 TOP5 邮件任务" })).toHaveCount(0);
    await expectNoGlobalHorizontalOverflow(page, "automated email campaigns");
  });

  test("admin publishes an update notice with the restored simple form and email delivery", async ({ page }) => {
    await installStableApiFixtures(page);
    let publishedPayload: Record<string, unknown> | null = null;
    await page.route("**/api/admin/update-notices", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      publishedPayload = route.request().postDataJSON() as Record<string, unknown>;
      return json(route, {
        notice: { id: 21, status: "published" },
        email_campaign: { pending: 2, skipped: 0 },
      }, 201);
    });

    await page.goto("/admin?section=updates&days=30", { waitUntil: "domcontentloaded" });
    await page.getByPlaceholder("公告标题，例如：本周更新").fill("发布流程回归");
    await page.getByPlaceholder("公告摘要（可选，会显示在正文前）").fill("发布流程摘要");
    await page.getByPlaceholder(/^Markdown 正文（必填）/).fill("## 本次更新\n- 修复公告发布\n- 恢复 **邮件推送**");

    await page.getByRole("button", { name: "保存并发布" }).click();
    await expect(page.getByRole("dialog", { name: "如何发布本次更新？" })).toBeVisible();
    await page.getByRole("button", { name: "网站弹窗 + 邮件推送" }).click();

    await expect.poll(() => publishedPayload).not.toBeNull();
    expect(publishedPayload).toMatchObject({
      title: "发布流程回归",
      summary: "发布流程摘要",
      content_markdown: "## 本次更新\n- 修复公告发布\n- 恢复 **邮件推送**",
      status: "published",
      send_email: true,
    });
    await expect(page.getByText(/公告已发布，邮件任务已创建/)).toBeVisible();
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
