import { expect, test } from "@playwright/test";

/**
 * High-level smoke for the Phase 1 priority surface. Validates that:
 *   - the application boots and the topbar renders
 *   - the kill-switch opens a friction dialog and gates submission on the
 *     typed-confirmation phrase
 *   - the Action Center route is reachable from the topbar bell
 *
 * The tests stub network so they run hermetically against `pnpm dev`.
 */
test.describe("Phase 1 — Live + Action Center smoke", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/aqp-api/**", (route) => {
      const url = route.request().url();
      if (url.includes("/health")) {
        return route.fulfill({ json: { status: "ok", version: "0.1.0" } });
      }
      if (url.includes("/portfolio/positions")) {
        return route.fulfill({ json: [] });
      }
      if (url.includes("/orders/working")) {
        return route.fulfill({ json: [] });
      }
      if (url.includes("/live/history")) {
        return route.fulfill({ json: [] });
      }
      if (url.includes("/live/book")) {
        return route.fulfill({ json: { bids: [], asks: [] } });
      }
      if (url.includes("/live/subscribe")) {
        return route.fulfill({ json: { channel_id: "stub" } });
      }
      if (url.endsWith("/")) {
        return route.fulfill({ json: { app: "AQP", version: "0.1.0", routes: [] } });
      }
      return route.fulfill({ json: {} });
    });
  });

  test("kill switch friction gates the halt action", async ({ page }) => {
    await page.goto("/");
    const halt = page.getByRole("button", { name: /halt$/i });
    await expect(halt).toBeVisible();
    await halt.click();
    const submit = page.getByRole("button", { name: /halt all subsystems/i });
    await expect(submit).toBeVisible();
    await expect(submit).toBeDisabled();
    await page.getByLabel(/Type/i).fill("HALT");
    await expect(submit).toBeEnabled();
    // Don't actually submit — the network mock would accept it but the
    // intent of this test is to validate the friction gate.
    await page.keyboard.press("Escape");
  });

  test("Action Center is reachable from the topbar bell", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /open action center/i }).click();
    await expect(page.getByRole("heading", { name: /Action Center/i })).toBeVisible();
    await expect(page.getByText(/No pending proposals/i)).toBeVisible();
  });

  test("Live Trading Desk route renders OHLC + ticket", async ({ page }) => {
    await page.goto("/live");
    await expect(page.getByRole("heading", { name: /Live Trading Desk/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /OHLC ·/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Order ticket/i })).toBeVisible();
  });

  test("sandbox mode prefixes the document title", async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem(
        "aqp-tenancy",
        JSON.stringify({ state: { mode: "sandbox" }, version: 0 }),
      );
    });
    await page.goto("/");
    await expect(page).toHaveTitle(/^\[SANDBOX\]/);
  });
});
