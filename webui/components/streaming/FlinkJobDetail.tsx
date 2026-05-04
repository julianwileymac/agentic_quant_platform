"use client";

import {
  App,
  Button,
  Card,
  Descriptions,
  Space,
  Tag,
  Typography,
} from "antd";
import { useEffect, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import {
  flinkApi,
  type FlinkSessionJob,
} from "@/lib/api/streaming";

const { Text } = Typography;

interface FlinkJobDetailProps {
  name: string;
}

export function FlinkJobDetail({ name }: FlinkJobDetailProps) {
  const { message } = App.useApp();
  const [job, setJob] = useState<FlinkSessionJob | null>(null);
  const [restJob, setRestJob] = useState<Record<string, unknown> | null>(null);
  const [exceptions, setExceptions] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);

  function refresh() {
    setLoading(true);
    flinkApi
      .sessionJob(name)
      .then(async (sj) => {
        setJob(sj);
        if (sj.job_id) {
          try {
            setRestJob(await flinkApi.job(sj.job_id));
            setExceptions(await flinkApi.jobExceptions(sj.job_id));
          } catch {
            // ignore - REST API may not be reachable
          }
        }
      })
      .catch((err) => message.error((err as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [name]);

  return (
    <PageContainer
      title={`Flink session job — ${name}`}
      subtitle="Operator-managed CRD + REST job snapshot."
      extra={
        <Space>
          <Button onClick={refresh} loading={loading}>
            Refresh
          </Button>
          <Button onClick={() => flinkApi.activateSessionJob(name).then(refresh)}>Activate</Button>
          <Button onClick={() => flinkApi.suspendSessionJob(name).then(refresh)}>Suspend</Button>
        </Space>
      }
    >
      <Card title="Session job spec" loading={loading}>
        {job && (
          <Descriptions bordered column={2} size="small">
            <Descriptions.Item label="Name">{job.name}</Descriptions.Item>
            <Descriptions.Item label="Namespace">{job.namespace}</Descriptions.Item>
            <Descriptions.Item label="State">
              <Tag color={job.state === "running" ? "green" : "default"}>{job.state ?? "?"}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Parallelism">{job.parallelism ?? "—"}</Descriptions.Item>
            <Descriptions.Item label="Jar URI" span={2}>
              <Text code>{job.jar_uri ?? "—"}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Entry class" span={2}>
              <Text code>{job.entry_class ?? "—"}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Args" span={2}>
              <pre style={{ margin: 0, fontSize: 12 }}>
                {JSON.stringify(job.args ?? [], null, 2)}
              </pre>
            </Descriptions.Item>
            <Descriptions.Item label="Job ID">{job.job_id ?? "—"}</Descriptions.Item>
          </Descriptions>
        )}
      </Card>
      {restJob && (
        <Card title="Flink REST job snapshot" style={{ marginTop: 16 }}>
          <pre style={{ margin: 0, fontSize: 12 }}>
            {JSON.stringify(restJob, null, 2)}
          </pre>
        </Card>
      )}
      {exceptions && (
        <Card title="Exceptions" style={{ marginTop: 16 }}>
          <pre style={{ margin: 0, fontSize: 12 }}>
            {JSON.stringify(exceptions, null, 2)}
          </pre>
        </Card>
      )}
    </PageContainer>
  );
}
