import { Loader2, PowerOff, Zap } from "lucide-react";
import { useEffect, useState } from "react";

import { DeploymentPicker } from "@/components/strategy-dev/DeploymentPicker";
import { useStrategyDev } from "@/components/strategy-dev/StrategyDevLayout";
import { SymbolsInput } from "@/components/strategy-dev/SymbolsInput";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";
import { useLiveStream } from "@/lib/ws";

interface LiveStartResp {
  channel_id: string;
  ws_url?: string;
}

/**
 * Live-test bridge. Calls `POST /ml/live-test/start` to open a
 * server-side stream, then subscribes via `useLiveStream`. Cleanly
 * tears down on route unmount or stop.
 */
export function LiveTestRoute() {
  const { selection, setSelection } = useStrategyDev();
  const [channelId, setChannelId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const live = useLiveStream({ channelId });

  useEffect(() => {
    return () => {
      if (channelId) {
        apiFetch(`/ml/live-test/${channelId}`, { method: "DELETE" }).catch(() => {
          /* noop on unmount */
        });
      }
    };
  }, [channelId]);

  const start = async () => {
    if (!selection.deploymentId) {
      toast.warning("Pick a deployment first");
      return;
    }
    setSubmitting(true);
    try {
      const res = await apiFetch<LiveStartResp>("/ml/live-test/start", {
        method: "POST",
        body: JSON.stringify({
          deployment_id: selection.deploymentId,
          venue: "simulated",
          symbols: selection.symbols,
        }),
      });
      setChannelId(res.channel_id);
      toast.success(`Live channel opened: ${res.channel_id.slice(0, 8)}…`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const stop = async () => {
    if (!channelId) return;
    try {
      await apiFetch(`/ml/live-test/${channelId}`, { method: "DELETE" });
      toast.success("Live channel closed");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    }
    setChannelId(null);
  };

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Live model inference</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <DeploymentPicker
            label="Deployment"
            value={selection.deploymentId}
            onChange={(deploymentId) => setSelection({ deploymentId })}
          />
          <SymbolsInput
            label="Symbols"
            value={selection.symbols}
            onChange={(symbols) => setSelection({ symbols })}
          />
          <div className="flex gap-2">
            {channelId ? (
              <Button variant="destructive" onClick={stop}>
                <PowerOff className="h-4 w-4" />
                Stop
              </Button>
            ) : (
              <Button onClick={start} disabled={submitting || !selection.deploymentId}>
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
                Start streaming
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Streaming bridge</CardTitle>
        </CardHeader>
        <CardContent>
          {!channelId ? (
            <p className="text-xs text-[var(--text-secondary)]">
              Start the bridge to subscribe.
            </p>
          ) : (
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2 text-xs">
                <Badge variant="default">channel {channelId.slice(0, 8)}…</Badge>
                <Badge variant={live.status === "open" ? "positive" : "secondary"}>
                  {live.status}
                </Badge>
                {live.error ? <Badge variant="negative">{live.error}</Badge> : null}
              </div>
              <p className="text-xs text-[var(--text-secondary)]">
                Live ticks are routed into <code className="rounded bg-[var(--bg-app)] px-1">useMarketStore</code> and
                drawn by any subscribed component (order book, position table, charts).
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
