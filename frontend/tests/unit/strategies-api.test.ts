import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { strategiesApi } from "@/lib/api/strategies";

describe("strategiesApi", () => {
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

  it("posts a backtest request to the per-strategy endpoint", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ task_id: "tsk-123" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const res = await strategiesApi.runBacktest("mean-rev");
    expect(res.task_id).toBe("tsk-123");
    const call = fetchMock.mock.calls[0];
    expect(call?.[0]).toContain("/strategies/mean-rev/backtest");
    expect((call?.[1] as RequestInit | undefined)?.method).toBe("POST");
  });

  it("encodes special characters in the strategy ref", async () => {
    await strategiesApi.get("ns:my-strat");
    const call = fetchMock.mock.calls[0];
    // encodeURIComponent turns ":" into %3A
    expect(call?.[0]).toContain("/strategies/ns%3Amy-strat");
  });

  it("attaches a query string when list is called with params", async () => {
    await strategiesApi.list({ tag: "alpha", limit: 25 });
    const call = fetchMock.mock.calls[0];
    const url = String(call?.[0]);
    expect(url).toContain("tag=alpha");
    expect(url).toContain("limit=25");
  });
});
