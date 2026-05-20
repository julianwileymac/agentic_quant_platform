import { Bot, RefreshCcw } from "lucide-react";

import { DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";
import type { LlmProfile, ProviderControl } from "@/lib/api/providers";

export function ModelsProvidersRoute() {
  const control = useApiQuery<ProviderControl>({
    queryKey: ["agentic", "provider-control"],
    path: "/agentic/provider-control",
    refetchInterval: 30_000,
  });
  const profiles = useApiQuery<LlmProfile[]>({
    queryKey: ["llm", "providers"],
    path: "/llm/providers",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  const c = control.data;

  return (
    <PageContainer
      title="Models & Providers"
      subtitle="LLM provider runtime status and registered profiles. Read-only; routing decisions live in the LiteLLM router."
      extra={
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            control.refetch();
            profiles.refetch();
          }}
        >
          <RefreshCcw className="h-4 w-4" /> Refresh
        </Button>
      }
    >
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        <ProviderCard
          title="Active provider"
          status="info"
          headline={c?.provider ?? "—"}
          rows={[
            { label: "Deep model", value: c?.deep_model ?? "—" },
            { label: "Quick model", value: c?.quick_model ?? "—" },
          ]}
        />
        <ProviderCard
          title="Ollama"
          status={c?.ollama_online ? "positive" : c ? "negative" : "info"}
          headline={c?.ollama_host ?? "—"}
          rows={[
            { label: "Online", value: c ? (c.ollama_online ? "yes" : "no") : "—" },
            {
              label: "Models",
              value: c?.ollama_models?.length ?? 0,
              modelList: c?.ollama_models,
            },
          ]}
        />
        <ProviderCard
          title="vLLM"
          status={c?.vllm_online ? "positive" : c ? "negative" : "info"}
          headline={c?.vllm_base_url ?? "—"}
          rows={[
            { label: "Online", value: c ? (c.vllm_online ? "yes" : "no") : "—" },
            {
              label: "Models",
              value: c?.vllm_models?.length ?? 0,
              modelList: c?.vllm_models,
            },
          ]}
        />
      </div>

      <Card className="mt-4 h-[40vh]">
        <CardHeader>
          <CardTitle>LLM profiles</CardTitle>
          <Badge variant="secondary">{profiles.data?.length ?? 0}</Badge>
        </CardHeader>
        <CardContent className="h-full p-0">
          <DataTable<LlmProfile>
            rows={profiles.data ?? []}
            rowKey={(p) => p.name}
            emptyState={
              profiles.isPending ? (
                <span>Loading profiles…</span>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <Bot className="h-6 w-6" />
                  <span>No profiles registered.</span>
                </div>
              )
            }
            columns={[
              { key: "name", header: "Profile", render: (p) => <span className="font-mono">{p.name}</span> },
              { key: "provider", header: "Provider", width: 140, render: (p) => <Badge variant="secondary">{p.provider}</Badge> },
              { key: "model", header: "Model", render: (p) => <span className="font-mono text-xs">{p.model}</span> },
              {
                key: "enabled",
                header: "Enabled",
                width: 100,
                render: (p) => (
                  <Badge variant={p.enabled ? "positive" : "secondary"}>{p.enabled ? "yes" : "no"}</Badge>
                ),
              },
              {
                key: "description",
                header: "Description",
                render: (p) => (
                  <span className="text-xs text-[var(--text-secondary)]">{p.description ?? "—"}</span>
                ),
              },
            ]}
          />
        </CardContent>
      </Card>
    </PageContainer>
  );
}

interface ProviderCardProps {
  title: string;
  status: "positive" | "negative" | "info";
  headline: string;
  rows: Array<{ label: string; value: string | number; modelList?: string[] | undefined }>;
}

function ProviderCard({ title, status, headline, rows }: ProviderCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <Badge variant={status === "positive" ? "positive" : status === "negative" ? "negative" : "secondary"}>
          {status === "positive" ? "online" : status === "negative" ? "offline" : "—"}
        </Badge>
      </CardHeader>
      <CardContent>
        <div className="mb-2 break-words font-mono text-xs">{headline}</div>
        <dl className="grid gap-1 text-xs">
          {rows.map((r) => (
            <div key={r.label} className="flex items-start justify-between gap-3">
              <dt className="text-[var(--text-secondary)]">{r.label}</dt>
              <dd className="text-right font-mono">
                {typeof r.value === "number" ? (
                  <Numeric value={r.value} kind="integer" digits={0} color="neutral" />
                ) : (
                  r.value
                )}
                {r.modelList && r.modelList.length > 0 ? (
                  <div className="mt-1 flex flex-wrap justify-end gap-1">
                    {r.modelList.slice(0, 4).map((m) => (
                      <Badge key={m} variant="outline" className="text-[9px]">
                        {m}
                      </Badge>
                    ))}
                    {r.modelList.length > 4 ? (
                      <span className="text-[9px] text-[var(--text-muted)]">+{r.modelList.length - 4}</span>
                    ) : null}
                  </div>
                ) : null}
              </dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}
