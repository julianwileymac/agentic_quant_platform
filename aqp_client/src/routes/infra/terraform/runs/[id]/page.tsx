import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { useApiQuery } from "@/lib/api/hooks";
import { type TerraformRun, terraformApi } from "@/lib/api/terraform";
import { formatTime } from "@/lib/utils";

interface ProgressFrame {
  task_id: string;
  stage: string;
  message: string;
  timestamp: number;
  [extra: string]: unknown;
}

function useRunStream(runId: string): ProgressFrame[] {
  const [frames, setFrames] = useState<ProgressFrame[]>([]);
  useEffect(() => {
    if (!runId) return;
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(
      `${proto}//${window.location.host}/terraform/ws/runs/${encodeURIComponent(runId)}`,
    );
    ws.onmessage = (e) => {
      try {
        const frame: ProgressFrame = JSON.parse(e.data);
        setFrames((prev) => [...prev.slice(-499), frame]);
      } catch {
        /* ignore */
      }
    };
    return () => {
      try {
        ws.close();
      } catch {
        /* ignore */
      }
    };
  }, [runId]);
  return frames;
}

export function TerraformRunDetailRoute() {
  const { id = "" } = useParams<{ id: string }>();
  const run = useApiQuery<TerraformRun>({
    queryKey: ["terraform", "run", id],
    path: `/terraform/runs/${encodeURIComponent(id)}`,
    refetchInterval: 5_000,
    select: (raw) => raw as TerraformRun,
  });
  const frames = useRunStream(id);
  const [cancelling, setCancelling] = useState(false);

  const r = run.data;

  const cancel = async () => {
    setCancelling(true);
    try {
      await terraformApi.cancelRun(id);
      toast.success("Run cancelled");
    } catch (err) {
      toast.error("Cancel failed", {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setCancelling(false);
    }
  };

  return (
    <PageContainer
      title={`Terraform run · ${id.slice(0, 8)}`}
      subtitle={r ? `${r.run_kind} · ${r.status}` : "Loading…"}
      data-mode="infra"
      extra={
        r && !["completed", "errored", "cancelled"].includes(r.status) ? (
          <Button variant="destructive" onClick={cancel} disabled={cancelling}>
            Cancel
          </Button>
        ) : null
      }
    >
      {r ? (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle>Run metadata</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-xs">
              <KV k="kind" v={r.run_kind} />
              <KV k="status" v={<Badge variant="outline">{r.status}</Badge>} />
              <KV k="halted" v={r.halted ? "yes" : "no"} />
              <KV k="exit_code" v={r.exit_code ?? "—"} />
              <KV k="started_at" v={r.started_at ? formatTime(r.started_at) : "—"} />
              <KV k="finished_at" v={r.finished_at ? formatTime(r.finished_at) : "—"} />
              <KV
                k="duration_ms"
                v={r.duration_ms != null ? r.duration_ms.toFixed(0) : "—"}
              />
              <KV k="experiment_id" v={r.experiment_id ?? "—"} />
            </CardContent>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Plan summary</CardTitle>
            </CardHeader>
            <CardContent className="text-xs">
              <pre className="overflow-x-auto whitespace-pre-wrap font-mono">
                {JSON.stringify(r.plan_summary_json ?? {}, null, 2)}
              </pre>
            </CardContent>
          </Card>

          {r.policy_check_result &&
          Object.keys(r.policy_check_result).length > 0 ? (
            <Card className="lg:col-span-3">
              <CardHeader>
                <CardTitle>Policy check</CardTitle>
              </CardHeader>
              <CardContent className="text-xs">
                <pre className="overflow-x-auto whitespace-pre-wrap font-mono">
                  {JSON.stringify(r.policy_check_result, null, 2)}
                </pre>
              </CardContent>
            </Card>
          ) : null}

          <Card className="lg:col-span-3">
            <CardHeader>
              <CardTitle>Live progress stream</CardTitle>
            </CardHeader>
            <CardContent>
              {frames.length === 0 ? (
                <p className="text-xs text-[var(--text-secondary)]">
                  Awaiting frames from /terraform/ws/runs/{id}…
                </p>
              ) : (
                <ul className="space-y-1 font-mono text-[11px]">
                  {frames.map((f, idx) => (
                    <li
                      key={`${f.timestamp}-${idx}`}
                      className="flex items-baseline gap-2 rounded-sm border border-[var(--border)] px-2 py-1"
                    >
                      <span className="text-[var(--text-secondary)]">
                        {new Date(f.timestamp * 1000).toLocaleTimeString()}
                      </span>
                      <Badge variant="outline">{f.stage}</Badge>
                      <span>{f.message}</span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      ) : (
        <p>Loading…</p>
      )}
    </PageContainer>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[var(--text-secondary)]">{k}</span>
      <span className="font-mono">{v}</span>
    </div>
  );
}
