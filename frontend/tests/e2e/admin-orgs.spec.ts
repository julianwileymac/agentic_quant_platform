import { expect, test } from "@playwright/test";

const ORGS = [
  {
    id: "org-1",
    slug: "acme",
    name: "Acme",
    status: "active",
    billing_email: "billing@acme.co",
    created_at: "2025-01-01T00:00:00Z",
  },
  {
    id: "org-2",
    slug: "globex",
    name: "Globex",
    status: "active",
    billing_email: "billing@globex.co",
    created_at: "2025-01-02T00:00:00Z",
  },
];

test.describe("Phase 5 — Organizations admin", () => {
  test("lists, creates, and friction-deletes an org", async ({ page }) => {
    let orgs = [...ORGS];
    let lastCreated: { slug?: string; name?: string; billing_email?: string | null } | null = null;
    let lastDeletedId: string | null = null;

    await page.route("**/aqp-api/**", async (route) => {
      const url = route.request().url();
      const method = route.request().method();

      if (url.includes("/health")) {
        return route.fulfill({ json: { status: "ok" } });
      }
      if (url.endsWith("/orgs") && method === "GET") {
        return route.fulfill({ json: orgs });
      }
      if (url.endsWith("/orgs") && method === "POST") {
        const body = await route.request().postDataJSON();
        lastCreated = body;
        const created = {
          id: "org-created",
          slug: body.slug,
          name: body.name,
          billing_email: body.billing_email,
          status: "active",
          created_at: "2025-05-01T00:00:00Z",
        };
        orgs = [...orgs, created];
        return route.fulfill({ json: created });
      }
      const deleteMatch = url.match(/\/orgs\/([^/?]+)$/);
      if (deleteMatch && method === "DELETE") {
        lastDeletedId = deleteMatch[1] ?? null;
        orgs = orgs.filter((o) => o.id !== lastDeletedId);
        return route.fulfill({ status: 204, body: "" });
      }
      if (url.endsWith("/")) {
        return route.fulfill({ json: { app: "AQP", routes: [] } });
      }
      return route.fulfill({ json: {} });
    });

    await page.goto("/admin/orgs");
    await expect(page.getByRole("heading", { name: /^Organizations$/ })).toBeVisible();

    await expect(page.getByText("acme")).toBeVisible();
    await expect(page.getByText("globex")).toBeVisible();

    // Create.
    await page.getByRole("button", { name: /^New$/ }).click();
    await page.getByLabel("Slug").fill("initech");
    await page.getByLabel("Name").fill("Initech");
    await page.getByLabel(/Billing email/i).fill("ops@initech.co");
    await page.getByRole("button", { name: /Create org/i }).click();

    await expect(page.getByText("initech")).toBeVisible();
    expect(lastCreated).toEqual({
      slug: "initech",
      name: "Initech",
      billing_email: "ops@initech.co",
    });

    // Friction-gated delete on `acme`.
    const acmeRow = page.locator('[role="row"]').filter({ hasText: "acme" }).first();
    await acmeRow.getByRole("button", { name: /^Delete$/ }).click();

    const dialog = page.getByRole("alertdialog");
    await expect(dialog.getByText(/Delete org acme/i)).toBeVisible();

    const submit = dialog.getByRole("button", { name: /^Delete$/ });
    await expect(submit).toBeDisabled();
    await dialog.getByLabel(/Type/i).fill("acme");
    await expect(submit).toBeEnabled();
    await submit.click();

    await expect(page.locator('[role="row"]').filter({ hasText: "acme" })).toHaveCount(0);
    expect(lastDeletedId).toBe("org-1");
  });
});
