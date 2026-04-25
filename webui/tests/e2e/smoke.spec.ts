import { expect, test } from "@playwright/test";

const ROUTES = [
  { path: "/", title: /Dashboard/i },
  { path: "/chat", title: /Chat/i },
  { path: "/strategies", title: /Strategies/i },
  { path: "/backtest", title: /Backtest/i },
  { path: "/data/explorer", title: /Data Explorer/i },
  { path: "/data/sources", title: /Sources/i },
  { path: "/workflows/agent", title: /Agent Crew/i },
  { path: "/workflows/data", title: /Data pipeline/i },
  { path: "/workflows/strategy", title: /Strategy composer/i },
];

for (const r of ROUTES) {
  test(`smoke: ${r.path} renders without crashing`, async ({ page }) => {
    await page.goto(r.path);
    await expect(page.locator("h3, h5").first()).toContainText(r.title);
  });
}
