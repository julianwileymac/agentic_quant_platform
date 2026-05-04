"use client";

import {
  App,
  Button,
  Card,
  Descriptions,
  Space,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { useEffect, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import {
  producersApi,
  type ProducerLogs,
  type ProducerStatus,
  type ProducerSummary,
} from "@/lib/api/streaming";

const { Text } = Typography;

interface ProducerDetailProps {
  name: string;
}

export function ProducerDetail({ name }: ProducerDetailProps) {
  const { message } = App.useApp();
  const [row, setRow] = useState<ProducerSummary | null>(null);
  const [status, setStatus] = useState<ProducerStatus | null>(null);
  const [logs, setLogs] = useState<ProducerLogs | null>(null);
  const [topics, setTopics] = useState<{
    producer: string;
    topics: string[];
    links: unknown[];
  } | null>(null);

  function refresh() {
    producersApi.get(name).then(setRow).catch((e) => message.error((e as Error).message));
    producersApi.status(name).then(setStatus).catch(() => undefined);
    producersApi.topics(name).then(setTopics).catch(() => undefined);
    producersApi.logs(name, 200).then(setLogs).catch(() => undefined);
  }

  useEffect(refresh, [name]);

  if (!row) {
    return (
      <PageContainer title={`Producer — ${name}`}>
        <Card>Loading…</Card>
      </PageContainer>
    );
  }

  return (
    <PageContainer
      title={`Producer — ${row.display_name}`}
      subtitle={row.description ?? "Lightweight market-data producer."}
      extra={
        <Space>
          <Button onClick={refresh}>Refresh</Button>
          <Button type="primary" onClick={() => producersApi.start(name).then(refresh)}>
            Start
          </Button>
          <Button onClick={() => producersApi.stop(name).then(refresh)}>Stop</Button>
          <Button onClick={() => producersApi.restart(name).then(refresh)}>Restart</Button>
        </Space>
      }
    >
      <Tabs
        items={[
          {
            key: "overview",
            label: "Overview",
            children: (
              <Card>
                <Descriptions bordered column={2} size="small">
                  <Descriptions.Item label="Name">{row.name}</Descriptions.Item>
                  <Descriptions.Item label="Kind">
                    <Tag color="blue">{row.kind}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="Runtime">{row.runtime}</Descriptions.Item>
                  <Descriptions.Item label="Image">{row.image ?? "—"}</Descriptions.Item>
                  <Descriptions.Item label="Deployment">
                    {row.deployment_namespace}/{row.deployment_name}
                  </Descriptions.Item>
                  <Descriptions.Item label="Replicas">
                    {row.current_replicas} / {row.desired_replicas}
                  </Descriptions.Item>
                  <Descriptions.Item label="Status">
                    <Tag>{row.last_status}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="Last error">{row.last_error ?? "—"}</Descriptions.Item>
                  <Descriptions.Item label="Topics" span={2}>
                    {(row.topics ?? []).map((t) => (
                      <Tag key={t}>{t}</Tag>
                    ))}
                  </Descriptions.Item>
                  <Descriptions.Item label="Tags" span={2}>
                    {(row.tags ?? []).map((t) => (
                      <Tag key={t}>{t}</Tag>
                    ))}
                  </Descriptions.Item>
                  <Descriptions.Item label="Config" span={2}>
                    <pre style={{ margin: 0, fontSize: 12 }}>
                      {JSON.stringify(row.config ?? {}, null, 2)}
                    </pre>
                  </Descriptions.Item>
                </Descriptions>
              </Card>
            ),
          },
          {
            key: "status",
            label: "Status",
            children: (
              <Card>
                <pre style={{ margin: 0, fontSize: 12 }}>
                  {JSON.stringify(status, null, 2)}
                </pre>
              </Card>
            ),
          },
          {
            key: "topics",
            label: "Topics & links",
            children: (
              <Card>
                <Text strong>Topics</Text>
                <ul>
                  {(topics?.topics ?? []).map((t) => (
                    <li key={t}>
                      <Text code>{t}</Text>
                    </li>
                  ))}
                </ul>
                <Text strong>Streaming dataset links</Text>
                <pre style={{ margin: 0, fontSize: 12 }}>
                  {JSON.stringify(topics?.links ?? [], null, 2)}
                </pre>
              </Card>
            ),
          },
          {
            key: "logs",
            label: "Logs",
            children: (
              <Card>
                <pre style={{ margin: 0, fontSize: 12, whiteSpace: "pre-wrap" }}>
                  {(logs?.lines ?? []).join("\n") || "(no log lines)"}
                </pre>
              </Card>
            ),
          },
        ]}
      />
    </PageContainer>
  );
}
