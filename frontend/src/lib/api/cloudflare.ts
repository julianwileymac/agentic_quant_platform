/**
 * Typed REST client for `/cloudflare/*` (Phase D of the Management
 * Engine). Backs the new `frontend/src/routes/cloudflare/page.tsx`
 * tunnel + DNS + Access app studio.
 */
import { apiFetch } from "./client";

export interface CloudflareHealth {
  status: string;
  account_id?: string;
  token_id?: string;
  token_status?: string;
  error?: string;
}

export interface TunnelSummary {
  id: string;
  name: string;
  status: string;
  config_src: string;
  created_at: string;
  deleted_at?: string | null;
  connections: number;
  metadata?: Record<string, unknown>;
}

export interface DnsRecordSummary {
  id: string;
  zone_id: string;
  name: string;
  type: string;
  content: string;
  ttl: number;
  proxied: boolean;
  comment: string;
}

export interface AccessAppSummary {
  id: string;
  name: string;
  domain: string;
  type: string;
  aud: string;
  session_duration: string;
  auto_redirect_to_identity: boolean;
}

export interface IngressRule {
  hostname: string;
  service: string;
}

export async function cloudflareHealth(): Promise<CloudflareHealth> {
  return apiFetch<CloudflareHealth>("/cloudflare/health");
}

export async function listTunnels(name?: string): Promise<TunnelSummary[]> {
  const qs = name ? `?name=${encodeURIComponent(name)}` : "";
  return apiFetch<TunnelSummary[]>(`/cloudflare/tunnels${qs}`);
}

export async function createTunnel(
  name: string,
  configSrc: "cloudflare" | "local" = "cloudflare",
): Promise<TunnelSummary> {
  return apiFetch<TunnelSummary>("/cloudflare/tunnels", {
    method: "POST",
    body: JSON.stringify({ name, config_src: configSrc }),
  });
}

export async function deleteTunnel(tunnelId: string): Promise<{ deleted: boolean }> {
  return apiFetch(`/cloudflare/tunnels/${encodeURIComponent(tunnelId)}`, {
    method: "DELETE",
  });
}

export async function getTunnelConfig(tunnelId: string): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(
    `/cloudflare/tunnels/${encodeURIComponent(tunnelId)}/config`,
  );
}

export async function putTunnelConfig(
  tunnelId: string,
  ingress: IngressRule[],
): Promise<{ tunnel_id: string; rules: number }> {
  return apiFetch(`/cloudflare/tunnels/${encodeURIComponent(tunnelId)}/config`, {
    method: "PUT",
    body: JSON.stringify({ ingress }),
  });
}

export async function listAccessApps(): Promise<AccessAppSummary[]> {
  return apiFetch<AccessAppSummary[]>("/cloudflare/access/apps");
}

export async function putAccessApp(
  payload: Record<string, unknown>,
): Promise<AccessAppSummary> {
  return apiFetch<AccessAppSummary>("/cloudflare/access/apps", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function listDnsRecords(
  zoneId: string,
  name?: string,
): Promise<DnsRecordSummary[]> {
  const qs = name ? `?name=${encodeURIComponent(name)}` : "";
  return apiFetch<DnsRecordSummary[]>(
    `/cloudflare/dns/${encodeURIComponent(zoneId)}/records${qs}`,
  );
}

export async function putDnsRecord(
  zoneId: string,
  payload: Record<string, unknown>,
): Promise<DnsRecordSummary> {
  return apiFetch<DnsRecordSummary>(
    `/cloudflare/dns/${encodeURIComponent(zoneId)}/records`,
    { method: "PUT", body: JSON.stringify(payload) },
  );
}

export async function deleteDnsRecord(
  zoneId: string,
  recordId: string,
): Promise<{ deleted: boolean }> {
  return apiFetch(
    `/cloudflare/dns/${encodeURIComponent(zoneId)}/records/${encodeURIComponent(recordId)}`,
    { method: "DELETE" },
  );
}
