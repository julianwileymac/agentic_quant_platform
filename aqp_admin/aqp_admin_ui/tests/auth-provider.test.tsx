/**
 * Tests for the dual MSAL/Auth0 detection logic.
 */
import { describe, expect, it, vi } from "vitest";

vi.mock("@azure/msal-browser", () => ({}));
vi.mock("@auth0/auth0-spa-js", () => ({}));

import { detectProvider } from "@/lib/auth/AuthProvider";

describe("detectProvider", () => {
  it("returns 'none' when no IdP env vars are set", () => {
    vi.stubEnv("VITE_MSAL_TENANT_ID", "");
    vi.stubEnv("VITE_MSAL_CLIENT_ID", "");
    vi.stubEnv("VITE_AUTH0_DOMAIN", "");
    vi.stubEnv("VITE_AUTH0_CLIENT_ID", "");
    expect(detectProvider()).toBe("none");
    vi.unstubAllEnvs();
  });

  it("prefers MSAL when Entra env vars are present", () => {
    vi.stubEnv("VITE_MSAL_TENANT_ID", "tenant-uuid");
    vi.stubEnv("VITE_MSAL_CLIENT_ID", "client-id");
    vi.stubEnv("VITE_AUTH0_DOMAIN", "aqp.us.auth0.com");
    vi.stubEnv("VITE_AUTH0_CLIENT_ID", "abc");
    expect(detectProvider()).toBe("msal");
    vi.unstubAllEnvs();
  });

  it("falls back to Auth0 when only Auth0 is configured", () => {
    vi.stubEnv("VITE_MSAL_TENANT_ID", "");
    vi.stubEnv("VITE_MSAL_CLIENT_ID", "");
    vi.stubEnv("VITE_AUTH0_DOMAIN", "aqp.us.auth0.com");
    vi.stubEnv("VITE_AUTH0_CLIENT_ID", "abc");
    expect(detectProvider()).toBe("auth0");
    vi.unstubAllEnvs();
  });
});
