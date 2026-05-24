import { describe, expect, it, beforeEach, vi } from "vitest";

// Mock next/headers BEFORE importing the route handler.
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: () => undefined,
    set: () => {},
    delete: () => {},
  }),
}));

vi.mock("@/lib/auth/session", async () => {
  return {
    getSession: vi.fn(async () => null),
  };
});

vi.mock("@/lib/api/client", async () => {
  return {
    upstreamFetch: vi.fn(),
  };
});

import { POST as killSwitchHandler } from "./route";
import { getSession } from "@/lib/auth/session";
import { upstreamFetch } from "@/lib/api/client";

const mockedGetSession = vi.mocked(getSession);
const mockedUpstreamFetch = vi.mocked(upstreamFetch);

describe("POST /api/kill-switch", () => {
  beforeEach(() => {
    mockedGetSession.mockReset();
    mockedUpstreamFetch.mockReset();
  });

  it("rejects unauthenticated requests with 401", async () => {
    mockedGetSession.mockResolvedValue(null);
    const res = await killSwitchHandler();
    expect(res.status).toBe(401);
  });

  it("fans out to all six halt endpoints when authenticated", async () => {
    mockedGetSession.mockResolvedValue({
      provider: "auth0",
      user: { id: "u1", email: "x" },
      claims: {
        orgId: "o1",
        teamId: null,
        workspaceId: "w1",
        projectId: null,
        labId: null,
        mode: null,
        roles: [],
        resources: [],
        scopes: [],
      },
      accessToken: "t",
      accessTokenExpiresAt: Math.floor(Date.now() / 1000) + 3600,
    });
    mockedUpstreamFetch.mockResolvedValue(
      new Response("", { status: 200 }),
    );

    const res = await killSwitchHandler();
    expect(res.status).toBe(200);
    expect(mockedUpstreamFetch).toHaveBeenCalledTimes(6);
    const endpoints = mockedUpstreamFetch.mock.calls.map((args) => args[0]);
    expect(endpoints).toEqual(
      expect.arrayContaining([
        "/portfolio/kill_switch",
        "/agents/halt",
        "/paper/stop-all",
        "/bots/halt-all",
        "/rl/halt-all",
        "/workflows/halt",
      ]),
    );
  });
});
