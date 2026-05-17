import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ingestWizardApi } from "@/lib/api/ingestWizard";

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("ingestWizardApi", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(json({}));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requests bootstrap from the orchestration endpoint", async () => {
    fetchMock.mockResolvedValueOnce(json({ generated_at: "", sources: [] }));
    await ingestWizardApi.bootstrap();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/ingest/wizard/bootstrap");
    expect(init.method).toBe("GET");
  });

  it("posts preflight payload to /ingest/wizard/preflight", async () => {
    fetchMock.mockResolvedValueOnce(json({ generated_at: "", ok: true, checks: [] }));
    await ingestWizardApi.preflight({
      source_name: "alpha_vantage",
      run_source_probe: true,
    });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/ingest/wizard/preflight");
    expect(init.method).toBe("POST");
    expect(String(init.body)).toContain("alpha_vantage");
  });

  it("dispatches preset and template runs on existing execution endpoints", async () => {
    fetchMock.mockResolvedValueOnce(json({ task_id: "preset-1", preset: "p", status: "queued" }));
    fetchMock.mockResolvedValueOnce(
      json({
        template_id: "t",
        endpoint: "/pipelines/templates/t/run",
        run_kind: "alpha",
        task_id: "tmpl-1",
        stream_url: "/chat/stream/tmpl-1",
      }),
    );

    await ingestWizardApi.launchPreset("equity_universe_sp500_daily", {
      symbols: ["AAPL"],
      extra_kwargs: { interval: "1d" },
    });
    await ingestWizardApi.launchTemplate("alpha-vantage-endpoints", {
      overrides: { interval: "5min" },
    });

    const firstCall = fetchMock.mock.calls[0] as [string, RequestInit];
    const secondCall = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(firstCall[0]).toContain("/dataset-presets/equity_universe_sp500_daily/ingest");
    expect(firstCall[1].method).toBe("POST");
    expect(String(firstCall[1].body)).toContain("AAPL");
    expect(secondCall[0]).toContain("/pipelines/templates/alpha-vantage-endpoints/run");
    expect(secondCall[1].method).toBe("POST");
    expect(String(secondCall[1].body)).toContain("\"dry_run\":false");
  });

  it("dispatches source dataset creation on /sources/{name}/datasets", async () => {
    fetchMock.mockResolvedValueOnce(
      json({
        dataset_id: "d",
        manifest_id: "m",
        iceberg_identifier: "aqp.s",
        run_id: "task-1",
        status: "created",
      }),
    );
    await ingestWizardApi.launchSource("alpha_vantage", {
      name: "dataset",
      namespace: "aqp_bronze_self_service",
      table: "dataset",
      source_kwargs: {},
      run_now: true,
    });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/sources/alpha_vantage/datasets");
    expect(init.method).toBe("POST");
    expect(String(init.body)).toContain("\"run_now\":true");
  });
});
