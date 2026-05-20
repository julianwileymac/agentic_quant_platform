import { Cog, ExternalLink, Power } from "lucide-react";
import { Link } from "react-router-dom";

import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useApiQuery } from "@/lib/api/hooks";
import type { ProviderControl } from "@/lib/api/providers";
import { useTenancyStore } from "@/store/tenancy";
import { useUiStore } from "@/store/ui";

export function SettingsRoute() {
  const themeMode = useUiStore((s) => s.themeMode);
  const toggleTheme = useUiStore((s) => s.toggleTheme);
  const mode = useTenancyStore((s) => s.mode);
  const setMode = useTenancyStore((s) => s.setMode);

  const control = useApiQuery<ProviderControl>({
    queryKey: ["agentic", "provider-control"],
    path: "/agentic/provider-control",
    refetchInterval: 30_000,
  });

  const env = import.meta.env;

  return (
    <PageContainer
      title="Settings"
      subtitle="Local UI preferences, runtime endpoints, and provider control summary."
    >
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Cog className="h-4 w-4" /> Appearance
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <Row
              label="Dark mode"
              hint="Bloomberg-terminal-grade contrast for prolonged trading sessions."
              control={
                <Switch checked={themeMode === "dark"} onCheckedChange={() => toggleTheme()} />
              }
            />
            <Row
              label="Sandbox mode"
              hint="Amber outline + tab-title prefix; orders route through paper / sandbox brokers only."
              control={
                <Switch
                  checked={mode !== "live"}
                  onCheckedChange={(c) => setMode(c ? "paper" : "live")}
                />
              }
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Endpoints</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 text-xs">
            <EndpointRow label="API" value={env.VITE_API_URL ?? "(proxied via /aqp-api)"} />
            <EndpointRow label="WebSocket" value={env.VITE_WS_URL ?? "(proxied via /aqp-ws)"} />
            <EndpointRow label="Dash" value={env.VITE_DASH_URL ?? "—"} />
            <EndpointRow label="MLflow" value={env.VITE_MLFLOW_URL ?? "—"} />
            <EndpointRow label="Jaeger" value={env.VITE_JAEGER_URL ?? "—"} />
            <EndpointRow label="Superset" value={env.VITE_SUPERSET_URL ?? "—"} />
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Power className="h-4 w-4" /> Provider control
            </CardTitle>
            <Link className="text-xs text-[var(--info-fg)] underline" to="/models">
              Models & Providers <ExternalLink className="inline h-3 w-3" />
            </Link>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
            <ProviderRow label="Active provider" value={control.data?.provider ?? "—"} />
            <ProviderRow label="Deep model" value={control.data?.deep_model ?? "—"} />
            <ProviderRow label="Quick model" value={control.data?.quick_model ?? "—"} />
            <div className="flex flex-col gap-1">
              <span className="text-[10px] uppercase tracking-wider text-[var(--text-secondary)]">
                Online
              </span>
              <div className="flex gap-2">
                <Badge variant={control.data?.ollama_online ? "positive" : "secondary"}>
                  Ollama
                </Badge>
                <Badge variant={control.data?.vllm_online ? "positive" : "secondary"}>vLLM</Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}

function Row({ label, hint, control }: { label: string; hint?: string; control: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3">
      <div className="flex flex-col">
        <Label>{label}</Label>
        {hint ? <span className="text-[10px] text-[var(--text-secondary)]">{hint}</span> : null}
      </div>
      {control}
    </div>
  );
}

function EndpointRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <code className="rounded bg-[var(--bg-app)] px-1 font-mono text-[10px]">{value}</code>
    </div>
  );
}

function ProviderRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wider text-[var(--text-secondary)]">
        {label}
      </span>
      <span className="font-mono text-xs">{value}</span>
    </div>
  );
}
