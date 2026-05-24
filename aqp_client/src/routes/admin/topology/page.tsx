import { useEffect, useMemo, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ManageApi,
  type ServiceHealth,
  type TopologyService,
  type TopologySnapshot,
} from "@/lib/api/manage";

/**
 * /admin/topology — canonical landing page for the AQP infra-expansion
 * plan's new admin surface. Reads from `/manage/topology` (Phase 0
 * route group) and groups services by role: streaming, timeseries,
 * lakehouse, observability, data-services, mlops, edge, plus the AQP
 * application services. Each row supports a "Probe health" button that
 * hits `/manage/topology/services/{id}/health` and surfaces the live
 * provider status.
 *
 * The page is read-only - mutations land in the role-specific admin
 * pages (`/admin/streaming`, `/admin/observability`, ...). The kill
 * switch in the topbar already fans out to the new
 * `/manage/streaming/halt` and `/manage/lakehouse/halt` endpoints.
 */
export function TopologyOverviewRoute() {
  const [snapshot, setSnapshot] = useState<TopologySnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [healthCache, setHealthCache] = useState<
    Record<string, ServiceHealth | null>
  >({});
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("streaming");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    ManageApi.topology
      .snapshot()
      .then((envelope) => {
        if (cancelled) return;
        setSnapshot(envelope.data);
        setError(null);
      })
      .catch((exc) => {
        if (cancelled) return;
        setError(String(exc));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const grouped = useMemo<Record<string, TopologyService[]>>(() => {
    if (!snapshot) return {};
    const out: Record<string, TopologyService[]> = {};
    for (const svc of snapshot.services) {
      const key = svc.role || "other";
      out[key] = out[key] ? [...out[key], svc] : [svc];
    }
    return out;
  }, [snapshot]);

  const probeHealth = async (serviceId: string) => {
    try {
      const result = await ManageApi.topology.serviceHealth(serviceId);
      setHealthCache((current) => ({ ...current, [serviceId]: result.data }));
    } catch (exc) {
      setHealthCache((current) => ({
        ...current,
        [serviceId]: {
          service_id: serviceId,
          namespace: "",
          status: "error",
          error: String(exc),
        },
      }));
    }
  };

  return (
    <PageContainer
      title="Topology"
      subtitle={
        snapshot
          ? `Active target: ${snapshot.active_target_id}. ${snapshot.services.length} services across ${
              new Set(snapshot.services.map((s) => s.namespace || "(unset)")).size
            } namespaces.`
          : "Loading topology snapshot from /manage/topology..."
      }
    >
      {error ? (
        <Card>
          <CardHeader>
            <CardTitle>Topology unavailable</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-[var(--neg-fg)]">{error}</p>
          </CardContent>
        </Card>
      ) : null}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          {[
            "streaming",
            "timeseries",
            "lakehouse",
            "observability",
            "tracing",
            "logging",
            "database",
            "cache",
            "storage",
            "metadata",
            "mlops",
            "orchestration",
            "elt",
            "vector-store",
          ].map((role) =>
            (grouped[role] ?? []).length === 0 ? null : (
              <TabsTrigger key={role} value={role}>
                {role} ({(grouped[role] ?? []).length})
              </TabsTrigger>
            ),
          )}
        </TabsList>

        {Object.entries(grouped).map(([role, services]) => (
          <TabsContent key={role} value={role}>
            <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
              {services.map((svc) => (
                <Card key={svc.id}>
                  <CardHeader>
                    <CardTitle className="flex items-baseline justify-between gap-2">
                      <span>{svc.label}</span>
                      <Badge variant="outline">{svc.id}</Badge>
                    </CardTitle>
                    <p className="text-xs text-[var(--text-muted)]">
                      <code>{svc.namespace || "(unset namespace)"}</code> ·{" "}
                      <code>{svc.workload}</code>
                      {svc.cluster ? ` · ${svc.cluster}` : ""}
                    </p>
                  </CardHeader>
                  <CardContent className="space-y-2 text-xs">
                    {svc.endpoints && Object.keys(svc.endpoints).length > 0 ? (
                      <div>
                        <p className="font-semibold">Endpoints</p>
                        <ul className="font-mono">
                          {Object.entries(svc.endpoints).map(([name, url]) => (
                            <li key={name}>
                              <span className="text-[var(--text-muted)]">{name}</span>
                              {": "}
                              <code>{url}</code>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {svc.protocols && Object.keys(svc.protocols).length > 0 ? (
                      <div>
                        <p className="font-semibold">Ports</p>
                        <ul className="font-mono">
                          {Object.entries(svc.protocols).map(([name, port]) => (
                            <li key={name}>
                              {name}: <code>{port}</code>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    <div className="flex items-center gap-2 pt-1">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => probeHealth(svc.id)}
                      >
                        Probe health
                      </Button>
                      {healthCache[svc.id] ? (
                        <Badge
                          variant={
                            healthCache[svc.id]?.status === "running"
                              ? "positive"
                              : "negative"
                          }
                        >
                          {healthCache[svc.id]?.status}
                        </Badge>
                      ) : null}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>
        ))}
      </Tabs>

      {loading ? (
        <p className="mt-4 text-xs text-[var(--text-muted)]">
          Loading topology snapshot from <code>/manage/topology</code>...
        </p>
      ) : null}
    </PageContainer>
  );
}

export default TopologyOverviewRoute;
