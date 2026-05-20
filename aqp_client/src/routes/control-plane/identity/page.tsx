import { useEffect, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api/client";
import { controlPlaneApi, type ControlPlaneIdentityStatus } from "@/lib/api/controlPlane";
import { authConfig, useAuth } from "@/lib/auth";

export function ControlPlaneIdentityRoute() {
  const auth = useAuth();
  const [identity, setIdentity] = useState<ControlPlaneIdentityStatus | null>(null);
  const [whoami, setWhoami] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    void apiFetch<Record<string, unknown>>("/auth/whoami").then(setWhoami).catch(() => setWhoami(null));
    void controlPlaneApi.getIdentityStatus().then(setIdentity).catch(() => setIdentity(null));
  }, []);

  return (
    <PageContainer title="Identity Control Plane" subtitle="OIDC, Auth0, Entra, and SCIM provisioning status.">
      <div className="grid gap-3 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>OIDC / Auth Provider</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label="Required" value={String(identity?.required ?? authConfig.required)} />
            <Row label="Configured" value={String(authConfig.enabled)} />
            <Row label="Provider" value={identity?.provider ?? authConfig.provider} />
            <Row label="Audience" value={identity?.oidc_audience || authConfig.audience || "—"} />
            <Row label="Issuer / Domain" value={identity?.oidc_issuer || authConfig.domain || "—"} />
            <Row label="Authenticated" value={String(auth.isAuthenticated)} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>SCIM 2.0</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label="Endpoint" value={identity?.scim_endpoint ?? "/scim/v2"} />
            <Row label="Enabled" value={identity?.scim_enabled ? "yes" : "no / disabled"} />
            <Row label="Patch" value={String(identity?.scim_patch_supported ?? false)} />
            <Row label="Current user" value={String(whoami?.email ?? "—")} />
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <code className="text-right">{value}</code>
    </div>
  );
}
