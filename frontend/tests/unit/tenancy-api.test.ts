import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createOrg, deleteOrg, listOrgs, listTeams, listUsers } from "@/lib/api/tenancy";

describe("tenancy api wrapper", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("listOrgs hits GET /orgs without a query string", async () => {
    await listOrgs();
    const call = fetchMock.mock.calls[0];
    const url = String(call?.[0]);
    expect(url).toContain("/orgs");
    expect(url).not.toContain("?");
    expect((call?.[1] as RequestInit | undefined)?.method ?? "GET").toBe("GET");
  });

  it("listTeams encodes the org_id query when provided", async () => {
    await listTeams("acme");
    const call = fetchMock.mock.calls[0];
    const url = String(call?.[0]);
    expect(url).toContain("/teams");
    expect(url).toContain("org_id=acme");
  });

  it("createOrg posts the body as JSON with the right headers", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          id: "org-1",
          slug: "acme",
          name: "Acme",
          status: "active",
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    const created = await createOrg({ slug: "acme", name: "Acme", billing_email: "a@b.co" });
    expect(created.id).toBe("org-1");
    const call = fetchMock.mock.calls[0];
    const init = call?.[1] as RequestInit | undefined;
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ slug: "acme", name: "Acme", billing_email: "a@b.co" }));
    const headers = init?.headers as Record<string, string>;
    expect(headers["Content-Type"]).toBe("application/json");
  });

  it("deleteOrg issues a DELETE against /orgs/{id}", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await deleteOrg("org-1");
    const call = fetchMock.mock.calls[0];
    expect(String(call?.[0])).toContain("/orgs/org-1");
    const init = call?.[1] as RequestInit | undefined;
    expect(init?.method).toBe("DELETE");
  });

  it("listUsers does not attach a query string", async () => {
    await listUsers();
    const call = fetchMock.mock.calls[0];
    const url = String(call?.[0]);
    expect(url).toContain("/users");
    expect(url).not.toContain("?");
  });
});
