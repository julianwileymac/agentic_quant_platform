"use client";

import {
  App,
  Button,
  Card,
  Descriptions,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { useEffect, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import {
  kafkaApi,
  type KafkaTopic,
  type TopicSampleMessage,
} from "@/lib/api/streaming";

const { Text } = Typography;

interface KafkaTopicDetailProps {
  topic: string;
}

export function KafkaTopicDetail({ topic }: KafkaTopicDetailProps) {
  const { message } = App.useApp();
  const [meta, setMeta] = useState<KafkaTopic | null>(null);
  const [samples, setSamples] = useState<TopicSampleMessage[]>([]);
  const [loadingMeta, setLoadingMeta] = useState(false);
  const [sampling, setSampling] = useState(false);

  useEffect(() => {
    setLoadingMeta(true);
    kafkaApi
      .topic(topic)
      .then(setMeta)
      .catch((err) => message.error((err as Error).message))
      .finally(() => setLoadingMeta(false));
  }, [topic, message]);

  async function sample() {
    setSampling(true);
    try {
      const rows = await kafkaApi.sample(topic, 50);
      setSamples(rows);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setSampling(false);
    }
  }

  return (
    <PageContainer
      title={`Kafka topic — ${topic}`}
      subtitle="Native admin metadata + tail sampling."
      extra={
        <Space>
          <Button onClick={sample} loading={sampling}>
            Sample latest 50
          </Button>
        </Space>
      }
    >
      <Card title="Metadata" loading={loadingMeta}>
        {meta && (
          <Descriptions bordered column={2} size="small">
            <Descriptions.Item label="Name">{meta.name}</Descriptions.Item>
            <Descriptions.Item label="Partitions">{meta.partitions}</Descriptions.Item>
            <Descriptions.Item label="Replication">{meta.replication_factor}</Descriptions.Item>
            <Descriptions.Item label="Internal">
              {meta.is_internal ? <Tag>internal</Tag> : <Tag color="blue">user</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="Config" span={2}>
              <pre style={{ margin: 0, fontSize: 12 }}>
                {JSON.stringify(meta.config ?? {}, null, 2)}
              </pre>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Card>
      <Card title="Recent messages" style={{ marginTop: 16 }}>
        <Table
          rowKey={(row) => `${row.partition}-${row.offset}`}
          dataSource={samples}
          loading={sampling}
          pagination={false}
          size="small"
          columns={[
            { title: "Partition", dataIndex: "partition" },
            { title: "Offset", dataIndex: "offset" },
            {
              title: "Timestamp",
              dataIndex: "timestamp",
              render: (ts: number | null) =>
                ts ? new Date(Number(ts)).toISOString() : "—",
            },
            { title: "Key", dataIndex: "key" },
            {
              title: "Value preview",
              dataIndex: "value_preview",
              render: (value: string | null) => (value ? <Text code>{value.slice(0, 200)}</Text> : "—"),
            },
          ]}
        />
      </Card>
    </PageContainer>
  );
}
