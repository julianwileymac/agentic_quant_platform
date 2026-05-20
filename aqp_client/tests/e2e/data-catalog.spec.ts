import { expect, test } from "@playwright/test";

const NAMESPACES = [
  { namespace: "aqp_silver_yfinance", table_count: 2, medallion_layer: "silver" },
  { namespace: "aqp_gold_signals", table_count: 1, medallion_layer: "gold" },
];

const TABLES_BY_NAMESPACE: Record<string, unknown[]> = {
  aqp_silver_yfinance: [
    {
      namespace: "aqp_silver_yfinance",
      name: "bars_1d",
      row_count: 12_345,
      partition_spec: ["day"],
      last_snapshot_at: "2025-05-01T00:00:00Z",
      medallion_layer: "silver",
    },
  ],
  aqp_gold_signals: [
    {
      namespace: "aqp_gold_signals",
      name: "alpha_v1",
      row_count: 100,
      partition_spec: [],
      medallion_layer: "gold",
    },
  ],
};

const TABLE_DETAIL = {
  namespace: "aqp_silver_yfinance",
  name: "bars_1d",
  row_count: 12_345,
  medallion_layer: "silver",
  schema: {
    fields: [
      { name: "ts", type: "timestamp" },
      { name: "vt_symbol", type: "string" },
      { name: "open", type: "double" },
      { name: "close", type: "double" },
    ],
  },
  partition_spec_full: [{ source_id: 1, transform: "day", field: "ts" }],
};

test.describe("Phase 3 — Data Catalog smoke", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/aqp-api/**", async (route) => {
      const url = route.request().url();
      if (url.includes("/health")) {
        return route.fulfill({ json: { status: "ok" } });
      }
      if (url.includes("/data/catalog/namespaces")) {
        return route.fulfill({ json: NAMESPACES });
      }
      const tableMatch = url.match(/\/data\/catalog\/([^/]+)\/([^/?]+)$/);
      if (tableMatch) {
        return route.fulfill({ json: TABLE_DETAIL });
      }
      const sampleMatch = url.match(/\/data\/catalog\/[^/]+\/[^/]+\/sample/);
      if (sampleMatch) {
        return route.fulfill({ json: { columns: [], rows: [] } });
      }
      const snapshotsMatch = url.match(/\/data\/catalog\/[^/]+\/[^/]+\/snapshots/);
      if (snapshotsMatch) {
        return route.fulfill({ json: [] });
      }
      const namespaceMatch = url.match(/\/data\/catalog\/([^/?]+)$/);
      if (namespaceMatch) {
        const ns = namespaceMatch[1] ?? "";
        return route.fulfill({ json: TABLES_BY_NAMESPACE[ns] ?? [] });
      }
      if (url.endsWith("/")) {
        return route.fulfill({ json: { app: "AQP", routes: [] } });
      }
      return route.fulfill({ json: {} });
    });
  });

  test("namespaces -> tables -> table detail schema", async ({ page }) => {
    await page.goto("/data/catalog");
    await expect(page.getByRole("heading", { name: /^Data Catalog$/ })).toBeVisible();
    // Namespace tile renders.
    const nsButton = page.getByRole("button", { name: /aqp_silver_yfinance/i });
    await expect(nsButton).toBeVisible();
    await nsButton.click();

    // Table row renders in the right pane and is clickable.
    const tableRow = page.getByText("bars_1d", { exact: true }).first();
    await expect(tableRow).toBeVisible();
    await tableRow.click();

    await expect(page).toHaveURL(/\/data\/catalog\/aqp_silver_yfinance\/bars_1d$/);
    await expect(page.getByRole("heading", { name: /aqp_silver_yfinance.bars_1d/ })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Schema/ })).toBeVisible();
    await expect(page.getByText("vt_symbol")).toBeVisible();
  });
});
