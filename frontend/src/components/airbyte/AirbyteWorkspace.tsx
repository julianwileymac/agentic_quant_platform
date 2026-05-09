import { Activity, FlaskConical, Network, Play, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { CodeEditor } from "@/components/common/CodeEditor";
import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import {
  AirbyteApi,
  type AirbyteConnection,
  type AirbyteConnector,
  type AirbyteRun,
} from "@/lib/api/airbyte";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { formatTime } from "@/lib/utils";

export type AirbyteView = "overview" | "connectors" | "builder" | "runs";

interface AirbyteHealthPayload {
  ok: boolean;
  enabled?: boolean;
  base_url?: string;
  airbyte?: { reachable?: boolean; detail?: string; available?: boolean; error?: string };
}

interface AirbyteSummary {
  total?: number;
  by_kind?: Record<string, number>;
  by_runtime?: Record<string, number>;
}

interface Props {
  view: AirbyteView;
}

const TITLE_FOR: Record<AirbyteView, string> = {
  overview: "Airbyte",
  connectors: "Airbyte Connectors",
  builder: "Airbyte Builder",
  runs: "Airbyte Runs",
};

/**
 * Hybrid Airbyte control plane. View-prop driven so all four nav routes
 * (`/airbyte/{,connectors,builder,runs}`) render this single component.
 */
export function AirbyteWorkspace({ view }: Props) {
  const [selectedConnector, setSelectedConnector] = useState("alpha-vantage");
  const [configText, setConfigText] = useState("{}");

  const health = useApiQuery<AirbyteHealthPayload>({
    queryKey: ["airbyte", "health"],
    path: "/airbyte/health",
    staleTime: 30_000,
  });
  const summary = useApiQuery<AirbyteSummary>({
    queryKey: ["airbyte", "summary"],
    path: "/airbyte/connectors/summary",
    staleTime: 60_000,
  });
  const connectors = useApiQuery<AirbyteConnector[]>({
    queryKey: ["airbyte", "connectors"],
    path: "/airbyte/connectors",
    staleTime: 60_000,
    select: (raw) => (Array.isArray(raw) ? (raw as AirbyteConnector[]) : []),
  });
  const connections = useApiQuery<AirbyteConnection[]>({
    queryKey: ["airbyte", "connections"],
    path: "/airbyte/connections",
    staleTime: 30_000,
    select: (raw) => (Array.isArray(raw) ? (raw as AirbyteConnection[]) : []),
  });
  const runs = useApiQuery<AirbyteRun[]>({
    queryKey: ["airbyte", "runs"],
    path: "/airbyte/runs",
    staleTime: 15_000,
    select: (raw) => (Array.isArray(raw) ? (raw as AirbyteRun[]) : []),
  });

  const connectorOptions = useMemo(
    () =>
      (connectors.data ?? [])
        .filter((c) => c.kind === "source")
        .map((c) => ({ value: c.id, label: c.name })),
    [connectors.data],
  );

  const queueDiscover = async () => {
    try {
      const cfg = parseConfig(configText);
      const task = await AirbyteApi.discover(selectedConnector, cfg);
      toast.success(`Discovery queued: ${task.task_id}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    }
  };

  const queueDryRun = async () => {
    try {
      const cfg = parseConfig(configText);
      const task = await AirbyteApi.embeddedRead(selectedConnector, cfg);
      toast.success(`Embedded dry-run queued: ${task.task_id}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    }
  };

  const queueSync = async (connectionId: string) => {
    try {
      const task = await AirbyteApi.sync(connectionId);
      toast.success(`Sync queued: ${task.task_id}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    }
  };

  const overviewMetrics: Metric[] = [
    {
      label: "Health",
      value: null,
      hint: (
        <Badge variant={health.data?.ok ? "positive" : "secondary"}>
          {health.data?.ok ? "ok" : String(health.data?.ok ?? "unknown")}
        </Badge>
      ),
    },
    { label: "Connectors", value: summary.data?.total ?? 0, kind: "integer", digits: 0, tone: "neutral" },
    { label: "Connections", value: connections.data?.length ?? 0, kind: "integer", digits: 0, tone: "neutral" },
    { label: "Recent runs", value: runs.data?.length ?? 0, kind: "integer", digits: 0, tone: "neutral" },
  ];

  return (
    <PageContainer
      title={TITLE_FOR[view]}
      subtitle="Hybrid Airbyte control plane for production syncs and embedded connector development."
    >
      {view === "overview" ? (
        <div className="flex flex-col gap-4">
          <MetricsGrid metrics={overviewMetrics} columns={4} />
          {health.data?.airbyte?.detail ? (
            <p className="text-xs text-[var(--text-secondary)]">{health.data.airbyte.detail}</p>
          ) : null}
          <ConnectionsCard
            rows={connections.data ?? []}
            loading={connections.isPending}
            onSync={queueSync}
          />
        </div>
      ) : null}

      {view === "connectors" ? (
        <Card className="h-[calc(100vh-180px)]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Network className="h-4 w-4" /> Connector catalog
            </CardTitle>
          </CardHeader>
          <CardContent className="h-full p-0">
            <ConnectorsTable rows={connectors.data ?? []} loading={connectors.isPending} />
          </CardContent>
        </Card>
      ) : null}

      {view === "builder" ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FlaskConical className="h-4 w-4" /> Connector development + test runs
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="connector">Source connector</Label>
              <select
                id="connector"
                value={selectedConnector}
                onChange={(e) => setSelectedConnector(e.target.value)}
                className="h-9 max-w-md rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm font-mono"
              >
                {connectorOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <Label>Config JSON</Label>
              <div className="h-56 overflow-hidden rounded-md">
                <CodeEditor language="json" value={configText} onChange={setConfigText} />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" onClick={queueDiscover} className="gap-2">
                <Search className="h-4 w-4" /> Discover streams
              </Button>
              <Button onClick={queueDryRun} className="gap-2">
                <Play className="h-4 w-4" /> Embedded dry-run
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {view === "runs" ? (
        <Card className="h-[calc(100vh-180px)]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-4 w-4" /> Sync runs
            </CardTitle>
          </CardHeader>
          <CardContent className="h-full p-0">
            <RunsTable rows={runs.data ?? []} loading={runs.isPending} />
          </CardContent>
        </Card>
      ) : null}
    </PageContainer>
  );
}

function ConnectionsCard({
  rows,
  loading,
  onSync,
}: {
  rows: AirbyteConnection[];
  loading: boolean;
  onSync: (id: string) => void;
}) {
  const columns: ColumnDef<AirbyteConnection>[] = [
    { key: "name", header: "Name", render: (r) => <span className="font-mono">{r.name}</span> },
    {
      key: "source_connector_id",
      header: "Source",
      render: (r) => <span className="text-xs">{r.source_connector_id}</span>,
    },
    {
      key: "destination_connector_id",
      header: "Destination",
      render: (r) => <span className="text-xs">{r.destination_connector_id}</span>,
    },
    {
      key: "last_sync_status",
      header: "Status",
      width: 130,
      render: (r) => <Badge variant="secondary">{r.last_sync_status ?? "never"}</Badge>,
    },
    {
      key: "actions",
      header: "Actions",
      width: 130,
      render: (r) => (
        <Button
          variant="ghost"
          size="sm"
          disabled={!r.airbyte_connection_id}
          onClick={() => onSync(r.id)}
          className="gap-1"
        >
          <Play className="h-3.5 w-3.5" /> Sync
        </Button>
      ),
    },
  ];
  return (
    <Card className="min-h-[40vh]">
      <CardHeader>
        <CardTitle>Configured connections</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="h-[40vh]">
          <DataTable<AirbyteConnection>
            rows={rows}
            rowKey={(r) => r.id}
            columns={columns}
            emptyState={loading ? <span>Loading…</span> : <span>No configured connections.</span>}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function ConnectorsTable({ rows, loading }: { rows: AirbyteConnector[]; loading: boolean }) {
  const columns: ColumnDef<AirbyteConnector>[] = [
    { key: "name", header: "Connector", render: (r) => <span className="font-mono">{r.name}</span> },
    {
      key: "kind",
      header: "Kind",
      width: 110,
      render: (r) => <Badge variant="secondary">{r.kind}</Badge>,
    },
    {
      key: "runtime",
      header: "Runtime",
      width: 130,
      render: (r) => <Badge variant="secondary">{r.runtime}</Badge>,
    },
    {
      key: "streams",
      header: "Streams",
      render: (r) => (
        <span className="font-mono text-xs">
          {r.streams && r.streams.length > 0 ? r.streams.map((s) => s.name).join(", ") : "—"}
        </span>
      ),
    },
    {
      key: "tags",
      header: "Tags",
      render: (r) => (
        <div className="flex flex-wrap gap-1">
          {(r.tags ?? []).map((t) => (
            <Badge key={t} variant="outline" className="text-[10px]">
              {t}
            </Badge>
          ))}
        </div>
      ),
    },
  ];
  return (
    <DataTable<AirbyteConnector>
      rows={rows}
      rowKey={(r) => r.id}
      columns={columns}
      emptyState={loading ? <span>Loading…</span> : <span>No connectors registered.</span>}
    />
  );
}

function RunsTable({ rows, loading }: { rows: AirbyteRun[]; loading: boolean }) {
  const columns: ColumnDef<AirbyteRun>[] = [
    {
      key: "started_at",
      header: "Started",
      width: 160,
      render: (r) => (
        <span className="text-[var(--text-secondary)]">
          {r.started_at ? formatTime(r.started_at) : "—"}
        </span>
      ),
    },
    {
      key: "runtime",
      header: "Runtime",
      width: 130,
      render: (r) => <Badge variant="secondary">{r.runtime}</Badge>,
    },
    {
      key: "status",
      header: "Status",
      width: 130,
      render: (r) => <Badge variant="secondary">{r.status}</Badge>,
    },
    {
      key: "airbyte_job_id",
      header: "Airbyte job",
      width: 160,
      render: (r) => (
        <span className="font-mono text-xs">{r.airbyte_job_id ?? "—"}</span>
      ),
    },
    {
      key: "task_id",
      header: "Task",
      width: 160,
      render: (r) => <span className="font-mono text-xs">{r.task_id ?? "—"}</span>,
    },
    {
      key: "error",
      header: "Error",
      render: (r) => (
        <span className="text-xs text-[var(--neg-fg)]">{r.error ?? "—"}</span>
      ),
    },
  ];
  return (
    <DataTable<AirbyteRun>
      rows={rows}
      rowKey={(r) => r.id}
      columns={columns}
      emptyState={loading ? <span>Loading…</span> : <span>No runs in the registry.</span>}
    />
  );
}

function parseConfig(text: string): Record<string, unknown> {
  const parsed = JSON.parse(text || "{}") as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Config must be a JSON object");
  }
  return parsed as Record<string, unknown>;
}
