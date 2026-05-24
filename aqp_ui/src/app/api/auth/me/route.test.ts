import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: () => undefined,
    set: () => {},
    delete: () => {},
  }),
}));

vi.mock("@/lib/auth/session", () => ({
  getSession: vi.fn(),
}));

import { GET as meHandler } from "./route";
import { getSession } from "@/lib/auth/session";

const mockedGetSession = vi.mocked(getSession);

describe("GET /api/auth/me", () => {
  beforeEach(() => {
    mockedGetSession.mockReset();
  });

  it("returns null user / claims / provider when no session is present", async () => {
    mockedGetSession.mockResolvedValue(null);
    const res = await meHandler();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.user).toBeNull();
    expect(body.claims).toBeNull();
    expect(body.provider).toBeNull();
  });

  it("returns user + claims + provider but NEVER the access token", async () => {
    mockedGetSession.mockResolvedValue({
      provider: "auth0",
      user: { id: "u1", email: "u@example.com", name: "User One" },
      claims: {
        orgId: "org_1",
        teamId: null,
        workspaceId: "ws_1",
        projectId: null,
        labId: null,
        mode: "paper",
        roles: ["editor"],
        resources: [],
        scopes: ["paper:start"],
      },
      accessToken: "redacted-access-token-should-NEVER-leak",
      accessTokenExpiresAt: Math.floor(Date.now() / 1000) + 3600,
    });

    const res = await meHandler();
    const body = await res.json();
    expect(body.provider).toBe("auth0");
    expect(body.user.email).toBe("u@example.com");
    expect(body.claims.orgId).toBe("org_1");
    expect(body.claims.scopes).toEqual(["paper:start"]);
    // AGENTS rule 4 + aqp-management-engine.mdc: never return the token.
    expect(JSON.stringify(body)).not.toContain("redacted-access-token-should-NEVER-leak");
  });
});
