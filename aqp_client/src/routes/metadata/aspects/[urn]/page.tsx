import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { CodeEditor } from "@/components/common/CodeEditor";
import { DataTable, type ColumnDef } from "@/components/common/DataTable";
import { MetadataLineageGraph } from "@/components/metadata/MetadataLineageGraph";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  describeMetadataEntity,
  metadataEntityHistory,
  metadataLineage,
  type EntityAspectRow,
} from "@/lib/api/metadata-aspects";

export function MetadataAspectDetailRoute() {
  const { urn: rawUrn = "" } = useParams<{ urn: string }>();
  const urn = safeDecode(rawUrn);
  const [selectedAspectName, setSelectedAspectName] = useState<string | null>(
    null,
  );
  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(
    null,
  );

  const entityQuery = useQuery({
    queryKey: ["metadata-aspects", "entity", urn],
    queryFn: () => describeMetadataEntity(urn),
    enabled: urn.length > 0,
  });
  const historyQuery = useQuery({
    queryKey: ["metadata-aspects", "history", urn],
    queryFn: () =>
      metadataEntityHistory(urn, {
        limit: 300,
      }),
    enabled: urn.length > 0,
  });
  const lineageQuery = useQuery({
    queryKey: ["metadata-aspects", "lineage-mini", urn],
    queryFn: () =>
      metadataLineage(urn, {
        depth: 2,
        direction: "both",
      }),
    enabled: urn.length > 0,
  });

  const aspectNames = useMemo(
    () => Object.keys(entityQuery.data?.aspects ?? {}).sort(),
    [entityQuery.data?.aspects],
  );
  useEffect(() => {
    if (!selectedAspectName && aspectNames.length > 0) {
      setSelectedAspectName(aspectNames[0] ?? null);
    }
  }, [aspectNames, selectedAspectName]);

  const historyRows = useMemo(
    () =>
      [...(historyQuery.data ?? [])].sort((a, b) => {
        const byTime =
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        if (byTime !== 0) {
          return byTime;
        }
        return b.version - a.version;
      }),
    [historyQuery.data],
  );
  useEffect(() => {
    if (!selectedHistoryId && historyRows.length > 0) {
      setSelectedHistoryId(historyRows[0]?.id ?? null);
    }
  }, [historyRows, selectedHistoryId]);

  const selectedAspect =
    selectedAspectName && entityQuery.data
      ? entityQuery.data.aspects[selectedAspectName]
      : undefined;
  const selectedHistory =
    historyRows.find((row) => row.id === selectedHistoryId) ??
    historyRows[0] ??
    null;
  const selectedHistoryDiff = selectedHistory
    ? buildVersionDiff(selectedHistory, historyRows)
    : {};

  const historyColumns: ColumnDef<EntityAspectRow>[] = [
    {
      key: "aspect_name",
      header: "Aspect",
      render: (row) => <Badge variant="secondary">{row.aspect_name}</Badge>,
    },
    {
      key: "version",
      header: "Version",
      width: 90,
      align: "right",
      render: (row) => <span className="font-mono tabular-nums">v{row.version}</span>,
    },
    {
      key: "created_at",
      header: "Created",
      width: 190,
      render: (row) => (
        <span className="text-xs text-[var(--text-muted)]">
          {formatDateTime(row.created_at)}
        </span>
      ),
    },
    {
      key: "created_by",
      header: "Created By",
      width: 140,
      render: (row) => (
        <span className="truncate text-xs text-[var(--text-muted)]">
          {row.created_by ?? "unknown"}
        </span>
      ),
    },
  ];

  return (
    <PageContainer
      title="Metadata Entity"
      subtitle={urn}
      extra={
        <Button asChild variant="outline" size="sm">
          <Link to={`/metadata/aspects/lineage/${encodeURIComponent(urn)}`}>
            Open lineage graph
          </Link>
        </Button>
      }
    >
      <div className="flex h-full min-h-0 flex-col gap-3">
        <Card>
          <CardContent className="grid gap-2 py-4 md:grid-cols-4">
            <MetaCell
              label="Entity Type"
              value={entityQuery.data?.entity_type ?? "—"}
            />
            <MetaCell
              label="Created"
              value={formatDateTime(entityQuery.data?.created_at)}
            />
            <MetaCell
              label="Updated"
              value={formatDateTime(entityQuery.data?.updated_at)}
            />
            <MetaCell
              label="Current Aspects"
              value={String(aspectNames.length)}
              mono
            />
          </CardContent>
        </Card>

        <Tabs defaultValue="aspects" className="flex min-h-0 flex-1 flex-col">
          <TabsList className="w-full justify-start">
            <TabsTrigger value="aspects">Aspects</TabsTrigger>
            <TabsTrigger value="history">History</TabsTrigger>
            <TabsTrigger value="lineage">Lineage</TabsTrigger>
          </TabsList>

          <TabsContent value="aspects" className="min-h-0 flex-1">
            <div className="grid h-full min-h-0 gap-3 md:grid-cols-[280px_1fr]">
              <Card className="min-h-0">
                <CardHeader>
                  <CardTitle>Current aspect names</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 overflow-auto">
                  {aspectNames.map((name) => (
                    <button
                      type="button"
                      key={name}
                      onClick={() => setSelectedAspectName(name)}
                      className={`flex w-full items-center justify-between rounded-md border px-2 py-1.5 text-left text-sm ${
                        selectedAspectName === name
                          ? "border-[var(--info-fg)] bg-[var(--info-bg)]"
                          : "border-[var(--border-default)]"
                      }`}
                    >
                      <span className="truncate font-mono text-xs">{name}</span>
                      <span className="font-mono tabular-nums text-[10px]">
                        v{entityQuery.data?.aspects[name]?.version ?? "?"}
                      </span>
                    </button>
                  ))}
                  {aspectNames.length === 0 ? (
                    <p className="text-sm text-[var(--text-muted)]">
                      {entityQuery.isPending
                        ? "Loading aspects..."
                        : "No current aspects found."}
                    </p>
                  ) : null}
                </CardContent>
              </Card>
              <Card className="min-h-0">
                <CardHeader>
                  <CardTitle>
                    {selectedAspectName
                      ? `Latest payload: ${selectedAspectName}`
                      : "Latest payload"}
                  </CardTitle>
                </CardHeader>
                <CardContent className="h-full min-h-0">
                  <CodeEditor
                    language="json"
                    readOnly
                    value={toPrettyJson(selectedAspect?.payload ?? {})}
                  />
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="history" className="min-h-0 flex-1">
            <div className="grid h-full min-h-0 gap-3 md:grid-cols-[1.2fr_1fr]">
              <Card className="min-h-0">
                <CardHeader>
                  <CardTitle>Version history</CardTitle>
                </CardHeader>
                <CardContent className="h-full p-0">
                  <DataTable<EntityAspectRow>
                    rows={historyRows}
                    columns={historyColumns}
                    rowKey={(row) => row.id}
                    onRowClick={(row) => setSelectedHistoryId(row.id)}
                    emptyState={
                      historyQuery.isPending
                        ? "Loading aspect history..."
                        : "No aspect history found."
                    }
                  />
                </CardContent>
              </Card>
              <div className="grid min-h-0 gap-3">
                <Card className="min-h-0">
                  <CardHeader>
                    <CardTitle>Selected payload</CardTitle>
                  </CardHeader>
                  <CardContent className="h-full min-h-0">
                    <CodeEditor
                      language="json"
                      readOnly
                      value={toPrettyJson(selectedHistory?.payload ?? {})}
                    />
                  </CardContent>
                </Card>
                <Card className="min-h-0">
                  <CardHeader>
                    <CardTitle>Version diff summary</CardTitle>
                  </CardHeader>
                  <CardContent className="h-full min-h-0">
                    <CodeEditor
                      language="json"
                      readOnly
                      value={toPrettyJson(selectedHistoryDiff)}
                    />
                  </CardContent>
                </Card>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="lineage" className="min-h-0 flex-1">
            <MetadataLineageGraph lineage={lineageQuery.data ?? null} compact />
          </TabsContent>
        </Tabs>
      </div>
    </PageContainer>
  );
}

function MetaCell({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-md border border-[var(--border-default)] p-2">
      <p className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </p>
      <p className={mono ? "font-mono tabular-nums text-sm" : "text-sm"}>
        {value}
      </p>
    </div>
  );
}

function buildVersionDiff(
  current: EntityAspectRow,
  rows: EntityAspectRow[],
): Record<string, unknown> {
  const previous = rows
    .filter(
      (row) =>
        row.aspect_name === current.aspect_name && row.version < current.version,
    )
    .sort((a, b) => b.version - a.version)[0];
  if (!previous) {
    return {
      aspect_name: current.aspect_name,
      current_version: current.version,
      status: "initial_version",
    };
  }
  const before = asRecord(previous.payload);
  const after = asRecord(current.payload);
  const beforeKeys = new Set(Object.keys(before));
  const afterKeys = new Set(Object.keys(after));
  const added = Array.from(afterKeys).filter((key) => !beforeKeys.has(key));
  const removed = Array.from(beforeKeys).filter((key) => !afterKeys.has(key));
  const changed: Record<string, { before: unknown; after: unknown }> = {};
  for (const key of afterKeys) {
    if (!beforeKeys.has(key)) {
      continue;
    }
    if (JSON.stringify(before[key]) === JSON.stringify(after[key])) {
      continue;
    }
    changed[key] = { before: before[key], after: after[key] };
  }
  return {
    aspect_name: current.aspect_name,
    current_version: current.version,
    previous_version: previous.version,
    added_keys: added,
    removed_keys: removed,
    changed,
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

function toPrettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function formatDateTime(value: string | undefined): string {
  if (!value) {
    return "—";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "—";
  }
  return parsed.toLocaleString();
}

function safeDecode(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}
