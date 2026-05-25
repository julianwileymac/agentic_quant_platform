import { useQuery } from "@tanstack/react-query";
import { Database, Network, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { DataTable, type ColumnDef } from "@/components/common/DataTable";
import { EntityPicker } from "@/components/common/EntityPicker";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  listMetadataEntitiesPage,
  metadataAspectStats,
  type MetadataAspectStats,
  type MetadataEntitySummary,
} from "@/lib/api/metadata-aspects";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 50;

export function MetadataAspectsListRoute() {
  const navigate = useNavigate();
  const location = useLocation();
  const [search, setSearch] = useState("");
  const [entityType, setEntityType] = useState<string>("all");
  const [page, setPage] = useState(0);
  const [lineageUrn, setLineageUrn] = useState("");
  const debouncedSearch = useDebouncedValue(search, 250);
  const isLineageLaunch = location.pathname === "/metadata/aspects/lineage";
  const queryTab = new URLSearchParams(location.search).get("tab");

  const entityTypeFilter = entityType === "all" ? undefined : entityType;
  const listQuery = useQuery({
    queryKey: [
      "metadata-aspects",
      "entities",
      entityTypeFilter ?? "all",
      debouncedSearch,
      page,
    ],
    queryFn: () => {
      // Build the request payload conditionally so we never assign
      // ``undefined`` to fields the typed wrapper declares as required
      // strings (``exactOptionalPropertyTypes: true`` rejects that).
      const params: Parameters<typeof listMetadataEntitiesPage>[0] = {
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      };
      if (entityTypeFilter) params.entity_type = entityTypeFilter;
      if (debouncedSearch) params.search = debouncedSearch;
      return listMetadataEntitiesPage(params);
    },
  });
  const statsQuery = useQuery<MetadataAspectStats>({
    queryKey: ["metadata-aspects", "stats"],
    queryFn: metadataAspectStats,
    staleTime: 10_000,
  });

  const rows = listQuery.data?.items ?? [];
  const total = listQuery.data?.total ?? 0;

  const columns: ColumnDef<MetadataEntitySummary>[] = [
    {
      key: "urn",
      header: "URN",
      render: (row) => (
        <span className="truncate font-mono text-xs text-[var(--text-primary)]">
          {row.urn}
        </span>
      ),
    },
    {
      key: "entity_type",
      header: "Type",
      width: 180,
      render: (row) => <Badge variant="secondary">{row.entity_type}</Badge>,
    },
    {
      key: "aspect_count",
      header: "Aspect Count",
      width: 130,
      align: "right",
      render: (row) => (
        <span className="font-mono tabular-nums">{row.aspect_count}</span>
      ),
    },
    {
      key: "updated_at",
      header: "Updated",
      width: 190,
      render: (row) => (
        <span className="text-xs text-[var(--text-muted)]">
          {formatDateTime(row.updated_at)}
        </span>
      ),
    },
  ];

  const canPrev = page > 0;
  const canNext = (page + 1) * PAGE_SIZE < total;

  return (
    <PageContainer
      title="Metadata Aspects"
      subtitle="Browse MetadataEntity rows, inspect versioned aspects, and jump into lineage DAG views."
      extra={
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
          <Input
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(0);
            }}
            placeholder="Search URN substring"
            className="w-80 pl-7"
          />
        </div>
      }
    >
      <div className="flex h-full min-h-0 flex-col gap-3">
        <StatsStrip stats={statsQuery.data} highlighted={queryTab === "stats"} />

        <Card>
          <CardContent className="flex flex-wrap items-center gap-3 py-3">
            <label className="text-xs text-[var(--text-muted)]" htmlFor="entity-type-filter">
              Entity type
            </label>
            {/*
              AGENTS rule 29 — typed entity input. Backed by the
              `metadata_entity_types` cache category seeded by
              `MetadataPrefetcher._populate_metadata_entity_types`.
              `null` selection collapses to the "all types" filter so
              the listing still renders every kind by default.
            */}
            <div className="w-64">
              <EntityPicker
                kind="metadata_entity_types"
                value={entityType === "all" ? null : entityType}
                onChange={(next) => {
                  setEntityType(next ?? "all");
                  setPage(0);
                }}
                placeholder="All types"
                clearable
              />
            </div>
            <div className="ml-auto flex items-center gap-2">
              <Button
                variant={isLineageLaunch ? "secondary" : "outline"}
                size="sm"
                onClick={() => navigate("/metadata/aspects/lineage")}
                className="gap-2"
              >
                <Network className="h-3.5 w-3.5" />
                Open lineage launcher
              </Button>
              {isLineageLaunch ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => navigate("/metadata/aspects")}
                >
                  Back to list
                </Button>
              ) : null}
            </div>
          </CardContent>
        </Card>

        {isLineageLaunch ? (
          <Card>
            <CardHeader>
              <CardTitle>Lineage Explorer Launch</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap items-end gap-2">
              <div className="min-w-[360px] flex-1">
                <p className="mb-1 text-xs text-[var(--text-muted)]">Focal URN</p>
                {/*
                  AGENTS rule 29 — typed entity input. The previous
                  free-text Input + <datalist> combobox is replaced by
                  the shared <EntityPicker> backed by the
                  `metadata_entity_urns` cache category seeded by
                  `MetadataPrefetcher._populate_metadata_entity_urns`.
                  `allowCustom` stays OFF — `lineageUrn` is only ever
                  set from the picker's whitelist, which guarantees
                  the lineage route URL holds a known URN.
                */}
                <EntityPicker
                  kind="metadata_entity_urns"
                  value={lineageUrn || null}
                  onChange={(next) => setLineageUrn(next ?? "")}
                  placeholder="Select metadata URN..."
                  clearable
                />
              </div>
              <Button
                onClick={() =>
                  navigate(
                    `/metadata/aspects/lineage/${encodeURIComponent(
                      lineageUrn.trim(),
                    )}`,
                  )
                }
                disabled={!lineageUrn.trim()}
              >
                Open lineage graph
              </Button>
            </CardContent>
          </Card>
        ) : null}

        <Card className="min-h-0 flex-1">
          <CardContent className="h-full p-0">
            <DataTable<MetadataEntitySummary>
              rows={rows}
              columns={columns}
              rowKey={(row) => row.urn}
              onRowClick={(row) =>
                navigate(`/metadata/aspects/${encodeURIComponent(row.urn)}`)
              }
              emptyState={
                <div className="flex flex-col items-center gap-2 text-[var(--text-muted)]">
                  <Database className="h-7 w-7" />
                  <p className="text-sm">
                    {listQuery.isPending
                      ? "Loading metadata entities..."
                      : "No metadata entities match this filter."}
                  </p>
                </div>
              }
            />
          </CardContent>
        </Card>

        <div className="flex items-center justify-between">
          <span className="font-mono text-xs tabular-nums text-[var(--text-muted)]">
            Page {page + 1} · {rows.length} / {total}
          </span>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!canPrev}
              onClick={() => setPage((prev) => Math.max(0, prev - 1))}
            >
              Previous
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!canNext}
              onClick={() => setPage((prev) => prev + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      </div>
    </PageContainer>
  );
}

function StatsStrip({
  stats,
  highlighted,
}: {
  stats: MetadataAspectStats | undefined;
  highlighted: boolean;
}) {
  const entityEntries = Object.entries(stats?.entity_count_by_type ?? {}).sort(
    ([a], [b]) => a.localeCompare(b),
  );
  const aspectEntries = Object.entries(stats?.aspect_count_by_name ?? {}).sort(
    ([a], [b]) => a.localeCompare(b),
  );
  return (
    <div
      className={cn(
        "grid grid-cols-1 gap-3 md:grid-cols-3",
        highlighted && "rounded-md ring-1 ring-[var(--info-fg)]",
      )}
    >
      <Card>
        <CardHeader>
          <CardTitle>Entity Count By Type</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-xs">
          {entityEntries.length === 0 ? (
            <p className="text-[var(--text-muted)]">No entity rows yet.</p>
          ) : (
            entityEntries.slice(0, 8).map(([name, count]) => (
              <div key={name} className="flex items-center justify-between">
                <span>{name}</span>
                <span className="font-mono tabular-nums">{count}</span>
              </div>
            ))
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Aspect Count By Name</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-xs">
          {aspectEntries.length === 0 ? (
            <p className="text-[var(--text-muted)]">No aspect rows yet.</p>
          ) : (
            aspectEntries.slice(0, 8).map(([name, count]) => (
              <div key={name} className="flex items-center justify-between">
                <span className="truncate">{name}</span>
                <span className="font-mono tabular-nums">{count}</span>
              </div>
            ))
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Recent Writes</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-xs">
          {(stats?.recent_writes ?? []).slice(0, 6).map((row) => (
            <div key={`${row.urn}-${row.aspect_name}-${row.version}`}>
              <p className="truncate font-mono text-[10px] text-[var(--text-primary)]">
                {row.urn}
              </p>
              <p className="text-[10px] text-[var(--text-muted)]">
                {row.aspect_name} · v{row.version} · {formatDateTime(row.created_at)}
              </p>
            </div>
          ))}
          {(stats?.recent_writes ?? []).length === 0 ? (
            <p className="text-[var(--text-muted)]">No writes recorded.</p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [delayMs, value]);
  return debounced;
}

function formatDateTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "—";
  }
  return parsed.toLocaleString();
}
