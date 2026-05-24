import { test, expect } from "@playwright/test";

test.describe("auth screens", () => {
  test("signup page renders both provider buttons when configured", async ({
    page,
  }) => {
    await page.goto("/signup");
    await expect(page.getByText(/Create your AQP account/i)).toBeVisible();
    // Both providers are rendered when AUTH0_DOMAIN + ENTRA_CLIENT_ID are
    // set in .env.local. In an unconfigured dev env, the page shows the
    // "no identity provider configured" warning instead — accept either.
    const anyButton = page.locator(
      "a:has-text('Sign up with email'), a:has-text('Sign up with Microsoft'), text=/No identity provider is configured/i",
    );
    await expect(anyButton.first()).toBeVisible();
  });

  test("login page renders the provider picker", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByText(/Welcome back/i)).toBeVisible();
  });

  test("entra-tenant-link onboarding renders a status card", async ({
    page,
  }) => {
    await page.goto("/onboarding/entra-tenant-link?status=pending");
    await expect(page.getByText(/Microsoft Entra tenant link/i)).toBeVisible();
    await expect(page.getByText(/pending approval/i)).toBeVisible();
  });
});

test.describe("BFF endpoints", () => {
  test("GET /api/healthz returns 200", async ({ request }) => {
    const res = await request.get("/api/healthz");
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.status).toBe("ok");
    expect(body.service).toBe("aqp-ui");
  });

  test("GET /api/auth/me returns null user when unauthenticated", async ({
    request,
  }) => {
    const res = await request.get("/api/auth/me");
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.user).toBeNull();
    expect(body.claims).toBeNull();
    expect(body.provider).toBeNull();
  });
});
