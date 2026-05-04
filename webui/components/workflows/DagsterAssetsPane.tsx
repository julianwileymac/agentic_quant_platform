"use client";

import { App, Alert, Button, Card, Descriptions, List, Space, Tag } from "antd";
import { useEffect, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import {
  dagsterApi,
  type DagsterAssetNode,
  type DagsterRunSummary,
  type DagsterScheduleSummary,
  type DagsterSensorSummary,
  type DagsterStatus,
} from "@/lib/api/dagster";

function assetKey(node: DagsterAssetNode): string[] {
  return node.assetKey?.path ?? node.key ?? [];
}

export function DagsterAssetsPane() {
  const { message } = App.useApp();
  const [status, setStatus] = useState<DagsterStatus | null>(null);
  const [assets, setAssets] = useState<DagsterAssetNode[]>([]);
  const [runs, setRuns] = useState<DagsterRunSummary[]>([]);
  const [schedules, setSchedules] = useState<DagsterScheduleSummary[]>([]);
  const [sensors, setSensors] = useState<DagsterSensorSummary[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const [s, a, r, sched, sens] = await Promise.all([
        dagsterApi.status(),
        dagsterApi.listAssets(),
        dagsterApi.listRuns(25),
        dagsterApi.listSchedules().catch(() => ({ schedules: [] })),
        dagsterApi.listSensors().catch(() => ({ sensors: [] })),
      ]);
      setStatus(s);
      setAssets(a.asset_nodes ?? []);
      setRuns(r.runs ?? []);
      setSchedules(sched.schedules ?? []);
      setSensors(sens.sensors ?? []);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function toggleSchedule(name: string, shouldStart: boolean) {
    setBusy(`schedule:${name}`);
    try {
      await (shouldStart ? dagsterApi.startSchedule(name) : dagsterApi.stopSchedule(name));
      message.success(`${shouldStart ? "started" : "stopped"} schedule ${name}`);
      await refresh();
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function toggleSensor(name: string, shouldStart: boolean) {
    setBusy(`sensor:${name}`);
    try {
      await (shouldStart ? dagsterApi.startSensor(name) : dagsterApi.stopSensor(name));
      message.success(`${shouldStart ? "started" : "stopped"} sensor ${name}`);
      await refresh();
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function trigger(node: DagsterAssetNode) {
    const key = assetKey(node);
    if (key.length === 0) {
      message.warning("asset key unknown");
      return;
    }
    setBusy(key.join("/"));
    try {
      await dagsterApi.trigger([key]);
      message.success(`triggered ${key.join("/")}`);
      await refresh();
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <PageContainer
      title="Dagster assets"
      subtitle="AQP code-location assets, jobs, schedules, and recent runs."
    >
      {error && <Alert type="warning" showIcon message={error} />}
      {status && (
        <Card size="small" style={{ marginBottom: 12 }}>
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="GraphQL">
              {status.graphql_url ?? "(local fallback)"}
            </Descriptions.Item>
            <Descriptions.Item label="Code location">
              <Tag color="blue">{status.code_location}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Module path" span={2}>
              <code>{status.module_path}</code>
            </Descriptions.Item>
            <Descriptions.Item label="gRPC" span={2}>
              {status.grpc_host}:{status.grpc_port}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      <Card size="small" title={`Assets (${assets.length})`} style={{ marginBottom: 12 }}>
        <List
          size="small"
          dataSource={assets}
          renderItem={(node) => {
            const key = assetKey(node).join("/");
            return (
              <List.Item
                actions={[
                  <Button
                    size="small"
                    key="trigger"
                    loading={busy === key}
                    onClick={() => trigger(node)}
                  >
                    Materialize
                  </Button>,
                ]}
              >
                <Space direction="vertical" size={0}>
                  <Space>
                    <code>{key}</code>
                    {node.groupName && <Tag>{node.groupName}</Tag>}
                  </Space>
                  {node.description && (
                    <span style={{ color: "var(--muted-foreground)" }}>
                      {node.description}
                    </span>
                  )}
                </Space>
              </List.Item>
            );
          }}
        />
      </Card>

      <Card size="small" title={`Recent runs (${runs.length})`}>
        <List
          size="small"
          dataSource={runs}
          renderItem={(run) => (
            <List.Item>
              <Space direction="vertical" size={0}>
                <Space>
                  <code>{run.runId}</code>
                  <Tag>{run.status}</Tag>
                  <span>{run.pipelineName}</span>
                </Space>
                <span style={{ fontSize: 12, color: "var(--muted-foreground)" }}>
                  {run.startTime ? new Date(run.startTime * 1000).toISOString() : "-"}
                </span>
              </Space>
            </List.Item>
          )}
        />
      </Card>

      <Card size="small" title={`Schedules (${schedules.length})`} style={{ marginTop: 12 }}>
        <List
          size="small"
          dataSource={schedules}
          renderItem={(schedule) => {
            const statusText = schedule.scheduleState?.status ?? "UNKNOWN";
            const started = statusText.toUpperCase().includes("RUNNING");
            return (
              <List.Item
                actions={[
                  <Button
                    size="small"
                    key="start-stop"
                    loading={busy === `schedule:${schedule.name}`}
                    onClick={() => toggleSchedule(schedule.name, !started)}
                  >
                    {started ? "Stop" : "Start"}
                  </Button>,
                ]}
              >
                <Space direction="vertical" size={0}>
                  <Space>
                    <code>{schedule.name}</code>
                    <Tag>{statusText}</Tag>
                    {schedule.cronSchedule ? <span>{schedule.cronSchedule}</span> : null}
                  </Space>
                  <span style={{ fontSize: 12, color: "var(--muted-foreground)" }}>
                    {schedule.executionTimezone ?? "timezone inherited"}
                  </span>
                </Space>
              </List.Item>
            );
          }}
        />
      </Card>

      <Card size="small" title={`Sensors (${sensors.length})`} style={{ marginTop: 12 }}>
        <List
          size="small"
          dataSource={sensors}
          renderItem={(sensor) => {
            const statusText = sensor.sensorState?.status ?? "UNKNOWN";
            const started = statusText.toUpperCase().includes("RUNNING");
            return (
              <List.Item
                actions={[
                  <Button
                    size="small"
                    key="start-stop"
                    loading={busy === `sensor:${sensor.name}`}
                    onClick={() => toggleSensor(sensor.name, !started)}
                  >
                    {started ? "Stop" : "Start"}
                  </Button>,
                ]}
              >
                <Space>
                  <code>{sensor.name}</code>
                  <Tag>{statusText}</Tag>
                </Space>
              </List.Item>
            );
          }}
        />
      </Card>
    </PageContainer>
  );
}
