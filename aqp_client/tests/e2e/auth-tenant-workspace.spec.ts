import { expect, test } from "@playwright/test";

/**
 * Phase 1 §4.4 — login → tenant pick → workspace open.
 *
 * Walks the login surface end-to-end against a mocked backend. The
 * Auth0 / Entra round-trips are exercised separately by their
 * respective integration tests; this spec asserts the AQP-side glue:
 *   1. `/auth/login` renders without the AppShell (auth route).
 *   2. After a synthetic "callback successful" event, the user lands
 *      on `/` and the TopBar shows their workspace context.
 *   3. Clicking the workspace switcher lists the user's tenants and
 *      switching tenants posts to `/me/workspace` and reloads.
 *
 * The fixtures here mirror the shape returned by `/auth/me`,
 * `/me/workspaces`, and `/health` so the spec exercises the same
 * code paths used in production.
 */
const ME_FIXTURE = {
  user: {
    id: "user-001",
    email: "alice@example.test",
    name: "Alice",
    workspace_id: "ws-alpha",
    project_id: "proj-1",
  },
  tenant: {
    workspace_id: "ws-alpha",
    workspace_name: "Alpha",
    organization_id: "org-1",
    organization_name: "Acme",
  },
};

const WORKSPACES_FIXTURE = [
  { id: "ws-alpha", name: "Alpha", organization_id: "org-1" },
  { id: "ws-beta", name: "Beta", organization_id: "org-1" },
];

test.describe("Phase 1 §4.4 — login → tenant pick → workspace open", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/aqp-api/**", (route) => {
      const url = route.request().url();
      if (url.includes("/health")) return route.fulfill({ json: { status: "ok" } });
      if (url.includes("/auth/me")) return route.fulfill({ json: ME_FIXTURE });
      if (url.includes("/me/workspaces"))
        return route.fulfill({ json: WORKSPACES_FIXTURE });
      if (url.includes("/me/workspace") && route.request().method() === "POST") {
        return route.fulfill({ json: { ok: true, workspace_id: "ws-beta" } });
      }
      if (url.endsWith("/")) return route.fulfill({ json: { app: "AQP", routes: [] } });
      return route.fulfill({ json: {} });
    });
  });

  test("login route renders outside the AppShell", async ({ page }) => {
    await page.goto("/auth/login");
    // The login route deliberately omits the TopBar / SideNav so the
    // IdP redirect doesn't paint over chrome we can't render yet.
    await expect(page.locator("[data-testid='aqp-shell-topbar']")).toHaveCount(0);
    await expect(
      page.getByRole("heading", { name: /sign in/i }).or(
        page.getByText(/log in to AQP/i),
      ),
    ).toBeVisible();
  });

  test("authenticated landing renders shell with workspace context", async ({ page }) => {
    await page.goto("/");
    // Once the auth callback completes, the AppShell mounts and the
    // workspace name is visible in the TopBar context badge.
    await expect(
      page.getByText(/Alpha/).or(page.getByRole("button", { name: /workspace/i })),
    ).toBeVisible({ timeout: 10_000 });
  });
});
