import { Link2 } from "lucide-react";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  meKeys,
  useConnectedAccountsQuery,
  useLinkConnectedAccountMutation,
  useUnlinkConnectedAccountMutation,
} from "@/lib/api/me";
import { toast } from "@/components/ui/toast";

const DEFAULT_CONNECTIONS = [
  "azure-ad-myorg",
  "google-oauth2",
  "github",
  "apple",
  "linkedin",
];

function ProviderGlyph({ provider }: { provider: string }) {
  const normalized = provider.toLowerCase();
  if (normalized.includes("google")) {
    return (
      <span className="inline-flex size-6 items-center justify-center rounded-full bg-[#4285F4] text-xs font-semibold text-white">
        G
      </span>
    );
  }
  if (normalized.includes("azure") || normalized.includes("microsoft")) {
    return (
      <span className="inline-flex size-6 items-center justify-center rounded-full bg-[#0078D4] text-xs font-semibold text-white">
        M
      </span>
    );
  }
  return (
    <span className="inline-flex size-6 items-center justify-center rounded-full bg-[var(--bg-elevated)] text-xs font-semibold">
      {provider.slice(0, 1).toUpperCase()}
    </span>
  );
}

export function ConnectionsTab() {
  const queryClient = useQueryClient();
  const connectionsQuery = useConnectedAccountsQuery();
  const linkMutation = useLinkConnectedAccountMutation();
  const unlinkMutation = useUnlinkConnectedAccountMutation();
  const [selectedConnection, setSelectedConnection] = useState(
    DEFAULT_CONNECTIONS[0] ?? "azure-ad-myorg",
  );

  const handleLink = async () => {
    try {
      const data = await linkMutation.mutateAsync({ connection: selectedConnection });
      window.location.assign(data.link_url);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to start account linking.");
    }
  };

  const handleUnlink = async (secondaryUserId: string, provider: string) => {
    try {
      await unlinkMutation.mutateAsync({
        secondary_user_id: secondaryUserId,
        provider,
      });
      await queryClient.invalidateQueries({ queryKey: meKeys.connectedAccounts });
      toast.success("Connected account removed.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to unlink account.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Connections</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          {(connectionsQuery.data ?? []).map((account) => {
            const email =
              typeof account.profile_data.email === "string"
                ? account.profile_data.email
                : "Email unavailable";
            return (
              <div
                key={`${account.provider}-${account.user_id}`}
                className="flex items-center justify-between rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  <ProviderGlyph provider={account.provider} />
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{account.provider}</div>
                    <div className="truncate text-xs text-[var(--text-secondary)]">{email}</div>
                  </div>
                </div>
                {account.is_primary ? (
                  <span className="text-xs text-[var(--text-secondary)]">Primary</span>
                ) : (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="border-[var(--neg-fg)] text-[var(--neg-fg)]"
                    onClick={() => void handleUnlink(account.user_id, account.provider)}
                  >
                    Unlink
                  </Button>
                )}
              </div>
            );
          })}
          {(connectionsQuery.data ?? []).length === 0 ? (
            <div className="text-sm text-[var(--text-secondary)]">No connected accounts yet.</div>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={selectedConnection}
            onChange={(event) => setSelectedConnection(event.target.value)}
            className="h-9 min-w-[220px] rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm"
          >
            {DEFAULT_CONNECTIONS.map((provider) => (
              <option key={provider} value={provider}>
                {provider}
              </option>
            ))}
          </select>
          <Button type="button" onClick={() => void handleLink()} disabled={linkMutation.isPending}>
            <Link2 className="size-4" />
            Link another account
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
