"use client";

import { DeleteOutlined, PlusOutlined, SendOutlined } from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Empty,
  Input,
  List,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { usePageContextStore } from "@/lib/store/page-context";
import { useChatStream } from "@/lib/ws";

import { ChatMessageList } from "./ChatMessageList";

const { Text, Title } = Typography;

interface ThreadSummary {
  id: string;
  title?: string | null;
  created_at?: string;
  message_count?: number;
}

interface MessageRow {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  meta?: Record<string, unknown> | null;
  created_at?: string;
}

export function ChatPage() {
  const { message } = App.useApp();
  const context = usePageContextStore((s) => s.context);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [tier, setTier] = useState<"quick" | "deep">("quick");
  const [prompt, setPrompt] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const stream = useChatStream(taskId);

  const threads = useApiQuery<ThreadSummary[]>({
    queryKey: ["chat", "threads"],
    path: "/chat/threads",
    select: (raw) => (Array.isArray(raw) ? (raw as ThreadSummary[]) : []),
  });

  const history = useApiQuery<MessageRow[]>({
    queryKey: ["chat", "messages", threadId ?? ""],
    path: threadId ? `/chat/sessions/${threadId}/messages` : "/chat/threads",
    enabled: Boolean(threadId),
    select: (raw) => (Array.isArray(raw) ? (raw as MessageRow[]) : []),
  });

  const merged = useMemo(() => {
    const base = (history.data ?? []).map((m) => ({
      role: (m.role === "tool" ? "assistant" : m.role) as "user" | "assistant" | "system",
      content: m.content,
    }));
    if (pending) base.push({ role: "user", content: pending });
    if (stream.text) base.push({ role: "assistant", content: stream.text });
    return base;
  }, [history.data, pending, stream.text]);

  useEffect(() => {
    if (stream.done) {
      setPending(null);
      history.refetch();
      threads.refetch();
    }
  }, [stream.done, history, threads]);

  async function send() {
    const text = prompt.trim();
    if (!text || pending) return;
    setPrompt("");
    setPending(text);
    try {
      const res = await apiFetch<{
        session_id?: string;
        content?: string;
        task_id?: string;
      }>("/chat", {
        method: "POST",
        body: JSON.stringify({
          prompt: text,
          session_id: threadId,
          tier,
          context,
        }),
      });
      if (res.session_id && !threadId) setThreadId(res.session_id);
      setTaskId(res.task_id ?? null);
      if (!res.task_id && res.content) {
        setPending(null);
        history.refetch();
        threads.refetch();
      }
    } catch (err) {
      setPending(null);
      message.error((err as Error).message);
    }
  }

  async function newThread() {
    setThreadId(null);
    setTaskId(null);
    setPending(null);
    setPrompt("");
  }

  async function removeThread(id: string) {
    try {
      await apiFetch(`/chat/threads/${id}`, { method: "DELETE" });
      message.success("Thread deleted");
      if (threadId === id) setThreadId(null);
      threads.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title="Chat"
      subtitle="Talk to the platform assistant. Threads persist server-side."
      extra={
        <Space>
          <Select
            value={tier}
            onChange={(v) => setTier(v)}
            options={[
              { value: "quick", label: "Quick model" },
              { value: "deep", label: "Deep model" },
            ]}
            style={{ width: 160 }}
          />
          <Button icon={<PlusOutlined />} onClick={newThread}>
            New thread
          </Button>
        </Space>
      }
    >
      <Row gutter={16} style={{ height: "calc(100vh - 200px)" }}>
        <Col xs={24} md={7} style={{ height: "100%" }}>
          <Card title="Threads" size="small" style={{ height: "100%" }} styles={{ body: { padding: 0, height: "calc(100% - 38px)", overflowY: "auto" } }}>
            {threads.isLoading ? (
              <Spin style={{ margin: 24 }} />
            ) : (threads.data ?? []).length === 0 ? (
              <Empty description="No threads yet" style={{ padding: 24 }} />
            ) : (
              <List
                dataSource={threads.data ?? []}
                renderItem={(t) => (
                  <List.Item
                    onClick={() => setThreadId(t.id)}
                    style={{
                      padding: "8px 12px",
                      cursor: "pointer",
                      background:
                        threadId === t.id
                          ? "var(--ant-color-bg-elevated)"
                          : "transparent",
                    }}
                    actions={[
                      <Button
                        key="del"
                        type="text"
                        size="small"
                        icon={<DeleteOutlined />}
                        danger
                        onClick={(e) => {
                          e.stopPropagation();
                          removeThread(t.id);
                        }}
                      />,
                    ]}
                  >
                    <div style={{ width: "100%" }}>
                      <Text strong style={{ fontSize: 13 }}>
                        {t.title ?? t.id.slice(0, 8)}
                      </Text>
                      <div style={{ fontSize: 11, opacity: 0.6 }}>
                        {t.message_count ?? 0} messages
                      </div>
                    </div>
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} md={17} style={{ height: "100%" }}>
          <Card
            title={
              <Space>
                <Title level={5} style={{ margin: 0 }}>
                  {threadId ? `Thread ${threadId.slice(0, 8)}` : "New conversation"}
                </Title>
                {context.page ? <Tag>{context.page}</Tag> : null}
                {context.vt_symbol ? <Tag color="blue">{context.vt_symbol}</Tag> : null}
                {context.backtest_id ? <Tag color="purple">backtest</Tag> : null}
                {stream.status === "open" ? <Tag color="green">streaming</Tag> : null}
              </Space>
            }
            size="small"
            style={{ height: "100%", display: "flex", flexDirection: "column" }}
            styles={{ body: { padding: 12, flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" } }}
          >
            <div style={{ flex: 1, overflowY: "auto", paddingRight: 6 }}>
              {merged.length === 0 ? (
                <Empty description="Start a conversation" />
              ) : (
                <ChatMessageList messages={merged} />
              )}
              {stream.error ? <Alert type="error" message={stream.error} style={{ marginTop: 8 }} /> : null}
            </div>
            <div
              style={{
                borderTop: "1px solid var(--ant-color-border)",
                paddingTop: 8,
                marginTop: 8,
                display: "flex",
                gap: 8,
              }}
            >
              <Input.TextArea
                autoSize={{ minRows: 1, maxRows: 8 }}
                placeholder="Type a message…"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onPressEnter={(e) => {
                  if (!e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                disabled={Boolean(pending)}
              />
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={send}
                disabled={!prompt.trim() || Boolean(pending)}
              >
                Send
              </Button>
            </div>
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
