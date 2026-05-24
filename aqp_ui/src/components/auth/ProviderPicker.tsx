"use client";

import { Building2, Mail, Microscope } from "lucide-react";

import { auth0LoginPath, entraLoginPath } from "@/lib/auth/paths";

interface ProviderPickerProps {
  mode: "signup" | "login";
  returnTo?: string;
  /** Set when an organization context is known (e.g. invite acceptance). */
  organization?: string;
  /** Disable providers that aren't configured for the current deployment. */
  auth0Enabled?: boolean;
  entraEnabled?: boolean;
}

/**
 * Renders the Auth0 (B2C) + Entra (B2B) provider picker.
 *
 * - Auth0 button drives the self-signup path. On the signup page it
 *   passes `screen_hint=signup`; on login it passes `screen_hint=login`.
 * - Entra button drives the enterprise SSO path against the customer's
 *   own tenant. AGENTS rule 44 keeps the EntraTenantLink wizard in
 *   front of any actual organization provisioning.
 */
export function ProviderPicker({
  mode,
  returnTo,
  organization,
  auth0Enabled = true,
  entraEnabled = true,
}: ProviderPickerProps) {
  const verb = mode === "signup" ? "Sign up" : "Log in";

  return (
    <div className="flex flex-col gap-3">
      {auth0Enabled ? (
        <a
          href={auth0LoginPath({ screenHint: mode, returnTo, organization })}
          className="flex items-center justify-center gap-2 rounded-md border px-4 py-3 text-sm font-semibold transition-colors hover:bg-white/5"
          style={{
            borderColor: "var(--border-default)",
            background: "var(--accent-primary)",
            color: "white",
          }}
        >
          <Mail size={16} />
          {verb} with email
        </a>
      ) : null}

      {entraEnabled ? (
        <a
          href={entraLoginPath({ screenHint: mode, returnTo })}
          className="flex items-center justify-center gap-2 rounded-md border px-4 py-3 text-sm font-semibold transition-colors hover:bg-white/5"
          style={{
            borderColor: "var(--border-default)",
            background: "var(--bg-elevated)",
            color: "var(--text-primary)",
          }}
        >
          <Building2 size={16} />
          {verb} with Microsoft (Entra ID)
        </a>
      ) : null}

      {!auth0Enabled && !entraEnabled ? (
        <div
          className="rounded-md border px-4 py-3 text-sm"
          style={{
            borderColor: "var(--warn-fg)",
            background: "rgba(245, 158, 11, 0.08)",
            color: "var(--warn-fg)",
          }}
        >
          <div className="flex items-center gap-2">
            <Microscope size={14} />
            <span>
              No identity provider is configured. Set <code>AUTH0_*</code> or
              <code>ENTRA_*</code> env vars to enable authentication.
            </span>
          </div>
        </div>
      ) : null}
    </div>
  );
}
