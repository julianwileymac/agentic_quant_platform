import { Eye, RefreshCcw } from "lucide-react";
import { useState } from "react";

import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import {
  featureSetsApi,
  useFeatureSets,
  type FeatureSetSummary,
} from "@/lib/api/featureSets";
import { formatTime } from "@/lib/utils";

export function FeatureSetWorkbench() {
  const list = useFeatureSets();
  const [previewing, setPreviewing] = useState<FeatureSetSummary | null>(null);
  const [previewRows, setPreviewRows] = useState<Array<Record<string, unknown>>>([]);
  const [previewBusy, setPreviewBusy] = useState(false);

  const preview = async (fs: FeatureSetSummary) => {
    setPreviewing(fs);
    setPreviewBusy(true);
    setPreviewRows([]);
    try {
      const res = await featureSetsApi.preview(fs.id, { limit: 50 });
      setPreviewRows(res.rows ?? []);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setPreviewBusy(false);
    }
  };

  const cols: ColumnDef<FeatureSetSummary>[] = [
    { key: "name", header: "Feature set", render: (r) => <span className="font-medium">{r.name}</span> },
    { key: "kind", header: "Kind", width: 130, render: (r) => <Badge variant="secondary">{r.kind}</Badge> },
    {
      key: "specs",
      header: "Specs",
      render: (r) => (
        <span className="font-mono text-xs">
          {r.specs.length} feature{r.specs.length === 1 ? "" : "s"}
        </span>
      ),
    },
    {
      key: "version",
      header: "v",
      width: 70,
      align: "right",
      render: (r) => <Numeric value={r.version} kind="integer" digits={0} color="neutral" />,
    },
    {
      key: "lookback",
      header: "Lookback",
      width: 110,
      align: "right",
      render: (r) => <Numeric value={r.default_lookback_days} kind="integer" digits={0} color="neutral" />,
    },
    {
      key: "actions",
      header: "Actions",
      width: 110,
      render: (r) => (
        <Button variant="ghost" size="sm" onClick={() => preview(r)} className="gap-1">
          <Eye className="h-3.5 w-3.5" /> Preview
        </Button>
      ),
    },
    {
      key: "updated_at",
      header: "Updated",
      width: 140,
      align: "right",
      render: (r) => (
        <span className="text-[var(--text-secondary)]">
          {r.updated_at ? formatTime(r.updated_at) : "—"}
        </span>
      ),
    },
  ];

  return (
    <PageContainer
      title="Feature Sets"
      subtitle="Versioned feature collections that ML / RL pipelines depend on. Preview a slice to verify the resolved column set + lookback."
      extra={
        <Button variant="ghost" size="sm" onClick={() => list.refetch()}>
          <RefreshCcw className="h-4 w-4" /> Refresh
        </Button>
      }
    >
      <Card className="mb-3 h-[50vh]">
        <CardContent className="h-full p-0">
          <DataTable<FeatureSetSummary>
            rows={list.data ?? []}
            rowKey={(r) => r.id}
            columns={cols}
            emptyState={list.isPending ? <span>Loading…</span> : <span>No feature sets.</span>}
          />
        </CardContent>
      </Card>

      {previewing ? (
        <Card>
          <CardHeader>
            <CardTitle>Preview: {previewing.name}</CardTitle>
            {previewBusy ? <Badge variant="secondary">loading…</Badge> : null}
          </CardHeader>
          <CardContent>
            <pre className="max-h-[40vh] overflow-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3 font-mono text-xs">
              {previewBusy
                ? "…"
                : JSON.stringify(previewRows.slice(0, 30), null, 2)}
            </pre>
          </CardContent>
        </Card>
      ) : null}
    </PageContainer>
  );
}
