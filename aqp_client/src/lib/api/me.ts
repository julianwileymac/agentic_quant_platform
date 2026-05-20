import { useMutation } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { useApiMutation, useApiQuery } from "./hooks";

export interface MeProfile {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  picture: string | null;
  auth_provider: string;
  auth_subject: string | null;
  created_at: string | null;
  updated_at: string | null;
  [key: string]: unknown;
}

export type MfaFactorType =
  | "totp"
  | "sms"
  | "webauthn-roaming"
  | "webauthn-platform"
  | "recovery-code"
  | "push";

export interface MfaFactor {
  id: string;
  type: MfaFactorType;
  name: string | null;
  enrolled_at: string;
  confirmed: boolean;
  phone_number: string | null;
}

export interface Session {
  id: string;
  user_id: string;
  created_at: string;
  updated_at: string;
  last_activity: string | null;
  ip: string | null;
  user_agent: string | null;
  device: string | null;
  location: string | null;
}

export interface MfaEnrollment {
  ticket_id: string;
  ticket_url: string;
  qr_code_url: string | null;
  secret: string | null;
  recovery_codes: string[];
  expires_at: string;
}

export interface ConnectedAccount {
  provider: string;
  connection: string;
  user_id: string;
  profile_data: Record<string, unknown>;
  is_primary: boolean;
}

export interface AuditEvent {
  id: string;
  date: string;
  event_type: string;
  event_category: "authn" | "authz" | "account" | "tenancy" | "safety";
  severity: "info" | "warning" | "critical";
  source: string;
  ip: string | null;
  user_agent: string | null;
  connection: string | null;
  details: Record<string, unknown>;
}

export interface AuditPage {
  events: AuditEvent[];
  total: number;
  page: number;
  per_page: number;
}

export interface DeleteMeResponse {
  status: "deleted";
}

export interface ChangePasswordResponse {
  ticket_url: string;
  expires_at: string;
}

export interface LinkConnectedAccountResponse {
  link_url: string;
  state: string;
}

export interface RevokeAllSessionsResponse {
  revoked: number;
}

export interface UpdateMePayload {
  display_name?: string;
  avatar_url?: string;
  picture?: string;
}

export const meKeys = {
  root: ["me"] as const,
  profile: ["me", "profile"] as const,
  mfaFactors: ["me", "mfa", "factors"] as const,
  sessions: ["me", "sessions"] as const,
  connectedAccounts: ["me", "connected-accounts"] as const,
  audit: (perPage: number, page: number) => ["me", "audit", perPage, page] as const,
};

export function useMeProfileQuery(enabled = true) {
  return useApiQuery<MeProfile>({
    queryKey: meKeys.profile,
    path: "/me",
    enabled,
  });
}

export function useUpdateMeProfileMutation() {
  return useApiMutation<MeProfile, UpdateMePayload>({
    path: "/me",
    method: "PATCH",
  });
}

export function useChangePasswordMutation() {
  return useApiMutation<ChangePasswordResponse, Record<string, never>>({
    path: "/me/change-password",
    method: "POST",
  });
}

export function useMfaFactorsQuery(enabled = true) {
  return useApiQuery<MfaFactor[]>({
    queryKey: meKeys.mfaFactors,
    path: "/me/mfa/factors",
    enabled,
  });
}

export function useEnrollMfaMutation() {
  return useApiMutation<
    MfaEnrollment,
    { factor: "totp" | "sms" | "webauthn-roaming" | "webauthn-platform" }
  >({
    path: "/me/mfa/enroll",
    method: "POST",
  });
}

export function useDeleteMfaFactorMutation() {
  return useApiMutation<void, { id: string }>({
    path: ({ id }) => `/me/mfa/factors/${encodeURIComponent(id)}`,
    method: "DELETE",
  });
}

export function useSessionsQuery(enabled = true) {
  return useApiQuery<Session[]>({
    queryKey: meKeys.sessions,
    path: "/me/sessions",
    enabled,
  });
}

export function useRevokeSessionMutation() {
  return useApiMutation<void, { id: string }>({
    path: ({ id }) => `/me/sessions/${encodeURIComponent(id)}`,
    method: "DELETE",
  });
}

export function useRevokeAllSessionsMutation() {
  return useApiMutation<RevokeAllSessionsResponse, Record<string, never>>({
    path: "/me/sessions",
    method: "DELETE",
  });
}

export function useConnectedAccountsQuery(enabled = true) {
  return useApiQuery<ConnectedAccount[]>({
    queryKey: meKeys.connectedAccounts,
    path: "/me/connected-accounts",
    enabled,
  });
}

export function useLinkConnectedAccountMutation() {
  return useApiMutation<
    LinkConnectedAccountResponse,
    { provider?: string; connection?: string } | Record<string, never>
  >({
    path: "/me/connected-accounts/link",
    method: "POST",
  });
}

export function useUnlinkConnectedAccountMutation() {
  return useMutation<void, Error, { secondary_user_id: string; provider: string }>({
    mutationFn: async ({ secondary_user_id, provider }) =>
      apiFetch<void>(`/me/connected-accounts/${encodeURIComponent(secondary_user_id)}`, {
        method: "DELETE",
        body: JSON.stringify({ provider }),
      }),
  });
}

export function useMeAuditQuery(perPage = 50, page = 0, enabled = true) {
  return useApiQuery<AuditPage>({
    queryKey: meKeys.audit(perPage, page),
    path: "/me/audit",
    query: { per_page: perPage, page },
    enabled,
  });
}

export function useDeleteMeMutation() {
  return useMutation<DeleteMeResponse, Error, { confirmEmail: string }>({
    mutationFn: async ({ confirmEmail }) =>
      apiFetch<DeleteMeResponse>("/me", {
        method: "DELETE",
        headers: { "X-AQP-Confirm-Email": confirmEmail },
      }),
  });
}
