import { describe, expect, it } from "vitest";

import { apiUrl, wsUrl } from "@/lib/api/config";

describe("api/config helpers", () => {
  it("apiUrl prepends the base URL when given a relative path", () => {
    expect(apiUrl("/health")).toContain("/health");
  });

  it("apiUrl returns absolute URLs unchanged", () => {
    expect(apiUrl("https://example.com/x")).toBe("https://example.com/x");
  });

  it("wsUrl produces ws:// from http://", () => {
    expect(wsUrl("/chat/stream/abc")).toMatch(/^wss?:\/\/.+\/chat\/stream\/abc$/);
  });
});
