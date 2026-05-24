"use client";

import { use, useState } from "react";
import { Button, Card, Tabs, message } from "antd";
import { useQuery } from "@tanstack/react-query";
import { Play, Square } from "lucide-react";

import { StrategyForm } from "@/components/strategy/StrategyForm";
import { useStepUp, runWithStepUp } from "@/hooks/useStepUp";

interface Strategy {
  id: string;
  name: string;
  yaml: string;
  recipe: Record<string, unknown>;
  versions: { id: string; hash: string; created_at: string }[];
}

export default function StrategyDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const { isSupported, requestStepUp } = useStepUp();

  const { data, isLoading } = useQuery<Strategy>({
    queryKey: ["strategy", id],
    queryFn: async () => {
      const res = await fetch(`/api/strategies/${id}`, { credentials: "include" });
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
  });

  async function startPaperRun() {
    try {
      const taskId = await runWithStepUp(requestStepUp, isSupported, async () => {
        const res = await fetch(`/api/paper/${id}/start`, {
          method: "POST",
          credentials: "include",
        });
        if (!res.ok) {
          const err = new Error(`start failed: ${res.status}`);
          (err as Error & { headers?: Headers }).headers = res.headers;
          throw err;
        }
        const body = (await res.json()) as { task_id: string };
        return body.task_id;
      });
      setActiveTaskId(taskId);
      message.success("Paper run started");
    } catch (err) {
      message.error(err instanceof Error ? err.message : "Start failed");
    }
  }

  async function stopPaperRun() {
    if (!activeTaskId) return;
    try {
      const res = await fetch(`/api/paper/${activeTaskId}/stop`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) throw new Error(`stop failed: ${res.status}`);
      message.success("Paper run stopped");
      setActiveTaskId(null);
    } catch (err) {
      message.error(err instanceof Error ? err.message : "Stop failed");
    }
  }

  if (isLoading) {
    return (
      <div className="text-sm" style={{ color: "var(--text-muted)" }}>
        Loading strategy…
      </div>
    );
  }
  if (!data) {
    return (
      <div className="text-sm" style={{ color: "var(--text-muted)" }}>
        Strategy not found.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
            {data.name}
          </h1>
          <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
            Strategy <code>{data.id}</code> · {data.versions.length} version
            {data.versions.length === 1 ? "" : "s"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {activeTaskId ? (
            <Button danger icon={<Square size={14} />} onClick={stopPaperRun}>
              Stop paper run
            </Button>
          ) : (
            <Button type="primary" icon={<Play size={14} />} onClick={startPaperRun}>
              Start paper run
            </Button>
          )}
        </div>
      </header>

      <Tabs
        items={[
          {
            key: "editor",
            label: "Editor",
            children: (
              <StrategyForm
                initialYaml={data.yaml}
                initialJson={data.recipe}
                onSubmit={async ({ yamlText, json }) => {
                  const res = await fetch(`/api/strategies/${id}`, {
                    method: "PUT",
                    credentials: "include",
                    headers: { "content-type": "application/json" },
                    body: JSON.stringify({ yaml: yamlText, recipe: json }),
                  });
                  if (!res.ok) {
                    message.error(`Save failed: ${res.status}`);
                    return;
                  }
                  message.success("New version saved");
                }}
              />
            ),
          },
          {
            key: "versions",
            label: "Versions",
            children: (
              <Card>
                <ul className="space-y-2 text-sm" style={{ color: "var(--text-secondary)" }}>
                  {data.versions.map((v) => (
                    <li key={v.id} className="flex items-center justify-between">
                      <code style={{ color: "var(--text-muted)" }}>{v.hash.slice(0, 16)}</code>
                      <span>{v.created_at}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            ),
          },
          {
            key: "live",
            label: "Live telemetry",
            children: (
              <Card>
                <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
                  {activeTaskId ? (
                    <>
                      Streaming progress for task <code>{activeTaskId}</code> via the canonical
                      <code> /chat/stream/&#123;task_id&#125;</code> WebSocket. Telemetry frames
                      land in <code>useTelemetryStore</code>.
                    </>
                  ) : (
                    "Start a paper run above to begin streaming progress."
                  )}
                </div>
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
}
