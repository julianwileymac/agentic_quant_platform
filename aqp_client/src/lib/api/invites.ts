import { apiFetch } from "./client";
import { useApiMutation, useApiQuery } from "./hooks";

export interface Invite {
  id: string;
  email: string;
  org_id: string;
  role: string;
  status: string;
  created_at: string | null;
  expires_at: string;
  inviter_user_id: string | null;
  token_hint: string | null;
  [key: string]: unknown;
}

export interface InviteCreateResponse {
  id: string;
  raw_token: string;
  expires_at: string;
}

export interface AcceptInviteResponse {
  redirect_url: string;
  signup_screen_hint?: "signup";
}

export interface CreateInvitePayload {
  email: string;
  org_id: string;
  role?: string;
  scope_kind?: string;
  scope_id?: string;
}

export const inviteKeys = {
  root: ["tenancy", "invites"] as const,
  list: ["tenancy", "invites", "list"] as const,
};

export function useInvitesQuery(enabled = true) {
  return useApiQuery<Invite[]>({
    queryKey: inviteKeys.list,
    path: "/tenancy/invites",
    enabled,
  });
}

export function useCreateInviteMutation() {
  return useApiMutation<InviteCreateResponse, CreateInvitePayload>({
    path: "/tenancy/invites",
    method: "POST",
  });
}

export function useDeleteInviteMutation() {
  return useApiMutation<void, { id: string }>({
    path: ({ id }) => `/tenancy/invites/${encodeURIComponent(id)}`,
    method: "DELETE",
  });
}

export async function acceptInviteToken(token: string): Promise<AcceptInviteResponse> {
  return apiFetch<AcceptInviteResponse>(`/tenancy/invites/${encodeURIComponent(token)}/accept`, {
    method: "POST",
  });
}

export function useAcceptInviteMutation() {
  return useApiMutation<AcceptInviteResponse, { token: string }>({
    path: ({ token }) => `/tenancy/invites/${encodeURIComponent(token)}/accept`,
    method: "POST",
  });
}
