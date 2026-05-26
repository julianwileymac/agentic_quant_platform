import { describe, expect, it } from "vitest";

import { parseWwwAuthenticate } from "@/lib/auth/useStepUp";

describe("parseWwwAuthenticate", () => {
  it("parses an RFC 9470 step-up challenge", () => {
    const header =
      'Bearer error="insufficient_user_authentication", error_description="MFA evidence stale", acr_values="mfa", max_age="180"';
    const parsed = parseWwwAuthenticate(header);
    expect(parsed).not.toBeNull();
    expect(parsed?.error).toBe("insufficient_user_authentication");
    expect(parsed?.acr_values).toBe("mfa");
    expect(parsed?.max_age).toBe(180);
  });

  it("returns null for non-error challenges", () => {
    expect(parseWwwAuthenticate("Bearer realm=\"aqp\"")).toBeNull();
  });

  it("returns null for missing or non-bearer headers", () => {
    expect(parseWwwAuthenticate(null)).toBeNull();
    expect(parseWwwAuthenticate("")).toBeNull();
    expect(parseWwwAuthenticate("Basic foo=bar")).toBeNull();
  });
});
