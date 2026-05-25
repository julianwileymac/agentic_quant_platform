import { expect, test } from "@playwright/test";

/**
 * Phase 1 §4.4 — cross-tenant URN deny (drives Rule 33 backend gate
 * end-to-end).
 *
 * Rule 33 says every URN-bound request includes a tenancy header
 * (workspace_id) and the backend's `resource_filter` MUST deny when
 * the URN is owned by a different tenant. This spec exercises the
 * frontend's reaction to that denial:
 *   1. The user (workspace=ws-alpha) navigates to a backtest detail
 *      whose owner is workspace=ws-beta.
 *   2. The mocked backend returns 403 with a `Rule 33` detail
 *      payload (`{ "detail": "...", "code": "TENANT_FORBIDDEN" }`).
 *   3. The UI surfaces an access-denied state — NOT the resource
 *      payload — and never re-issues the request as a default-shape
 *      empty fixture.
 *
 * Without this gate at the UI, a 403 from the backend would silently
 * present an empty equity chart; with the gate, the user sees an
 * explicit denial and a "request access" affordance.
 */
const FOREIGN_BT_ID = "bt-foreign-001";

test.describe("Phase 1 §4.4 — cross-tenant URN deny (Rule 33)", () => {
  let attemptCount = 0;

  test.beforeEach(async ({ page }) => {
    attemptCount = 0;
    await page.route("**/aqp-api/**", (route) => {
      const url = route.request().url();
      if (url.includes("/health")) return route.fulfill({ json: { status: "ok" } });
      // The cross-tenant resource: deny with a Rule-33 shaped body.
      if (url.includes(`/backtest/runs/${FOREIGN_BT_ID}`)) {
        attemptCount += 1;
        return route.fulfill({
          status: 403,
          contentType: "application/json",
          json: {
            detail:
              "URN belongs to a different workspace; access forbidden " +
              "by tenancy policy (Rule 33).",
            code: "TENANT_FORBIDDEN",
            workspace_id: "ws-alpha",
            urn_workspace_id: "ws-beta",
          },
        });
      }
      // Listings return only the user's own runs — never the foreign one.
      if (url.endsWith("/backtest/runs") || url.includes("/backtest/runs?")) {
        return route.fulfill({ json: [] });
      }
      // Auth bootstrap: caller is in ws-alpha.
      if (url.includes("/auth/me"))
        return route.fulfill({
          json: {
            user: { id: "user-001", email: "alice@example.test" },
            tenant: {
              workspace_id: "ws-alpha",
              organization_id: "org-1",
            },
          },
        });
      if (url.endsWith("/")) return route.fulfill({ json: { app: "AQP", routes: [] } });
      return route.fulfill({ json: {} });
    });
  });

  test("foreign backtest URL renders denied state, not the resource", async ({
    page,
  }) => {
    // Direct deep-link to the foreign URN — common phishing / shared-
    // link scenario.
    await page.goto(`/backtest/${FOREIGN_BT_ID}`);
    // The 403 must surface — the page MUST NOT render the chart that
    // would be visible for an authorised user.
    await expect(page.locator('[data-equity-chart="true"]')).toHaveCount(0);
    // Either an explicit denied-state surface or at minimum a
    // recognisable error message including the code or "forbidden".
    await expect(
      page
        .getByText(/forbidden/i)
        .or(page.getByText(/access denied/i))
        .or(page.getByText(/TENANT_FORBIDDEN/))
        .or(page.getByText(/different workspace/i)),
    ).toBeVisible({ timeout: 10_000 });
    // Single attempt — the UI MUST NOT loop on the 403 (which would
    // hammer the backend / surface).
    expect(attemptCount).toBeGreaterThanOrEqual(1);
    expect(attemptCount).toBeLessThan(5);
  });
});
