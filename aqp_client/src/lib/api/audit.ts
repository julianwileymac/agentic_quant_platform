import { apiFetch } from "./client";
import { useApiQuery } from "./hooks";
import type { AuditEvent } from "./me";

export interface TenantAuditPage {
  events: AuditEvent[];
  total: number;
  page: number;
  per_page: number;
}

export interface TenantAuditQuery {
  org_id?: string;
  per_page?: number;
  page?: number;
}

export const auditKeys = {
  tenancy: (query: TenantAuditQuery) =>
    [
      "tenancy",
      "audit",
      query.org_id ?? "",
      query.per_page ?? 50,
      query.page ?? 0,
    ] as const,
};

export async function getTenantAudit(query: TenantAuditQuery): Promise<TenantAuditPage> {
  return apiFetch<TenantAuditPage>("/tenancy/audit", {
    query: {
      org_id: query.org_id,
      per_page: query.per_page ?? 50,
      page: query.page ?? 0,
    },
  });
}

export function useTenantAuditQuery(query: TenantAuditQuery, enabled = true) {
  return useApiQuery<TenantAuditPage>({
    queryKey: auditKeys.tenancy(query),
    path: "/tenancy/audit",
    query: {
      org_id: query.org_id,
      per_page: query.per_page ?? 50,
      page: query.page ?? 0,
    },
    enabled,
  });
}
