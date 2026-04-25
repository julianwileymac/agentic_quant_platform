"use client";

import { PauseCircleOutlined, PlayCircleOutlined } from "@ant-design/icons";
import {
  App,
  Alert,
  Button,
  Card,
  Empty,
  List,
  Space,
  Tag,
  Typography,
} from "antd";
import { useState } from "react";

import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";

const { Text, Paragraph } = Typography;

interface InterruptSummary {
  id: string;
  backtest_id: string;
  task_id?: string | null;
  ts?: string | null;
  rule?: string | null;
  status: string;
  payload: {
    pending_orders?: Array<{
      vt_symbol?: string;
      side?: string;
      quantity?: number;
      price?: number;
    }>;
    bar_context?: Record<string, unknown>;
    rule?: string;
  };
  response: Record<string, unknown>;
  created_at: string;
  resolved_at?: string | null;
}

export function InterruptPanel({ backtestId }: { backtestId: string }) {
  const { message } = App.useApp();
  const [actingId, setActingId] = useState<string | null>(null);

  const interrupts = useApiQuery<InterruptSummary[]>({
    queryKey: ["backtest", "interrupts", backtestId],
    path: "/backtest/interrupts",
    query: { backtest_id: backtestId, status: "pending" },
    refetchInterval: 3000,
  });

  async function respond(
    interruptId: string,
    action: "continue" | "skip",
    note?: string,
  ) {
    setActingId(interruptId);
    try {
      await apiFetch(`/backtest/interrupts/${interruptId}/respond`, {
        method: "POST",
        body: JSON.stringify({ action, note }),
      });
      message.success(`Interrupt ${action}d`);
      void interrupts.refetch();
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setActingId(null);
    }
  }

  const rows = interrupts.data ?? [];

  return (
    <Card
      size="small"
      title={
        <Space>
          <PauseCircleOutlined />
          Pending interrupts
          {rows.length ? <Tag color="orange">{rows.length}</Tag> : null}
        </Space>
      }
    >
      {!rows.length ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No pending interrupts." />
      ) : (
        <>
          <Alert
            type="info"
            showIcon
            message="The backtest engine is blocked waiting on these interrupts. Respond to release it."
            style={{ marginBottom: 8 }}
          />
          <List
            size="small"
            dataSource={rows}
            renderItem={(row) => (
              <List.Item
                actions={[
                  <Button
                    key="cont"
                    size="small"
                    icon={<PlayCircleOutlined />}
                    type="primary"
                    loading={actingId === row.id}
                    onClick={() => respond(row.id, "continue")}
                  >
                    Continue
                  </Button>,
                  <Button
                    key="skip"
                    size="small"
                    danger
                    loading={actingId === row.id}
                    onClick={() => respond(row.id, "skip", "skipped from UI")}
                  >
                    Skip
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Tag color="orange">{row.rule ?? "rule"}</Tag>
                      <Text type="secondary">{row.ts ?? row.created_at}</Text>
                    </Space>
                  }
                  description={
                    <>
                      <Paragraph style={{ margin: 0 }}>
                        {(row.payload?.pending_orders ?? []).map((o, i) => (
                          <Tag key={i}>
                            {o.side} {o.quantity} {o.vt_symbol} @ {o.price ?? "mkt"}
                          </Tag>
                        ))}
                      </Paragraph>
                    </>
                  }
                />
              </List.Item>
            )}
          />
        </>
      )}
    </Card>
  );
}
