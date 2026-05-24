import { test, expect } from "@playwright/test";

test.describe("marketing site", () => {
  test("homepage renders without FOUC", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/AQP/);

    const body = page.locator("body");
    await expect(body).toHaveCSS("background-color", /rgb\(15, 23, 42\)|#0[Ff]172[Aa]/);

    await expect(page.locator("h1").first()).toBeVisible();
  });

  test("login redirect preserves returnTo", async ({ page }) => {
    const response = await page.goto("/dashboard");
    expect(response?.status()).toBeLessThan(400);
    await expect(page).toHaveURL(/\/login\?returnTo=%2Fdashboard/);
  });
});
