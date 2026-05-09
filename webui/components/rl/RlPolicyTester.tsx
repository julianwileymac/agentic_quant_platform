"use client";

import { App, Button, Card, Form, Input, Space } from "antd";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useChatStream } from "@/lib/ws";

export function RlPolicyTester({ runId }: { runId: string }) {
  const { message } = App.useApp();
  const [checkpoint, setCheckpoint] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);
  const stream = useChatStream(taskId);

  async function trigger() {
    if (!checkpoint) {
      message.error("Checkpoint path is required.");
      return;
    }
    try {
      const res = await apiFetch<{ task_id: string }>(`/rl/runs/${runId}/replay`, {
        method: "POST",
        body: JSON.stringify({
          checkpoint,
          new_window: { kwargs: { start, end } },
        }),
      });
      setTaskId(res.task_id);
      message.success(`Replay queued (${res.task_id})`);
    } catch (err) {
      message.error(`Replay failed: ${(err as Error).message}`);
    }
  }

  return (
    <PageContainer title="Quick policy tester" subtitle="Re-roll a saved checkpoint on a new window.">
      <Card size="small">
        <Form layout="vertical" style={{ maxWidth: 480 }}>
          <Form.Item label="Checkpoint path">
            <Input value={checkpoint} onChange={(e) => setCheckpoint(e.target.value)} placeholder="/data/models/rl/.../policy.zip" />
          </Form.Item>
          <Form.Item label="Start (YYYY-MM-DD)">
            <Input value={start} onChange={(e) => setStart(e.target.value)} />
          </Form.Item>
          <Form.Item label="End (YYYY-MM-DD)">
            <Input value={end} onChange={(e) => setEnd(e.target.value)} />
          </Form.Item>
          <Space>
            <Button type="primary" onClick={trigger}>
              Run rollout
            </Button>
          </Space>
        </Form>
      </Card>
      {taskId ? (
        <Card size="small" style={{ marginTop: 12 }} title="Stream">
          <pre style={{ fontSize: 11, maxHeight: 200, overflow: "auto", margin: 0 }}>
            {stream.events.map((e, i) => `[${i}] ${JSON.stringify(e)}`).join("\n") || "Waiting…"}
          </pre>
        </Card>
      ) : null}
    </PageContainer>
  );
}
