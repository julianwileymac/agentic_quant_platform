import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import {
  cloudflareHealth,
  createTunnel,
  deleteTunnel,
  listAccessApps,
  listTunnels,
  type TunnelSummary,
} from "@/lib/api/cloudflare";

/**
 * Cloudflare edge studio — Phase D of the Management Engine.
 *
 * Backs the new `/cloudflare/*` REST surface (Tunnels + Access apps +
 * DNS records). The Vite shell is intentionally bare in this drop —
 * detailed editors for ingress rules, Access policies, and DNS
 * record bulk import land in the Phase D-2 follow-up.
 */
export function CloudflareEdgeRoute(): React.ReactElement {
  const qc = useQueryClient();
  const { data: health } = useQuery({
    queryKey: ["cloudflare", "health"],
    queryFn: cloudflareHealth,
    refetchInterval: 30_000,
  });
  const { data: tunnels = [] } = useQuery({
    queryKey: ["cloudflare", "tunnels"],
    queryFn: () => listTunnels(),
  });
  const { data: apps = [] } = useQuery({
    queryKey: ["cloudflare", "access", "apps"],
    queryFn: listAccessApps,
  });

  const createMut = useMutation({
    mutationFn: (name: string) => createTunnel(name, "cloudflare"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cloudflare", "tunnels"] }),
  });
  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteTunnel(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cloudflare", "tunnels"] }),
  });
  const [newName, setNewName] = useState("");
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  const healthOk = health?.status === "ok";

  return (
    <div className="space-y-6 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Cloudflare edge</h1>
          <p className="text-muted-foreground text-sm">
            Tunnels + Access apps + DNS records. Backed by the
            <code className="mx-1">CloudflareEdgeAdapter</code> via the
            AQP Management Engine.
          </p>
        </div>
        <Badge variant={healthOk ? "default" : "negative"}>
          {health?.status ?? "unknown"}
        </Badge>
      </header>

      <Card className="space-y-3 p-4">
        <h2 className="text-lg font-semibold">Tunnels</h2>
        <div className="flex gap-2">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="aqp-rpi-edge"
            className="w-64 rounded border border-input bg-transparent px-2 py-1 text-sm font-mono"
          />
          <Button
            size="sm"
            onClick={() =>
              createMut.mutate(newName, {
                onSuccess: (t) => {
                  toast.success(`created tunnel ${t.name}`);
                  setNewName("");
                },
                onError: (err) =>
                  toast.error("create failed", { description: String(err) }),
              })
            }
            disabled={!newName || createMut.isPending}
          >
            Create tunnel
          </Button>
        </div>
        <div className="grid gap-2">
          {tunnels.map((t) => (
            <TunnelRow
              key={t.id}
              tunnel={t}
              onDelete={() => setPendingDelete(t.id)}
            />
          ))}
          {tunnels.length === 0 && (
            <p className="text-muted-foreground text-sm">No tunnels yet.</p>
          )}
        </div>
      </Card>

      <Card className="space-y-3 p-4">
        <h2 className="text-lg font-semibold">Access applications</h2>
        <div className="grid gap-2">
          {apps.map((a) => (
            <div
              key={a.id}
              className="flex items-center justify-between rounded border border-border p-2"
            >
              <div>
                <p className="font-medium font-mono">{a.name}</p>
                <p className="text-muted-foreground text-xs font-mono">
                  {a.domain}
                </p>
              </div>
              <Badge variant="outline">{a.type}</Badge>
            </div>
          ))}
          {apps.length === 0 && (
            <p className="text-muted-foreground text-sm">No Access apps yet.</p>
          )}
        </div>
      </Card>

      <ConfirmFrictionDialog
        open={pendingDelete !== null}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title="Delete Cloudflare tunnel"
        consequence="Removing the tunnel disconnects every public endpoint routed through it until cloudflared is re-attached. Existing Access app policies stay."
        confirmPhrase="DELETE"
        confirmLabel="Delete tunnel"
        confirmVariant="destructive"
        onConfirm={async () => {
          if (!pendingDelete) return;
          deleteMut.mutate(pendingDelete, {
            onSuccess: () => toast.success("tunnel deleted"),
            onError: (err) =>
              toast.error("delete failed", { description: String(err) }),
          });
          setPendingDelete(null);
        }}
      />
    </div>
  );
}

function TunnelRow({ tunnel, onDelete }: { tunnel: TunnelSummary; onDelete: () => void }) {
  const healthy = tunnel.status.toLowerCase() === "healthy";
  return (
    <div className="flex items-center justify-between rounded border border-border p-2">
      <div>
        <p className="font-medium font-mono">{tunnel.name}</p>
        <p className="text-muted-foreground text-xs font-mono">id: {tunnel.id}</p>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant={healthy ? "default" : "secondary"}>
          {tunnel.status || "unknown"}
        </Badge>
        <Badge variant="outline">conns: {tunnel.connections}</Badge>
        <Button size="sm" variant="outline" onClick={onDelete}>
          Delete
        </Button>
      </div>
    </div>
  );
}
