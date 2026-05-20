import { CloudUpload, Pause, Play, RefreshCcw, Sliders } from "lucide-react";
import { useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { producersApi, type ProducerSummary } from "@/lib/api/producers";
import { formatTime } from "@/lib/utils";

type ActionKind =
  | { kind: "start"; producer: ProducerSummary }
  | { kind: "stop"; producer: ProducerSummary }
  | { kind: "scale"; producer: ProducerSummary; replicas: number };

export function ProducersRoute() {
  const [pending, setPending] = useState<ActionKind | null>(null);
  const [scaleDraft, setScaleDraft] = useState<{ name: string; replicas: number } | null>(null);

  const list = useApiQuery<ProducerSummary[]>({
    queryKey: ["producers"],
    path: "/streaming/producers",
    refetchInterval: 5_000,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  const submit = async () => {
    if (!pending) return;
    try {
      switch (pending.kind) {
        case "start":
          await producersApi.start(pending.producer.name);
          toast.success(`${pending.producer.name} started`);
          break;
        case "stop":
          await producersApi.stop(pending.producer.name);
          toast.success(`${pending.producer.name} stopped`);
          break;
        case "scale":
          await producersApi.scale(pending.producer.name, pending.replicas);
          toast.success(`${pending.producer.name} scaled to ${pending.replicas}`);
          break;
      }
      list.refetch();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Action failed: ${msg}`);
    } finally {
      setPending(null);
      setScaleDraft(null);
    }
  };

  return (
    <PageContainer
      title="Market data producers"
      subtitle="Producer registry. start / stop / scale are friction-gated; the supervisor reseeds curated producers on next boot."
      extra={
        <Button variant="ghost" size="sm" onClick={() => list.refetch()}>
          <RefreshCcw className="h-4 w-4" /> Refresh
        </Button>
      }
    >
      <Card className="h-[calc(100vh-180px)]">
        <CardContent className="h-full p-0">
          <DataTable<ProducerSummary>
            rows={list.data ?? []}
            rowKey={(p) => p.name}
            emptyState={
              list.isPending ? (
                <span>Loading producers…</span>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <CloudUpload className="h-6 w-6" />
                  <span>No producers registered.</span>
                </div>
              )
            }
            columns={[
              {
                key: "name",
                header: "Producer",
                render: (p) => (
                  <div className="flex flex-col">
                    <span className="font-medium">{p.name}</span>
                    <span className="font-mono text-[10px] text-[var(--text-muted)]">{p.id}</span>
                  </div>
                ),
              },
              {
                key: "kind",
                header: "Kind",
                width: 140,
                render: (p) => <Badge variant="secondary">{p.kind}</Badge>,
              },
              {
                key: "status",
                header: "Status",
                width: 110,
                render: (p) => (
                  <Badge
                    variant={
                      p.last_status === "running"
                        ? "positive"
                        : p.last_status === "stopped"
                          ? "warn"
                          : p.last_status === "failed"
                            ? "negative"
                            : "secondary"
                    }
                  >
                    {p.last_status}
                  </Badge>
                ),
              },
              {
                key: "topics",
                header: "Topics",
                width: 200,
                render: (p) => (
                  <span className="font-mono text-xs">
                    {p.topics && p.topics.length > 0 ? p.topics.join(", ") : "—"}
                  </span>
                ),
              },
              {
                key: "replicas",
                header: "Replicas",
                width: 110,
                align: "right",
                render: (p) => (
                  <Numeric
                    value={p.current_replicas}
                    kind="integer"
                    digits={0}
                    color="neutral"
                  />
                ),
              },
              {
                key: "heartbeat",
                header: "Last status",
                width: 140,
                align: "right",
                render: (p) => (
                  <span className="text-[var(--text-secondary)]">
                    {p.last_status_at ? formatTime(p.last_status_at) : "—"}
                  </span>
                ),
              },
              {
                key: "actions",
                header: "Actions",
                width: 240,
                render: (p) => (
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        setPending({ kind: "start", producer: p });
                      }}
                      disabled={p.last_status === "running"}
                      className="gap-1 text-[var(--pos-fg)]"
                    >
                      <Play className="h-3.5 w-3.5" /> Start
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        setPending({ kind: "stop", producer: p });
                      }}
                      disabled={p.last_status !== "running"}
                      className="gap-1 text-[var(--warn-fg)]"
                    >
                      <Pause className="h-3.5 w-3.5" /> Stop
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        setScaleDraft({ name: p.name, replicas: p.current_replicas });
                      }}
                      className="gap-1"
                    >
                      <Sliders className="h-3.5 w-3.5" /> Scale
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        </CardContent>
      </Card>

      {scaleDraft ? (
        <Card className="mt-4 max-w-md">
          <CardContent className="grid gap-3 py-4">
            <div className="text-sm font-semibold">Scale {scaleDraft.name}</div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="scale-replicas">Replicas</Label>
              <Input
                id="scale-replicas"
                type="number"
                min={0}
                max={64}
                value={scaleDraft.replicas}
                onChange={(e) =>
                  setScaleDraft((prev) =>
                    prev ? { ...prev, replicas: Number(e.target.value) || 0 } : prev,
                  )
                }
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setScaleDraft(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => {
                  const target = list.data?.find((p) => p.name === scaleDraft.name);
                  if (!target) return;
                  setPending({ kind: "scale", producer: target, replicas: scaleDraft.replicas });
                }}
              >
                Apply
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {pending ? (
        <ConfirmFrictionDialog
          open
          onOpenChange={(open) => !open && setPending(null)}
          title={describeAction(pending)}
          consequence={consequenceFor(pending)}
          details={[
            { label: "Producer", value: pending.producer.name },
            { label: "Kind", value: pending.producer.kind },
            ...(pending.kind === "scale"
              ? [{ label: "Replicas", value: pending.replicas, tone: "warn" as const }]
              : []),
          ]}
          confirmPhrase=""
          confirmLabel={describeAction(pending)}
          confirmVariant={pending.kind === "stop" ? "warn" : "default"}
          onConfirm={submit}
        />
      ) : null}
    </PageContainer>
  );
}

function describeAction(action: ActionKind): string {
  switch (action.kind) {
    case "start":
      return `Start ${action.producer.name}`;
    case "stop":
      return `Stop ${action.producer.name}`;
    case "scale":
      return `Scale ${action.producer.name} → ${action.replicas}`;
  }
}

function consequenceFor(action: ActionKind): string {
  switch (action.kind) {
    case "start":
      return "Spins up the producer process. Connection to the upstream broker / API is opened on first heartbeat.";
    case "stop":
      return "Sends a stop signal. In-flight publishes complete; subsequent fetches stop until restarted.";
    case "scale":
      return "Adjusts replica count. Scaling down terminates the highest-numbered pods first; scaling up provisions new replicas asynchronously.";
  }
}
