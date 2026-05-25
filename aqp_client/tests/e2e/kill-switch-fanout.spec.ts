import { expect, test } from "@playwright/test";

/**
 * Phase 1 §4.4 — kill-switch fan-out.
 *
 * The TopBar `KillSwitch` component (`src/components/common/KillSwitch.tsx`)
 * fans out to a hard-coded list of halt endpoints in parallel. This
 * spec verifies:
 *   1. The Halt button surfaces in the TopBar.
 *   2. Clicking it opens the `ConfirmFrictionDialog` listing every
 *      target subsystem.
 *   3. Cancelling does NOT POST anything.
 *
 * The full fan-out POST assertion lives in a separate integration
 * test that authenticates against a step-up MFA stub; here we keep
 * the test green-no-network-on-cancel so it stays a smoke check.
 */
const HALT_PATHS = [
  "/agents/halt",
  "/quant-agents/halt",
  "/paper/stop-all",
  "/bots/halt-all",
  "/rl/halt-all",
  "/workflows/halt",
  "/assistants/halt",
  "/terraform/halt",
  "/workloads/halt",
  "/manage/streaming/halt",
  "/manage/lakehouse/halt",
  "/lab/halt-all",
  "/ml/serving/halt-all",
] as const;

test.describe("Phase 1 §4.4 — kill-switch fan-out", () => {
  let postedPaths: string[] = [];

  test.beforeEach(async ({ page }) => {
    postedPaths = [];
    await page.route("**/aqp-api/**", (route) => {
      const url = route.request().url();
      const method = route.request().method();
      if (url.includes("/health")) return route.fulfill({ json: { status: "ok" } });
      // Capture every halt POST so the test can assert the fan-out
      // included every advertised subsystem.
      for (const path of HALT_PATHS) {
        if (url.endsWith(path) && method === "POST") {
          postedPaths.push(path);
          return route.fulfill({
            json: { ok: true, path, halted_count: 0 },
          });
        }
      }
      // Auth + workspace bootstrap returns OK so the AppShell mounts.
      if (url.includes("/auth/me"))
        return route.fulfill({
          json: {
            user: { id: "user-001", email: "alice@example.test" },
            tenant: { workspace_id: "ws-1", organization_id: "org-1" },
          },
        });
      if (url.endsWith("/")) return route.fulfill({ json: { app: "AQP", routes: [] } });
      return route.fulfill({ json: {} });
    });
  });

  test("kill-switch dialog enumerates every halt endpoint", async ({ page }) => {
    await page.goto("/");
    // The TopBar Halt button is keyed off `aria-label`.
    const halt = page.getByRole("button", {
      name: /Kill switch — halt all running agents, bots, and paper sessions/i,
    });
    await expect(halt).toBeVisible({ timeout: 10_000 });
    await halt.click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    // Every halt endpoint is rendered as a tone="warn" detail row in
    // the dialog body. Asserting the path strings is the strongest
    // contract because the labels may be reworded over time.
    for (const path of HALT_PATHS) {
      await expect(dialog.getByText(path)).toBeVisible();
    }
    // Cancelling MUST NOT POST anything.
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    expect(postedPaths).toEqual([]);
  });
});
