/**
 * Tenant detail page — namespace summary + identity-aware metrics.
 *
 * Reads:
 *
 *  - ``GET /admin/accounts/organizations/{org_id}`` for org metadata
 *    + tenant namespace status.
 *  - ``POST /admin/metrics/prometheus/query`` for identity-aware
 *    PromQL charts. The query injection happens server-side in the
 *    CP rewriter; the UI just sends the raw expression.
 */
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { adminApi } from "@/lib/api";

export function TenantDetail() {
  const { orgId } = useParams<{ orgId: string }>();
  const safeOrgId = orgId ?? "";
  const org = useQuery({
    queryKey: ["org", safeOrgId],
    queryFn: () => adminApi.getOrganization(safeOrgId),
    enabled: !!safeOrgId,
  });
  const cpu = useQuery({
    queryKey: ["prom-cpu", safeOrgId],
    queryFn: () => adminApi.prometheusQuery("sum(container_cpu_usage_seconds_total)"),
    enabled: !!safeOrgId,
    refetchInterval: 30000,
  });
  const memory = useQuery({
    queryKey: ["prom-mem", safeOrgId],
    queryFn: () => adminApi.prometheusQuery("sum(container_memory_working_set_bytes)"),
    enabled: !!safeOrgId,
    refetchInterval: 30000,
  });

  if (!safeOrgId) return <p>Missing org id.</p>;

  return (
    <section className="space-y-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {org.data?.organization.name ?? safeOrgId}
          </h1>
          <p className="text-sm text-muted-foreground">{safeOrgId}</p>
        </div>
        <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium">
          plan: {org.data?.organization.plan ?? "unknown"}
        </span>
      </header>
      <div className="grid grid-cols-2 gap-4">
        <Card title="Namespace">
          {org.isLoading ? (
            <p>Loading...</p>
          ) : org.data?.namespace ? (
            <pre className="overflow-auto text-xs">
              {JSON.stringify(org.data.namespace, null, 2)}
            </pre>
          ) : (
            <p className="text-sm text-muted-foreground">No namespace metadata available.</p>
          )}
        </Card>
        <Card title="Billing (live broker)">
          <BillingPanel orgId={safeOrgId} />
        </Card>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Card title="CPU usage (PromQL rewritten with aqp_tenant matcher)">
          <MetricBlock metric={cpu} />
        </Card>
        <Card title="Memory usage (PromQL rewritten with aqp_tenant matcher)">
          <MetricBlock metric={memory} />
        </Card>
      </div>
    </section>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h2>
      <div>{children}</div>
    </div>
  );
}

function MetricBlock({
  metric,
}: {
  metric: ReturnType<typeof useQuery<unknown, Error>>;
}) {
  if (metric.isLoading) return <p className="text-sm">Loading...</p>;
  if (metric.error) return <p className="text-sm text-red-600">{metric.error.message}</p>;
  const data = metric.data as
    | { data?: { rewritten_query?: string; data?: unknown } }
    | undefined;
  return (
    <div>
      <p className="text-xs text-muted-foreground">
        rewritten: <code>{data?.data?.rewritten_query ?? "—"}</code>
      </p>
      <pre className="mt-2 max-h-48 overflow-auto rounded bg-slate-50 p-2 text-xs">
        {JSON.stringify(data?.data?.data, null, 2)}
      </pre>
    </div>
  );
}

function BillingPanel({ orgId }: { orgId: string }) {
  const billing = useQuery({
    queryKey: ["billing", orgId],
    queryFn: () => adminApi.billingSummary(orgId),
  });
  if (billing.isLoading) return <p>Loading billing...</p>;
  if (billing.error) return <p className="text-sm text-red-600">{billing.error.message}</p>;
  return (
    <ul className="space-y-2 text-sm">
      {billing.data?.summaries.map((s) => (
        <li key={s.provider} className="flex justify-between rounded border p-2">
          <span>{s.provider}</span>
          <span>
            {(s.amount_cents / 100).toLocaleString(undefined, {
              style: "currency",
              currency: s.currency || "USD",
            })}
          </span>
        </li>
      ))}
      {billing.data?.summaries.length === 0 ? (
        <li className="text-sm text-muted-foreground">No billing providers configured.</li>
      ) : null}
    </ul>
  );
}
