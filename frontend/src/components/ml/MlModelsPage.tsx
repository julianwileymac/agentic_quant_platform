import { RefreshCcw } from "lucide-react";

import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";
import { formatTime } from "@/lib/utils";

interface MlModelDeployment {
  id: string;
  name: string;
  version?: string;
  status: string;
  framework?: string;
  metrics?: Record<string, number | string | null>;
  registered_at?: string;
}

export function MlModelsPage() {
  const list = useApiQuery<MlModelDeployment[]>({
    queryKey: ["ml", "models"],
    path: "/ml/models",
    select: (raw) => (Array.isArray(raw) ? (raw as MlModelDeployment[]) : []),
  });

  const columns: ColumnDef<MlModelDeployment>[] = [
    { key: "name", header: "Model", render: (r) => <span className="font-medium">{r.name}</span> },
    {
      key: "version",
      header: "Version",
      width: 110,
      render: (r) => <span className="font-mono text-xs">{r.version ?? "—"}</span>,
    },
    {
      key: "framework",
      header: "Framework",
      width: 130,
      render: (r) => <Badge variant="secondary">{r.framework ?? "—"}</Badge>,
    },
    {
      key: "status",
      header: "Status",
      width: 110,
      render: (r) => <Badge variant="secondary">{r.status}</Badge>,
    },
    {
      key: "sharpe",
      header: "Sharpe",
      width: 100,
      align: "right",
      render: (r) => (
        <Numeric
          value={typeof r.metrics?.sharpe === "number" ? r.metrics.sharpe : null}
          kind="decimal"
          digits={2}
          color="auto"
        />
      ),
    },
    {
      key: "registered_at",
      header: "Registered",
      width: 140,
      align: "right",
      render: (r) => (
        <span className="text-[var(--text-secondary)]">
          {r.registered_at ? formatTime(r.registered_at) : "—"}
        </span>
      ),
    },
  ];

  return (
    <PageContainer
      title="ML Models"
      subtitle="Registered ML model deployments, their framework + version, and headline metrics. Mirrors `mlflow models list-deployments`."
      extra={
        <Button variant="ghost" size="sm" onClick={() => list.refetch()}>
          <RefreshCcw className="h-4 w-4" /> Refresh
        </Button>
      }
    >
      <Card className="h-[calc(100vh-180px)]">
        <CardContent className="h-full p-0">
          <DataTable<MlModelDeployment>
            rows={list.data ?? []}
            rowKey={(r) => r.id}
            columns={columns}
            emptyState={list.isPending ? <span>Loading…</span> : <span>No registered models.</span>}
          />
        </CardContent>
      </Card>
    </PageContainer>
  );
}
