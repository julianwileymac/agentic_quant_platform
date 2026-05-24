"use client";

import { use } from "react";
import { Button, Card, message } from "antd";
import { Square } from "lucide-react";

import { TaskStreamer } from "@/components/telemetry/TaskStreamer";
import { useStepUp, runWithStepUp } from "@/hooks/useStepUp";

export default function PaperRunDetailPage({
  params,
}: {
  params: Promise<{ taskId: string }>;
}) {
  const { taskId } = use(params);
  const { isSupported, requestStepUp } = useStepUp();

  async function stopRun() {
    try {
      await runWithStepUp(requestStepUp, isSupported, async () => {
        const res = await fetch(`/api/paper/${taskId}/stop`, {
          method: "POST",
          credentials: "include",
        });
        if (!res.ok) {
          const err = new Error(`stop failed: ${res.status}`);
          (err as Error & { headers?: Headers }).headers = res.headers;
          throw err;
        }
      });
      message.success("Stop signal sent");
    } catch (err) {
      message.error(err instanceof Error ? err.message : "Stop failed");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
            Paper run
          </h1>
          <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
            Task <code>{taskId}</code>
          </p>
        </div>
        <Button danger icon={<Square size={14} />} onClick={stopRun}>
          Stop run
        </Button>
      </header>

      <Card title="Live telemetry">
        <TaskStreamer taskId={taskId} />
      </Card>
    </div>
  );
}
