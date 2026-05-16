import { useState } from "react";
import { Loader2, PlayCircle, RefreshCcw } from "lucide-react";

import { LobReplayChart } from "@/components/backtest/LobReplayChart";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useApiMutation, useApiQuery } from "@/lib/api/hooks";

const STRATEGIES = [
  { value: "AvellanedaStoikovMM", label: "Avellaneda-Stoikov MM (full HJB)" },
  { value: "GLFTMM", label: "GLFT closed-form MM" },
  { value: "GridMM", label: "Symmetric grid MM" },
  { value: "ImbalanceAlphaMM", label: "Imbalance-skew alpha MM" },
  { value: "BasisAlphaMM", label: "Cross-instrument basis MM" },
  { value: "QueueAwareMM", label: "Queue-position-aware MM" },
];

const PRESETS = [
  { value: "lob_btcusdt_sample", label: "BTC-USDT sample (Binance USDM)" },
];

const LATENCY_PROFILES = [
  { value: "intp_order_latency", label: "Interpolated (file-driven, default)" },
  { value: "constant_50us", label: "Constant 50 µs" },
];

const QUEUE_MODELS = [
  { value: "probabilistic", label: "Probabilistic (default)" },
  { value: "risk_averse", label: "Risk-averse" },
];

interface LaunchResponse {
  task_id: string;
  status: string;
  stream_url?: string;
}

interface LobBacktestSummary {
  task_id: string;
  status: string;
  summary?: Record<string, number | string | boolean | null> | null;
  error?: string | null;
}

const SELECT_CLASSES =
  "h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm text-[var(--text-primary)]";

/** Full HFT/LOB backtest wizard. Talks to /backtest/lob; streams live progress. */
export function LobBacktestRoute() {
  const [strategy, setStrategy] = useState("AvellanedaStoikovMM");
  const [preset, setPreset] = useState<string>("lob_btcusdt_sample");
  const [latencyProfile, setLatencyProfile] = useState("intp_order_latency");
  const [queueModel, setQueueModel] = useState("probabilistic");
  const [maxEvents, setMaxEvents] = useState(1_000_000);
  const [snapshotEvery, setSnapshotEvery] = useState(5_000);
  const [taskId, setTaskId] = useState<string | null>(null);

  const launch = useApiMutation<LaunchResponse, Record<string, unknown>>({
    method: "POST",
    path: "/backtest/lob",
  });

  const status = useApiQuery<LobBacktestSummary>({
    queryKey: ["lob_backtest", taskId ?? "none"],
    path: taskId ? `/backtest/lob/${taskId}` : "/backtest/lob/none",
    refetchInterval: taskId ? 2000 : false,
    enabled: Boolean(taskId),
  });

  const onLaunch = () => {
    launch.mutate(
      {
        strategy,
        dataset_preset: preset,
        latency_profile: latencyProfile,
        queue_model: queueModel,
        max_events: maxEvents,
        snapshot_every: snapshotEvery,
      },
      {
        onSuccess: (result) => {
          setTaskId(result.task_id);
        },
      },
    );
  };

  const summary = status.data?.summary ?? null;
  const isRunning = status.data?.status === "pending" || status.data?.status === "started";

  return (
    <PageContainer
      title="HFT / LOB backtest"
      subtitle="Tick-level replay through hftbacktest. Pick a strategy, dataset, latency model, and inspect the equity / position curve."
      extra={
        <Button variant="ghost" size="sm" onClick={() => status.refetch()} disabled={!taskId}>
          <RefreshCcw className="h-4 w-4" /> Refresh
        </Button>
      }
    >
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Configuration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="lob-strategy">Strategy</Label>
              <select
                id="lob-strategy"
                className={SELECT_CLASSES + " w-full"}
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
              >
                {STRATEGIES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="lob-preset">Dataset preset</Label>
              <select
                id="lob-preset"
                className={SELECT_CLASSES + " w-full"}
                value={preset}
                onChange={(e) => setPreset(e.target.value)}
              >
                {PRESETS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="lob-latency">Latency profile</Label>
                <select
                  id="lob-latency"
                  className={SELECT_CLASSES + " w-full"}
                  value={latencyProfile}
                  onChange={(e) => setLatencyProfile(e.target.value)}
                >
                  {LATENCY_PROFILES.map((l) => (
                    <option key={l.value} value={l.value}>
                      {l.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="lob-queue">Queue model</Label>
                <select
                  id="lob-queue"
                  className={SELECT_CLASSES + " w-full"}
                  value={queueModel}
                  onChange={(e) => setQueueModel(e.target.value)}
                >
                  {QUEUE_MODELS.map((q) => (
                    <option key={q.value} value={q.value}>
                      {q.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="lob-max-events">Max events</Label>
                <Input
                  id="lob-max-events"
                  type="number"
                  value={maxEvents}
                  onChange={(e) => setMaxEvents(Number(e.target.value))}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="lob-snapshot">Snapshot every</Label>
                <Input
                  id="lob-snapshot"
                  type="number"
                  value={snapshotEvery}
                  onChange={(e) => setSnapshotEvery(Number(e.target.value))}
                />
              </div>
            </div>
            <Button onClick={onLaunch} disabled={launch.isPending}>
              {launch.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <PlayCircle className="h-4 w-4" />
              )}
              Launch backtest
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              Status{" "}
              {taskId ? (
                <Badge
                  variant={
                    isRunning
                      ? "default"
                      : status.data?.status === "success"
                        ? "positive"
                        : "secondary"
                  }
                >
                  {status.data?.status ?? "queued"}
                </Badge>
              ) : null}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!taskId ? (
              <p className="text-sm text-[var(--text-muted)]">
                Launch a backtest to stream progress + render the equity / position curve.
              </p>
            ) : (
              <div className="space-y-2 text-sm">
                <div>
                  <span className="text-[var(--text-muted)]">Task ID:</span>{" "}
                  <code className="font-mono text-xs">{taskId}</code>
                </div>
                {summary ? (
                  <div className="grid grid-cols-2 gap-2 pt-2">
                    <SummaryTile label="Sharpe (sample)" value={summary.hft_sharpe_sample_aware} />
                    <SummaryTile label="Sortino (sample)" value={summary.hft_sortino_sample_aware} />
                    <SummaryTile label="Max position" value={summary.hft_max_position} />
                    <SummaryTile label="Mean leverage" value={summary.hft_mean_leverage} />
                    <SummaryTile label="Fill ratio" value={summary.hft_fill_ratio} />
                    <SummaryTile label="Events" value={summary.events_processed} />
                  </div>
                ) : null}
                {status.data?.error ? (
                  <p className="rounded bg-[var(--surface-error)] p-2 text-xs text-[var(--text-error)]">
                    {status.data.error}
                  </p>
                ) : null}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Replay chart</CardTitle>
          </CardHeader>
          <CardContent className="h-[420px] p-0">
            <LobReplayChart taskId={taskId} />
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}

function SummaryTile({
  label,
  value,
}: {
  label: string;
  value: number | string | boolean | null | undefined;
}) {
  const num = typeof value === "number" ? value : Number(value);
  return (
    <div className="rounded border border-[var(--border-default)] p-2">
      <div className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">{label}</div>
      {Number.isFinite(num) ? (
        <Numeric value={num} kind="decimal" digits={3} color="auto" />
      ) : (
        <span className="font-mono text-xs">{String(value ?? "—")}</span>
      )}
    </div>
  );
}
