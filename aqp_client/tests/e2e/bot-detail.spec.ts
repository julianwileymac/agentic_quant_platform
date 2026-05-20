import { expect, test } from "@playwright/test";

const BOT_ID = "bot-aapl-mr";

const BOT_FIXTURE = {
  id: BOT_ID,
  name: "AAPL Mean Rev",
  kind: "trading",
  status: "running",
  current_version: 3,
  description: "Test fixture",
  spec: { strategy: { class: "FrameworkAlgorithm", module_path: "aqp.strategies.framework" } },
  pnl_total: 1234,
  sharpe: 1.42,
  annotations: ["test"],
  created_at: "2024-12-01T00:00:00Z",
  updated_at: "2025-05-01T00:00:00Z",
};

test.describe("Phase 2.5 — Bot Detail smoke", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/aqp-api/**", (route) => {
      const url = route.request().url();
      if (url.includes("/health")) return route.fulfill({ json: { status: "ok" } });
      if (url.endsWith("/bots") || url.includes("/bots?")) {
        return route.fulfill({ json: [BOT_FIXTURE] });
      }
      if (url.includes(`/bots/${BOT_ID}/versions`)) {
        return route.fulfill({
          json: [
            {
              id: "v3",
              bot_id: BOT_ID,
              version: 3,
              spec_hash: "abcdef0123456789abcdef0123456789",
              created_at: "2025-05-01T00:00:00Z",
              notes: "active",
            },
          ],
        });
      }
      if (url.includes(`/bots/${BOT_ID}/deployments`)) return route.fulfill({ json: [] });
      if (url.includes(`/bots/${BOT_ID}/halt`)) return route.fulfill({ json: { ok: true } });
      if (url.includes(`/bots/${BOT_ID}`)) return route.fulfill({ json: BOT_FIXTURE });
      if (url.endsWith("/")) return route.fulfill({ json: { app: "AQP", routes: [] } });
      return route.fulfill({ json: {} });
    });
  });

  test("list -> detail -> friction-gated halt", async ({ page }) => {
    await page.goto("/bots");
    await expect(page.getByRole("heading", { name: /^Bots$/ })).toBeVisible();
    const row = page.getByText("AAPL Mean Rev");
    await expect(row).toBeVisible();
    await row.click();

    await expect(page).toHaveURL(new RegExp(`/bots/${BOT_ID}$`));
    await expect(page.getByRole("heading", { name: /AAPL Mean Rev/ })).toBeVisible();

    // Halt button gates on typed phrase.
    await page.getByRole("button", { name: /^Halt$/ }).click();
    const halt = page.getByRole("button", { name: /Halt bot/i });
    await expect(halt).toBeDisabled();
    await page.getByLabel(/Type/i).fill("HALT");
    await expect(halt).toBeEnabled();
    await page.keyboard.press("Escape");
  });
});
