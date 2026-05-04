"use client";

import {
  App,
  Badge,
  Button,
  Card,
  InputNumber,
  Space,
  Tag,
  Typography,
} from "antd";
import Link from "next/link";
import { useState } from "react";

import { producersApi, type ProducerSummary } from "@/lib/api/streaming";

const { Paragraph, Text } = Typography;

interface ProducerCardProps {
  row: ProducerSummary;
  onChange?: () => void;
}

export function ProducerCard({ row, onChange }: ProducerCardProps) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState<string | null>(null);
  const [scaleTo, setScaleTo] = useState<number>(row.desired_replicas || 1);

  async function call(action: string, fn: () => Promise<unknown>) {
    setBusy(action);
    try {
      await fn();
      message.success(`${row.name}: ${action} ok`);
      onChange?.();
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const ready = row.current_replicas === row.desired_replicas;
  const statusColor =
    row.last_status === "running"
      ? "green"
      : row.last_status === "stopped"
      ? "default"
      : row.last_status === "error"
      ? "red"
      : "orange";

  return (
    <Card
      title={
        <Space>
          <Text strong>{row.display_name}</Text>
          <Tag color="blue">{row.kind}</Tag>
          <Tag>{row.runtime}</Tag>
        </Space>
      }
      extra={
        <Link href={`/streaming/producers/${encodeURIComponent(row.name)}`}>
          Details
        </Link>
      }
    >
      {row.description && <Paragraph type="secondary">{row.description}</Paragraph>}
      <Space size="small" wrap>
        <Badge
          status={ready ? "success" : "processing"}
          text={`${row.current_replicas}/${row.desired_replicas} replicas`}
        />
        <Tag color={statusColor}>{row.last_status}</Tag>
        {(row.tags ?? []).map((t) => (
          <Tag key={t}>{t}</Tag>
        ))}
      </Space>
      <Paragraph style={{ marginTop: 8 }} type="secondary" ellipsis={{ tooltip: true }}>
        Topics: {(row.topics ?? []).join(", ") || "—"}
      </Paragraph>
      <Space size="small" wrap>
        <Button
          size="small"
          type="primary"
          loading={busy === "start"}
          onClick={() => call("start", () => producersApi.start(row.name))}
        >
          Start
        </Button>
        <Button
          size="small"
          loading={busy === "stop"}
          onClick={() => call("stop", () => producersApi.stop(row.name))}
        >
          Stop
        </Button>
        <Button
          size="small"
          loading={busy === "restart"}
          onClick={() => call("restart", () => producersApi.restart(row.name))}
        >
          Restart
        </Button>
        <InputNumber
          size="small"
          min={0}
          max={32}
          value={scaleTo}
          onChange={(v) => setScaleTo(Number(v ?? 0))}
          style={{ width: 80 }}
        />
        <Button
          size="small"
          loading={busy === "scale"}
          onClick={() => call("scale", () => producersApi.scale(row.name, scaleTo))}
        >
          Scale
        </Button>
      </Space>
    </Card>
  );
}
