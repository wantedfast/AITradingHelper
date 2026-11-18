import { expect, test, type Page, type Route } from "@playwright/test";

// Homepage "交易日航海图": the live trading-day clock must point visitors at
// the right tool for the current Beijing time, and the page must stay honest
// and accessible.

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function stubApi(page: Page) {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me") return json(route, { user: null });
    if (path === "/api/public/membership/plans") {
      return json(route, {
        plans: [
          { id: "monthly_membership", plan_name: "月度会员", amount_cents: 5900, duration_days: 31 },
          { id: "annual_membership", plan_name: "年度会员", amount_cents: 39900, duration_days: 365 },
        ],
        checkout: {},
      });
    }
    return json(route, {});
  });
}

// Fixed instants (UTC) and what a Beijing (UTC+8) visitor should be told.
const MOMENTS = [
  { utc: "2026-11-18T01:27:00Z", time: "09:27", phase: "集合竞价刚结束", tool: "每日 TOP5", href: "/auction-strength" },
  { utc: "2026-11-18T02:40:00Z", time: "10:40", phase: "上午盘中", tool: "市场真实强弱", href: "/market-breadth" },
  { utc: "2026-11-18T08:10:00Z", time: "16:10", phase: "收盘后", tool: "AI 复盘", href: "/review" },
  { utc: "2026-11-21T03:00:00Z", time: "11:00", phase: "周末休市", tool: "价值投资", href: "/stock-research" },
];

test.describe("homepage trading-day clock", () => {
  test.use({ viewport: { width: 1280, height: 900 }, timezoneId: "America/New_York" });

  for (const moment of MOMENTS) {
    test(`at Beijing ${moment.time} it recommends ${moment.tool}`, async ({ page }) => {
      // The visitor's own timezone is New York on purpose: the clock must use Beijing time.
      await page.clock.setFixedTime(new Date(moment.utc));
      await stubApi(page);
      // The readout is client-rendered (it needs the visitor's real clock), so wait for hydration.
      await page.goto("/", { waitUntil: "load" });
      const clock = page.locator(".yh-clock");
      await expect(clock.locator(".yh-clock__readout b")).toHaveText(moment.time);
      await expect(clock.locator(".yh-clock__readout em")).toHaveText(moment.phase);
      await expect(clock.getByRole("link", { name: moment.tool })).toHaveAttribute("href", moment.href);
      await expect(page.locator(".yh-route__list > li.is-now").getByRole("heading", { name: moment.tool })).toBeVisible();
    });
  }
});

test.describe("homepage content and accessibility", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("has one h1, honest performance copy, plan links and a working skip link", async ({ page }) => {
    await stubApi(page);
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.locator("h1")).toHaveCount(1);
    await expect(page.locator("h1")).toContainText("先看懂市场");
    await expect(page.locator(".yh-record")).toContainText("历史表现不代表未来收益");
    await expect(page.locator(".yh-ledger caption")).toContainText("红涨绿跌");
    // A-share convention, and a regression: a global `.is-up !important` once turned gains black.
    await expect(page.locator(".yh-ledger td.yh-up").first()).toHaveCSS("color", "rgb(215, 0, 21)");
    await expect(page.getByRole("link", { name: "开通年度会员" })).toHaveAttribute("href", "/billing?plan_id=annual_membership");
    await expect(page.getByRole("link", { name: "开通月度会员" })).toHaveAttribute("href", "/billing?plan_id=monthly_membership");
    await expect(page.locator(".yh-pricing")).not.toContainText("七项功能不限次数");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "跳到正文" })).toBeFocused();
    const images = await page.locator(".yh img").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("alt")));
    expect(images.every((alt) => alt !== null)).toBe(true);
  });

  test("reduced motion still shows every section", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    await stubApi(page);
    await page.goto("/", { waitUntil: "domcontentloaded" });
    for (const selector of [".yh-route__list > li", ".yh-plan", ".yh-ledger"]) {
      const opacity = await page.locator(selector).first().evaluate((node) => getComputedStyle(node).opacity);
      expect(opacity).toBe("1");
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
    await context.close();
  });

  test("tablet header keeps every feature reachable", async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 1024, height: 768 } });
    const page = await context.newPage();
    await stubApi(page);
    await page.goto("/", { waitUntil: "domcontentloaded" });

    const menuButton = page.getByRole("button", { name: "打开导航" });
    await expect(menuButton).toBeVisible();
    await menuButton.click();
    await expect(page.getByRole("navigation", { name: "手机导航" }).getByRole("link", { name: "价值投资" })).toHaveAttribute("href", "/stock-research");

    await context.close();
  });
});
