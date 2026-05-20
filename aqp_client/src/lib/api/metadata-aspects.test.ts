import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  describeMetadataEntity,
  listMetadataEntities,
  metadataAspectStats,
  metadataEntityHistory,
  metadataLineage,
} from "./metadata-aspects";

describe("metadata-aspects api wrapper", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({}), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("listMetadataEntities forwards query params and unwraps items", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          items: [
            {
              urn: "urn:aqp:dataset:prod:aqp_silver_alpha_vantage.daily_bars",
              entity_type: "dataset",
              created_at: "2026-01-01T00:00:00Z",
              updated_at: "2026-01-01T00:00:00Z",
              aspect_count: 3,
            },
          ],
          total: 1,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    const rows = await listMetadataEntities({
      entity_type: "dataset",
      search: "daily_bars",
      limit: 25,
      offset: 50,
    });
    expect(rows).toHaveLength(1);
    expect(rows[0]?.aspect_count).toBe(3);
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain("/metadata/aspects/entities");
    expect(url).toContain("entity_type=dataset");
    expect(url).toContain("search=daily_bars");
    expect(url).toContain("limit=25");
    expect(url).toContain("offset=50");
  });

  it("describeMetadataEntity URL-encodes the urn path segment", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          urn: "urn:aqp:mlmodel:prod:ridge.v1",
          entity_type: "mlmodel",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          aspects: {},
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    await describeMetadataEntity("urn:aqp:mlmodel:prod:ridge.v1");
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain(
      "/metadata/aspects/entities/urn%3Aaqp%3Amlmodel%3Aprod%3Aridge.v1",
    );
  });

  it("metadataEntityHistory encodes urn and includes optional aspect filter", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    await metadataEntityHistory("urn:aqp:dataset:prod:prices.daily", {
      aspect_name: "datasetProperties",
      limit: 120,
    });
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain(
      "/metadata/aspects/entities/urn%3Aaqp%3Adataset%3Aprod%3Aprices.daily/history",
    );
    expect(url).toContain("aspect_name=datasetProperties");
    expect(url).toContain("limit=120");
  });

  it("metadataLineage encodes urn and query params", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          entity: "urn:aqp:dataset:prod:prices.daily",
          upstream_edges: [],
          downstream_edges: [],
          depth: 2,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    await metadataLineage("urn:aqp:dataset:prod:prices.daily", {
      depth: 4,
      direction: "downstream",
    });
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain(
      "/metadata/aspects/lineage/urn%3Aaqp%3Adataset%3Aprod%3Aprices.daily",
    );
    expect(url).toContain("depth=4");
    expect(url).toContain("direction=downstream");
  });

  it("metadataAspectStats hits the stats endpoint", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          entity_count_by_type: { dataset: 2 },
          aspect_count_by_name: { datasetProperties: 4 },
          recent_writes: [],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    const stats = await metadataAspectStats();
    expect(stats.entity_count_by_type.dataset).toBe(2);
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain("/metadata/aspects/stats");
  });
});
