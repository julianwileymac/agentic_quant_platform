import { expect, test } from "@playwright/test";

test.describe("Phase 3 — RAG Admin smoke", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/aqp-api/**", async (route) => {
      const url = route.request().url();
      if (url.includes("/health")) return route.fulfill({ json: { status: "ok" } });
      if (url.includes("/rag/corpora"))
        return route.fulfill({
          json: [
            {
              name: "strategies",
              order: "third",
              l1: "research",
              l2: "alpha",
              chunks: 1024,
              last_indexed_at: "2025-05-01T00:00:00Z",
            },
          ],
        });
      if (url.endsWith("/")) return route.fulfill({ json: { app: "AQP", routes: [] } });
      return route.fulfill({ json: {} });
    });
  });

  test("Refresh L0 button gates on the typed REFRESH phrase", async ({ page }) => {
    await page.goto("/rag/admin");
    await expect(page.getByRole("heading", { name: /^RAG Admin$/ })).toBeVisible();

    await page.getByRole("button", { name: /Refresh L0$/ }).click();

    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    const submit = dialog.getByRole("button", { name: /Refresh L0 base/i });
    await expect(submit).toBeDisabled();

    await page.getByLabel(/Type/i).fill("WRONG");
    await expect(submit).toBeDisabled();
    await page.getByLabel(/Type/i).fill("REFRESH");
    await expect(submit).toBeEnabled();
    await page.keyboard.press("Escape");
  });
});
