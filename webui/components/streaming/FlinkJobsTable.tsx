"use client";

import {
  App,
  Button,
  Card,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import Link from "next/link";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";
import {
  flinkApi,
  type FlinkJobOverview,
  type FlinkSessionJob,
} from "@/lib/api/streaming";

const { Text, Paragraph } = Typography;

export function FlinkJobsTable() {
  const { message } = App.useApp();
  const [tab, setTab] = useState<string>("sessions");

  const sessions = useApiQuery<FlinkSessionJob[]>({
    queryKey: ["flink", "session-jobs"],
    path: "/streaming/flink/sessionjobs",
  });
  const jobs = useApiQuery<FlinkJobOverview[]>({
    queryKey: ["flink", "jobs"],
    path: "/streaming/flink/jobs",
    enabled: tab === "rest",
  });

  async function activate(name: string) {
    try {
      await flinkApi.activateSessionJob(name);
      message.success(`Activated ${name}`);
      sessions.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function suspend(name: string) {
    try {
      await flinkApi.suspendSessionJob(name);
      message.success(`Suspended ${name}`);
      sessions.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function savepoint(name: string) {
    try {
      const res = await flinkApi.triggerSavepoint(name);
      message.success(`Savepoint trigger ${res.trigger_id ?? "queued"}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title="Flink"
      subtitle="Native session-job CRUD via the Flink Operator (with cluster-mgmt fallback)."
    >
      <Tabs
        activeKey={tab}
        onChange={setTab}
        items={[
          {
            key: "sessions",
            label: "Session jobs",
            children: (
              <Card loading={sessions.isLoading}>
                <Table
                  rowKey="name"
                  dataSource={sessions.data ?? []}
                  pagination={{ pageSize: 25 }}
                  columns={[
                    {
                      title: "Name",
                      dataIndex: "name",
                      render: (name: string) => (
                        <Link href={`/streaming/flink/jobs/${encodeURIComponent(name)}`}>
                          {name}
                        </Link>
                      ),
                    },
                    {
                      title: "State",
                      dataIndex: "state",
                      render: (s: string | null) =>
                        s ? (
                          <Tag color={s === "running" ? "green" : "default"}>{s}</Tag>
                        ) : (
                          <Tag>unknown</Tag>
                        ),
                    },
                    { title: "Parallelism", dataIndex: "parallelism" },
                    { title: "Job ID", dataIndex: "job_id" },
                    { title: "Jar URI", dataIndex: "jar_uri" },
                    {
                      title: "Actions",
                      render: (_: unknown, row: FlinkSessionJob) => (
                        <Space>
                          <Button size="small" onClick={() => activate(row.name)}>
                            Activate
                          </Button>
                          <Button size="small" onClick={() => suspend(row.name)}>
                            Suspend
                          </Button>
                          <Button size="small" onClick={() => savepoint(row.name)}>
                            Savepoint
                          </Button>
                          <Link href={`/streaming/flink/jobs/${encodeURIComponent(row.name)}`}>
                            <Button size="small" type="primary">
                              Details
                            </Button>
                          </Link>
                        </Space>
                      ),
                    },
                  ]}
                />
              </Card>
            ),
          },
          {
            key: "rest",
            label: "REST jobs overview",
            children: (
              <Card loading={jobs.isLoading}>
                <Paragraph type="secondary">
                  Live snapshot from the Flink REST API.
                </Paragraph>
                <Table
                  rowKey="jid"
                  dataSource={jobs.data ?? []}
                  pagination={{ pageSize: 25 }}
                  columns={[
                    { title: "Job ID", dataIndex: "jid" },
                    { title: "Name", dataIndex: "name" },
                    {
                      title: "State",
                      dataIndex: "state",
                      render: (s: string) => <Tag>{s}</Tag>,
                    },
                    {
                      title: "Started",
                      dataIndex: "start_time",
                      render: (ts: number | undefined) =>
                        ts ? new Date(ts).toISOString() : "—",
                    },
                    {
                      title: "Tasks",
                      dataIndex: "tasks",
                      render: (t: Record<string, number> | undefined) =>
                        t ? <Text code>{JSON.stringify(t)}</Text> : "—",
                    },
                  ]}
                />
              </Card>
            ),
          },
        ]}
      />
    </PageContainer>
  );
}
