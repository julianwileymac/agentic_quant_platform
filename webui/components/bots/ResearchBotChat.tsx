"use client";

import { SendOutlined } from "@ant-design/icons";
import { App, Button, Card, Input, List, Space, Tag, Typography } from "antd";
import { useEffect, useState } from "react";

import { BotsApi } from "@/lib/api/bots";
import { useChatStream } from "@/lib/ws/useChatStream";

const { Text, Paragraph } = Typography;

interface ResearchBotChatProps {
  botRef: string;
}

interface ChatTurn {
  id: string;
  prompt: string;
  taskId: string;
  startedAt: number;
  reply?: string;
  status: "pending" | "running" | "done" | "error";
  error?: string;
}

/**
 * Chat panel for :class:`ResearchBot`. Posts each prompt to
 * ``POST /bots/{ref}/chat`` (which dispatches a Celery task that drives
 * :class:`AgentRuntime`) and renders the live stream from the existing
 * ``/chat/stream/{task_id}`` WebSocket transport.
 */
export function ResearchBotChat({ botRef }: ResearchBotChatProps) {
  const { message } = App.useApp();
  const [prompt, setPrompt] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const stream = useChatStream(activeTaskId);

  // Forward stream events into the active turn.
  useEffect(() => {
    if (!activeTaskId) return;
    setTurns((prev) =>
      prev.map((t) =>
        t.taskId === activeTaskId
          ? {
              ...t,
              status: stream.error ? "error" : stream.done ? "done" : "running",
              reply: pickReply(stream.events, stream.text),
              error: stream.error ?? undefined,
            }
          : t,
      ),
    );
  }, [activeTaskId, stream.events, stream.text, stream.done, stream.error]);

  async function send(): Promise<void> {
    const text = prompt.trim();
    if (!text) return;
    try {
      const ack = await BotsApi.chat(botRef, { prompt: text });
      const turn: ChatTurn = {
        id: ack.task_id,
        prompt: text,
        taskId: ack.task_id,
        startedAt: Date.now(),
        status: "pending",
      };
      setTurns((prev) => [...prev, turn]);
      setActiveTaskId(ack.task_id);
      setPrompt("");
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <Card size="small" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <List
        dataSource={turns}
        locale={{ emptyText: "Ask the bot anything to start a chat session." }}
        renderItem={(turn) => (
          <List.Item>
            <Space direction="vertical" style={{ width: "100%" }}>
              <Space>
                <Tag color="blue">prompt</Tag>
                <Text strong>{turn.prompt}</Text>
              </Space>
              <Space>
                <Tag color={turn.status === "error" ? "red" : turn.status === "done" ? "green" : "gold"}>
                  {turn.status}
                </Tag>
                {turn.taskId ? (
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    task {turn.taskId}
                  </Text>
                ) : null}
              </Space>
              {turn.error ? (
                <Text type="danger" style={{ fontSize: 12 }}>
                  {turn.error}
                </Text>
              ) : null}
              {turn.reply ? (
                <Paragraph
                  style={{ marginBottom: 0, whiteSpace: "pre-wrap", fontSize: 13 }}
                  copyable={{ tooltips: ["Copy reply", "Copied"] }}
                >
                  {turn.reply}
                </Paragraph>
              ) : null}
            </Space>
          </List.Item>
        )}
      />
      <Space.Compact style={{ width: "100%" }}>
        <Input.TextArea
          autoSize={{ minRows: 1, maxRows: 4 }}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Ask the research bot…"
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={send}
          disabled={!prompt.trim()}
        >
          Send
        </Button>
      </Space.Compact>
    </Card>
  );
}

function pickReply(events: ReturnType<typeof useChatStream>["events"], delta: string): string {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const ev = events[i];
    if (!ev) continue;
    if (ev.stage === "done" && ev.result) {
      const result = ev.result as { summary?: string; replies?: Record<string, unknown> };
      if (typeof result.summary === "string") return result.summary;
      if (result.replies) return JSON.stringify(result.replies, null, 2);
    }
  }
  return delta;
}
