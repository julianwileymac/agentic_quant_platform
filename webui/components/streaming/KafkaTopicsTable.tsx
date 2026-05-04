"use client";

import {
  App,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";
import {
  kafkaApi,
  type ConsumerGroup,
  type KafkaTopic,
} from "@/lib/api/streaming";

const { Text, Paragraph } = Typography;

export function KafkaTopicsTable() {
  const { message } = App.useApp();
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm();
  const [tab, setTab] = useState<string>("topics");

  const topics = useApiQuery<KafkaTopic[]>({
    queryKey: ["kafka", "topics"],
    path: "/streaming/kafka/topics",
  });
  const groups = useApiQuery<ConsumerGroup[]>({
    queryKey: ["kafka", "consumer-groups"],
    path: "/streaming/kafka/consumer-groups",
    enabled: tab === "groups",
  });
  const subjects = useApiQuery<Array<{ subject: string }>>({
    queryKey: ["kafka", "schema-subjects"],
    path: "/streaming/kafka/schema-registry/subjects",
    enabled: tab === "schemas",
  });

  useEffect(() => {
    if (!creating) form.resetFields();
  }, [creating, form]);

  async function createTopic() {
    try {
      const v = await form.validateFields();
      await kafkaApi.createTopic({
        name: v.name,
        partitions: v.partitions ?? 1,
        replication_factor: v.replication_factor ?? 1,
        config: {},
      });
      message.success(`Topic ${v.name} created`);
      setCreating(false);
      topics.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function deleteTopic(name: string) {
    try {
      await kafkaApi.deleteTopic(name);
      message.success(`Topic ${name} deleted`);
      topics.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title="Kafka"
      subtitle="Native Strimzi admin (with cluster-mgmt fallback)."
      extra={
        <Button type="primary" onClick={() => setCreating(true)}>
          New topic
        </Button>
      }
    >
      <Tabs
        activeKey={tab}
        onChange={setTab}
        items={[
          {
            key: "topics",
            label: "Topics",
            children: (
              <Card>
                <Table
                  rowKey="name"
                  loading={topics.isLoading}
                  dataSource={topics.data ?? []}
                  pagination={{ pageSize: 25 }}
                  columns={[
                    {
                      title: "Name",
                      dataIndex: "name",
                      render: (name: string) => (
                        <Link href={`/streaming/kafka/topics/${encodeURIComponent(name)}`}>
                          {name}
                        </Link>
                      ),
                    },
                    { title: "Partitions", dataIndex: "partitions" },
                    { title: "Replication", dataIndex: "replication_factor" },
                    {
                      title: "Internal",
                      dataIndex: "is_internal",
                      render: (i: boolean) =>
                        i ? <Tag>internal</Tag> : <Tag color="blue">user</Tag>,
                    },
                    {
                      title: "Actions",
                      render: (_: unknown, row: KafkaTopic) => (
                        <Space>
                          <Link
                            href={`/streaming/kafka/topics/${encodeURIComponent(row.name)}`}
                          >
                            <Button size="small">Details</Button>
                          </Link>
                          {!row.is_internal && (
                            <Button
                              size="small"
                              danger
                              onClick={() => deleteTopic(row.name)}
                            >
                              Delete
                            </Button>
                          )}
                        </Space>
                      ),
                    },
                  ]}
                />
              </Card>
            ),
          },
          {
            key: "groups",
            label: "Consumer groups",
            children: (
              <Card>
                <Table
                  rowKey="group_id"
                  loading={groups.isLoading}
                  dataSource={groups.data ?? []}
                  pagination={{ pageSize: 25 }}
                  columns={[
                    { title: "Group", dataIndex: "group_id" },
                    {
                      title: "State",
                      dataIndex: "state",
                      render: (s: string) => <Tag>{s}</Tag>,
                    },
                    { title: "Members", dataIndex: "members" },
                  ]}
                />
              </Card>
            ),
          },
          {
            key: "schemas",
            label: "Schema subjects",
            children: (
              <Card>
                <Table
                  rowKey="subject"
                  loading={subjects.isLoading}
                  dataSource={subjects.data ?? []}
                  pagination={{ pageSize: 25 }}
                  columns={[
                    { title: "Subject", dataIndex: "subject" },
                  ]}
                />
                <Paragraph type="secondary" style={{ marginTop: 8 }}>
                  Apicurio schema registry subjects (Confluent ccompat). Use the
                  schema-registry endpoints under <Text code>/streaming/kafka/schema-registry</Text> to
                  inspect or register versions.
                </Paragraph>
              </Card>
            ),
          },
        ]}
      />

      <Modal
        open={creating}
        title="Create topic"
        onCancel={() => setCreating(false)}
        onOk={createTopic}
        okText="Create"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="Topic name"
            rules={[{ required: true, message: "Topic name is required" }]}
          >
            <Input placeholder="market.bar.v1" />
          </Form.Item>
          <Form.Item name="partitions" label="Partitions" initialValue={1}>
            <InputNumber min={1} max={10000} />
          </Form.Item>
          <Form.Item
            name="replication_factor"
            label="Replication factor"
            initialValue={1}
          >
            <InputNumber min={1} max={10} />
          </Form.Item>
        </Form>
      </Modal>
    </PageContainer>
  );
}
