import { expect, test } from "@playwright/test";

const BT_ID = "bt-001";

const RUN_FIXTURE = {
  id: BT_ID,
  run_name: "smoke-backtest",
  engine: "vbt-pro",
  strategy: "FrameworkAlgorithm",
  status: "completed",
  pnl_total: 5_432.1,
  sharpe: 1.32,
  sortino: 1.65,
  max_drawdown: -0.07,
  win_rate: 0.6,
  total_return: 0.21,
  started_at: "2025-01-01T00:00:00Z",
  ended_at: "2025-01-02T00:00:00Z",
};

const EQUITY_PLOT = {
  data: [
    {
      x: ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"],
      y: [100, 102, 104, 110],
      name: "equity",
      type: "scatter",
    },
  ],
};

test.describe("Phase 2.5 — Backtest Detail smoke", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/aqp-api/**", (route) => {
      const url = route.request().url();
      if (url.includes("/health")) return route.fulfill({ json: { status: "ok" } });
      if (url.endsWith("/backtest/runs") || url.includes("/backtest/runs?")) {
        return route.fulfill({ json: [RUN_FIXTURE] });
      }
      if (url.includes(`/backtest/runs/${BT_ID}/plot/equity`)) return route.fulfill({ json: EQUITY_PLOT });
      if (url.includes(`/backtest/runs/${BT_ID}/plot/drawdown`)) return route.fulfill({ json: { data: [] } });
      if (url.includes(`/backtest/runs/${BT_ID}/trades`)) return route.fulfill({ json: [] });
      if (url.includes(`/backtest/runs/${BT_ID}`)) return route.fulfill({ json: RUN_FIXTURE });
      if (url.endsWith("/")) return route.fulfill({ json: { app: "AQP", routes: [] } });
      return route.fulfill({ json: {} });
    });
  });

  test("list -> detail -> equity chart loads", async ({ page }) => {
    await page.goto("/backtest");
    await expect(page.getByRole("heading", { name: /^Backtests$/ })).toBeVisible();
    const row = page.getByText("smoke-backtest");
    await expect(row).toBeVisible();
    await row.click();

    await expect(page).toHaveURL(new RegExp(`/backtest/${BT_ID}$`));
    await expect(page.getByRole("heading", { name: /smoke-backtest/ })).toBeVisible();

    // EquityChart renders a div tagged with data-equity-chart="true" once
    // data is non-empty.
    await expect(page.locator('[data-equity-chart="true"]').first()).toBeVisible();
    await expect(page.getByText(/Equity curve/)).toBeVisible();
    await expect(page.getByText(/Trades \(/)).toBeVisible();
  });
});
