import { CloudUpload, Loader2, Plus } from "lucide-react";
import { useState } from "react";

import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import {
  featureSetsApi,
  type FeatureSetSummary,
} from "@/lib/api/featureSets";
import { useApiQuery } from "@/lib/api/hooks";
import { formatTime } from "@/lib/utils";

export function MlDatasetDesigner() {
  const list = useApiQuery<FeatureSetSummary[]>({
    queryKey: ["feature-sets"],
    path: "/feature-sets",
    select: (raw) => (Array.isArray(raw) ? (raw as FeatureSetSummary[]) : []),
  });

  const [name, setName] = useState("");
  const [kind, setKind] = useState("technical");
  const [specs, setSpecs] = useState("close, returns, sma_20, rsi_14");
  const [busy, setBusy] = useState(false);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      await featureSetsApi.create({
        name: name.trim(),
        kind,
        specs: specs.split(",").map((s) => s.trim()).filter(Boolean),
        default_lookback_days: 365,
      });
      toast.success(`Feature set ${name} created`);
      list.refetch();
      setName("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const columns: ColumnDef<FeatureSetSummary>[] = [
    { key: "name", header: "Feature set", render: (r) => <span className="font-medium">{r.name}</span> },
    { key: "kind", header: "Kind", width: 130, render: (r) => <Badge variant="secondary">{r.kind}</Badge> },
    {
      key: "specs",
      header: "Specs",
      render: (r) => (
        <div className="flex flex-wrap gap-1">
          {r.specs.slice(0, 6).map((s) => (
            <Badge key={s} variant="outline" className="text-[10px] font-mono">
              {s}
            </Badge>
          ))}
          {r.specs.length > 6 ? (
            <span className="text-[10px] text-[var(--text-muted)]">+{r.specs.length - 6}</span>
          ) : null}
        </div>
      ),
    },
    {
      key: "version",
      header: "v",
      width: 70,
      align: "right",
      render: (r) => <span className="font-mono">{r.version}</span>,
    },
    {
      key: "status",
      header: "Status",
      width: 110,
      render: (r) => <Badge variant="secondary">{r.status}</Badge>,
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
      title="ML Datasets"
      subtitle="Author and version feature sets that ML training pipelines consume. Each row is hash-locked; specs accumulate immutable versions."
    >
      <Card className="mb-3">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Plus className="h-4 w-4" /> New feature set
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={create} className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="fs-name">Name</Label>
              <Input
                id="fs-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="alpha158_v1"
                className="w-64 font-mono"
                required
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="fs-kind">Kind</Label>
              <select
                id="fs-kind"
                value={kind}
                onChange={(e) => setKind(e.target.value)}
                className="h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm"
              >
                <option value="technical">technical</option>
                <option value="fundamental">fundamental</option>
                <option value="macro">macro</option>
                <option value="alternative">alternative</option>
              </select>
            </div>
            <div className="flex flex-1 flex-col gap-1">
              <Label htmlFor="fs-specs">Specs (comma-separated)</Label>
              <Input
                id="fs-specs"
                value={specs}
                onChange={(e) => setSpecs(e.target.value)}
                className="font-mono"
                placeholder="close, returns, sma_20"
              />
            </div>
            <Button type="submit" disabled={busy} className="gap-2">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudUpload className="h-4 w-4" />}
              {busy ? "Saving…" : "Save"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card className="h-[calc(100vh-360px)]">
        <CardContent className="h-full p-0">
          <DataTable<FeatureSetSummary>
            rows={list.data ?? []}
            rowKey={(r) => r.id}
            columns={columns}
            emptyState={list.isPending ? <span>Loading…</span> : <span>No feature sets.</span>}
          />
        </CardContent>
      </Card>
    </PageContainer>
  );
}
