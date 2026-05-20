import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IngestWizard } from "@/components/data/ingest/IngestWizard";

const BOOTSTRAP_PAYLOAD = {
  generated_at: "2026-05-17T00:00:00Z",
  sources: [
    {
      name: "alpha_vantage",
      display_name: "Alpha Vantage",
      description: "Market data source",
      kind: "alpha_vantage",
      enabled: true,
      tags: ["market", "equities"],
    },
  ],
  source_wizards: [
    {
      source_key: "alpha_vantage",
      display_name: "Alpha Vantage",
      description: "Wizard",
      documentation_url: null,
      steps: [{ id: "intro", label: "Intro", prompt: "hello", optional: false, fields: [] }],
    },
  ],
  dataset_presets: [
    {
      name: "equity_universe_sp500_daily",
      description: "S&P500 daily bars",
      namespace: "aqp_silver_equity",
      table: "sp500_daily",
      source_kind: "alpha_vantage",
      ingestion_task: "dataset_preset",
      tags: ["equity"],
      setup_steps: [],
      required_config: {},
    },
  ],
  loading_templates: [
    {
      id: "alpha-vantage-endpoints",
      title: "Alpha Vantage endpoints",
      description: "Template",
      endpoint: "/pipelines/templates/alpha-vantage-endpoints/run",
      run_kind: "alpha_vantage_endpoints",
      default_payload: {},
      fields: [],
    },
  ],
  service_health: {
    ok: true,
    services: {},
  },
  compute_status: {
    default_backend: "auto",
  },
  queue: {
    workers_seen: 1,
    active: 0,
    reserved: 0,
    scheduled: 0,
    queued: 0,
    total: 0,
    ingestion_active: 0,
    ingestion_reserved: 0,
    ingestion_scheduled: 0,
    ingestion_queued: 0,
  },
};

const PREFLIGHT_PAYLOAD = {
  generated_at: "2026-05-17T00:00:05Z",
  ok: true,
  checks: [
    {
      check_id: "service-health",
      ok: true,
      severity: "info",
      message: "ok",
      details: {},
    },
  ],
  queue: {
    workers_seen: 1,
    active: 0,
    reserved: 0,
    scheduled: 0,
    queued: 0,
    total: 0,
    ingestion_active: 0,
    ingestion_reserved: 0,
    ingestion_scheduled: 0,
    ingestion_queued: 0,
  },
};

const RECOMMEND_PAYLOAD = {
  generated_at: "2026-05-17T00:01:00Z",
  queue: {
    workers_seen: 2,
    active: 6,
    reserved: 4,
    scheduled: 4,
    queued: 8,
    total: 14,
    ingestion_active: 6,
    ingestion_reserved: 4,
    ingestion_scheduled: 4,
    ingestion_queued: 8,
  },
  compute: {
    requested_backend: "auto",
    backend: "dask",
    chunk_rows: 50000,
    max_concurrent_pipelines: 2,
    dask_address: "tcp://dask:8786",
    ray_address: null,
    rationale: ["Estimated rows: 1,000,000"],
  },
  queue_strategy: {
    pressure: "high",
    recommended_parallel_runs: 1,
    recommended_spacing_seconds: 60,
    rationale: ["High queue pressure"],
  },
  rate_limit: {
    source_name: "alpha_vantage",
    provider_rpm: 10,
    provider_daily: 500,
    desired_rpm: 20,
    recommended_rpm: 5,
    rationale: ["Provider limit: 10 RPM"],
  },
  advisories: [
    {
      severity: "warn",
      message: "Queue pressure is high; reduce dispatch rate and parallelism.",
      details: {},
    },
  ],
};

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function renderWizard() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <IngestWizard />
    </QueryClientProvider>,
  );
}

describe("<IngestWizard />", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/ingest/wizard/bootstrap")) return Promise.resolve(json(BOOTSTRAP_PAYLOAD));
      if (url.includes("/ingest/wizard/preflight")) return Promise.resolve(json(PREFLIGHT_PAYLOAD));
      if (url.includes("/ingest/wizard/recommend")) return Promise.resolve(json(RECOMMEND_PAYLOAD));
      if (url.includes("/sources/")) return Promise.resolve(json({ run_id: "task-123" }));
      const method = (init?.method ?? "GET").toUpperCase();
      return Promise.resolve(json({ detail: `Unhandled ${method} ${url}` }, 404));
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("blocks moving past Test step until preflight runs", async () => {
    const user = userEvent.setup();
    renderWizard();

    await screen.findByText(/Dataset identification/i);
    await user.click(screen.getByRole("button", { name: /^Next$/i }));
    await user.click(screen.getByRole("button", { name: /^Next$/i }));

    expect(screen.getByText(/Preflight and validation/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Next$/i }));
    expect(screen.getByText(/Preflight and validation/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^Run preflight$/i }));
    await screen.findByRole("heading", { name: /^Checks/i });
    await user.click(screen.getByRole("button", { name: /^Next$/i }));

    expect(await screen.findByText(/Data-layer integration/i)).toBeInTheDocument();
  });

  it("renders recommendation details on the Coordinate step", async () => {
    const user = userEvent.setup();
    renderWizard();
    await screen.findByText(/Dataset identification/i);

    await user.click(screen.getByRole("button", { name: /Coordinate/i }));
    expect(screen.getByText(/Run coordination/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Get recommendation/i }));
    await waitFor(() => {
      expect(screen.getByText(/queue pressure: high/i)).toBeInTheDocument();
      expect(screen.getByText(/compute backend/i)).toBeInTheDocument();
      expect(screen.getByText(/^dask$/i, { selector: "dd" })).toBeInTheDocument();
      expect(
        screen.getByText(/Queue pressure is high; reduce dispatch rate and parallelism/i),
      ).toBeInTheDocument();
    });
  });
});
