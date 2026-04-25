"use client";

import { CloseOutlined, SendOutlined } from "@ant-design/icons";
import { Alert, Button, Drawer, Input, Space, Spin, Tag, Typography } from "antd";
import { useState } from "react";

import { useChatStream } from "@/lib/ws";
import { apiFetch } from "@/lib/api/client";
import { usePageContextStore } from "@/lib/store/page-context";
import { useUiStore } from "@/lib/store/ui";

import { ChatMessageList } from "./ChatMessageList";

const { Text } = Typography;

interface PendingTurn {
  prompt: string;
  task_id: string | null;
}

export function AssistantDrawer() {
  const open = useUiStore((s) => s.assistantOpen);
  const setOpen = useUiStore((s) => s.setAssistantOpen);
  const context = usePageContextStore((s) => s.context);
  const [prompt, setPrompt] = useState("");
  const [pending, setPending] = useState<PendingTurn | null>(null);
  const [history, setHistory] = useState<
    Array<{ role: "user" | "assistant"; content: string }>
  >([]);
  const [error, setError] = useState<string | null>(null);

  const stream = useChatStream(pending?.task_id ?? null);

  async function send() {
    const text = prompt.trim();
    if (!text || pending) return;
    setError(null);
    setHistory((h) => [...h, { role: "user", content: text }]);
    setPrompt("");
    try {
      const res = await apiFetch<{ task_id?: string; session_id?: string; content?: string }>(
        "/chat",
        {
          method: "POST",
          body: JSON.stringify({
            prompt: text,
            tier: "quick",
            context,
          }),
        },
      );
      if (res.content) {
        setHistory((h) => [...h, { role: "assistant", content: res.content as string }]);
      }
      setPending({ prompt: text, task_id: res.task_id ?? null });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setPending(null);
    }
  }

  if (stream.done && stream.text && !history.find((m) => m.content === stream.text)) {
    setHistory((h) => [...h, { role: "assistant", content: stream.text }]);
    setPending(null);
  }

  return (
    <Drawer
      open={open}
      onClose={() => setOpen(false)}
      title={
        <Space>
          <span>Assistant</span>
          {context.page ? <Tag>{context.page}</Tag> : null}
        </Space>
      }
      width={420}
      placement="right"
      closeIcon={<CloseOutlined />}
      styles={{ body: { display: "flex", flexDirection: "column", padding: 0 } }}
    >
      <div style={{ padding: 12, flex: 1, overflowY: "auto", minHeight: 0 }}>
        {history.length === 0 && !stream.text ? (
          <Text type="secondary">
            Ask anything about your strategies, backtests, or live data. Page context is sent
            automatically.
          </Text>
        ) : null}
        <ChatMessageList
          messages={history.concat(
            stream.text ? [{ role: "assistant", content: stream.text }] : [],
          )}
        />
        {pending && !stream.done ? (
          <div style={{ marginTop: 8 }}>
            <Spin size="small" /> <Text type="secondary">streaming…</Text>
          </div>
        ) : null}
        {error ? (
          <Alert type="error" message={error} style={{ marginTop: 12 }} closable />
        ) : null}
      </div>
      <div
        style={{
          borderTop: "1px solid var(--ant-color-border, #1f2937)",
          padding: 10,
          display: "flex",
          gap: 8,
        }}
      >
        <Input.TextArea
          autoSize={{ minRows: 1, maxRows: 6 }}
          placeholder="Ask the assistant…"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          disabled={Boolean(pending && !stream.done)}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={send}
          disabled={!prompt.trim() || Boolean(pending && !stream.done)}
        />
      </div>
    </Drawer>
  );
}
