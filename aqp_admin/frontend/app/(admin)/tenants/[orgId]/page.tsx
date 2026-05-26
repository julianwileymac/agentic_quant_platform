"use client";

import { useQuery } from "@tanstack/react-query";
import { use } from "react";

import { adminGet } from "@/lib/api/client";

export default function TenantDetailPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = use(params);
  const { data } = useQuery({
    queryKey: ["admin", "tenants", orgId],
    queryFn: () => adminGet<Record<string, unknown>>(`/tenants/${orgId}`),
  });
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Tenant {orgId}</h1>
      <pre className="rounded-md border bg-white p-4 text-xs">
        {JSON.stringify(data ?? {}, null, 2)}
      </pre>
    </div>
  );
}
