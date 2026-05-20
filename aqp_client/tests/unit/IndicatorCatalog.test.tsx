import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { IndicatorCatalogRoute } from "@/routes/data/indicators/page";

function renderRoute() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <IndicatorCatalogRoute />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("<IndicatorCatalogRoute />", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify([
          {
            name: "sma",
            category: "trend",
            formula: "SUM(close, n) / n",
            inputs: ["close"],
            output: "sma_n",
            tags: ["trend", "moving-average"],
          },
          {
            name: "rsi",
            category: "momentum",
            formula: "100 - 100/(1+RS)",
            inputs: ["close"],
            output: "rsi_n",
            tags: ["momentum"],
          },
        ]),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the page header", async () => {
    renderRoute();
    expect(await screen.findByRole("heading", { name: /^Indicator Catalog$/ })).toBeInTheDocument();
  });
});
