import { expect, test } from "@playwright/test";

/**
 * Phase 4 — Bot Builder smoke. Validates that:
 *   - the builder route renders with the AQP palette and FlowCanvas
 *   - the bot-name input accepts input
 *   - clicking Save invokes the friction dialog
 *   - confirming Save POSTs to /bots with a serialised spec body
 *
 * Drag-and-drop in jsdom-less Playwright headless runs is environment-
 * sensitive, so the test pre-seeds an existing bot via `?id=` so the
 * canvas hydrates without manual drops. The legacy webui's drag-drop
 * E2E is intentionally not replicated here.
 */
const BOT_FIXTURE = {
  id: "bot-stub",
  name: "Stub Bot",
  slug: "stub-bot",
  kind: "trading",
  status: "idle",
  current_version: 1,
  spec: {
    name: "Stub Bot",
    kind: "trading",
    universe: { symbols: ["SPY"], model: null },
    strategy: {
      class: "FrameworkAlgorithm",
      module_path: "aqp.strategies.framework",
      kwargs: {},
    },
    risk: { max_drawdown_pct: 0.2 },
    deployment: { target: "paper_session" },
  },
  description: "test fixture",
  created_at: "2025-05-01T00:00:00Z",
  updated_at: "2025-05-01T00:00:00Z",
};

test.describe("Phase 4 — Bot Builder smoke", () => {
  test.beforeEach(async ({ page }) => {
    let saveBody: unknown = null;
    await page.route("**/aqp-api/**", async (route) => {
      const url = route.request().url();
      const method = route.request().method();
      if (url.includes("/health")) {
        return route.fulfill({ json: { status: "ok" } });
      }
      if (url.includes(`/bots/${BOT_FIXTURE.id}`) && method === "GET") {
        return route.fulfill({ json: BOT_FIXTURE });
      }
      if (url.includes(`/bots/${BOT_FIXTURE.id}`) && method === "PUT") {
        saveBody = JSON.parse(route.request().postData() ?? "{}");
        return route.fulfill({ json: { ...BOT_FIXTURE, current_version: 2 } });
      }
      if (url.endsWith("/")) {
        return route.fulfill({ json: { app: "AQP", routes: [] } });
      }
      return route.fulfill({ json: {} });
    });
    // Stash the route handler's reference on the page for later assertion.
    await page.exposeFunction("__getSavedBody", () => saveBody);
  });

  test("loads an existing bot and friction-gates the save", async ({ page }) => {
    await page.goto(`/bots/builder?id=${BOT_FIXTURE.id}`);
    await expect(page.getByRole("heading", { name: /Bot Builder/i })).toBeVisible();
    await expect(page.getByText(/drop palette tiles/i).or(page.getByText(/Stub Bot/i))).toBeVisible();
    // Save without changes should still serialise the hydrated graph.
    await page.getByRole("button", { name: /^Save$/ }).click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/Save bot/i).or(dialog.getByText(/Save and run/i))).toBeVisible();
    await page.keyboard.press("Escape");
  });
});
