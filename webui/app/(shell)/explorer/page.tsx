"use client";

import {
  AppstoreOutlined,
  BulbOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  LineChartOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import {
  Card,
  Col,
  Divider,
  Empty,
  Row,
  Segmented,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import { useMemo, useState } from "react";
import useSWR from "swr";

import {
  listLabCorpora,
  listLabMemory,
  listProjectAgentRuns,
  listProjectAgents,
  listProjectBacktests,
  listProjectStrategies,
} from "@/lib/api/tenancy";
import { useWorkspace } from "@/lib/tenancy/use-workspace";

const { Title, Text } = Typography;

type ResourceFilter = "strategies" | "backtests" | "agents" | "agent-runs" | "corpora" | "memory";

const FILTERS: { value: ResourceFilter; label: string; icon: React.ReactNode; needsLab?: boolean }[] = [
  { value: "strategies", label: "Strategies", icon: <AppstoreOutlined /> },
  { value: "backtests", label: "Backtests", icon: <LineChartOutlined /> },
  { value: "agents", label: "Agents", icon: <RobotOutlined /> },
  { value: "agent-runs", label: "Agent Runs", icon: <RobotOutlined /> },
  { value: "corpora", label: "RAG Corpora", icon: <DatabaseOutlined />, needsLab: true },
  { value: "memory", label: "Memory", icon: <BulbOutlined />, needsLab: true },
];

export default function ExplorerPage() {
  const { org, workspace, project, lab, projects, labs, isLoading } = useWorkspace();
  const [filter, setFilter] = useState<ResourceFilter>("strategies");

  const projectId = project?.id ?? null;
  const labId = lab?.id ?? null;

  const { data: strategies = [] } = useSWR(
    filter === "strategies" && projectId ? ["strategies", projectId] : null,
    () => listProjectStrategies(projectId!),
  );
  const { data: backtests = [] } = useSWR(
    filter === "backtests" && projectId ? ["backtests", projectId] : null,
    () => listProjectBacktests(projectId!),
  );
  const { data: agents = [] } = useSWR(
    filter === "agents" && projectId ? ["agents", projectId] : null,
    () => listProjectAgents(projectId!),
  );
  const { data: runs = [] } = useSWR(
    filter === "agent-runs" && projectId ? ["agent-runs", projectId] : null,
    () => listProjectAgentRuns(projectId!),
  );
  const { data: corpora = [] } = useSWR(
    filter === "corpora" && labId ? ["corpora", labId] : null,
    () => listLabCorpora(labId!),
  );
  const { data: memory = [] } = useSWR(
    filter === "memory" && labId ? ["memory", labId] : null,
    () => listLabMemory(labId!),
  );

  const table = useMemo(() => {
    switch (filter) {
      case "strategies":
        return { rows: strategies, columns: [
          { title: "Name", dataIndex: "name" },
          { title: "Version", dataIndex: "version" },
          { title: "Status", dataIndex: "status", render: (s: string) => <Tag>{s}</Tag> },
        ]};
      case "backtests":
        return { rows: backtests, columns: [
          { title: "ID", dataIndex: "id", render: (v: string) => <Text code>{v.slice(0, 8)}</Text> },
          { title: "Status", dataIndex: "status", render: (s: string) => <Tag>{s}</Tag> },
          { title: "Sharpe", dataIndex: "sharpe", render: (v: number | null) => v?.toFixed(3) ?? "—" },
          { title: "Return", dataIndex: "total_return", render: (v: number | null) => v != null ? `${(v * 100).toFixed(2)}%` : "—" },
          { title: "Created", dataIndex: "created_at", render: (s: string) => new Date(s).toLocaleString() },
        ]};
      case "agents":
        return { rows: agents, columns: [
          { title: "Name", dataIndex: "name" },
          { title: "Role", dataIndex: "role" },
          { title: "Version", dataIndex: "current_version" },
        ]};
      case "agent-runs":
        return { rows: runs, columns: [
          { title: "Spec", dataIndex: "spec_name" },
          { title: "Status", dataIndex: "status", render: (s: string) => <Tag>{s}</Tag> },
          { title: "Cost (USD)", dataIndex: "cost_usd", render: (v: number) => `$${v.toFixed(4)}` },
          { title: "Started", dataIndex: "started_at", render: (s: string) => new Date(s).toLocaleString() },
        ]};
      case "corpora":
        return { rows: corpora, columns: [
          { title: "Name", dataIndex: "name" },
          { title: "Order", dataIndex: "order", render: (s: string) => <Tag>{s}</Tag> },
          { title: "L1", dataIndex: "l1" },
          { title: "L2", dataIndex: "l2" },
          { title: "Chunks", dataIndex: "chunks_count" },
        ]};
      case "memory":
        return { rows: memory, columns: [
          { title: "Role", dataIndex: "role" },
          { title: "Symbol", dataIndex: "vt_symbol" },
          { title: "Lesson", dataIndex: "lesson", render: (v: string) => <Text>{v}</Text> },
          { title: "Created", dataIndex: "created_at", render: (s: string) => new Date(s).toLocaleString() },
        ]};
    }
  }, [filter, strategies, backtests, agents, runs, corpora, memory]);

  const filterNeedsLab = FILTERS.find((f) => f.value === filter)?.needsLab;
  const noScopeForFilter = filterNeedsLab ? !labId : !projectId;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <div>
        <Title level={3} style={{ margin: 0 }}>Resource Explorer</Title>
        <Text type="secondary">
          Browse the resources visible under your active org / workspace / project / lab.
        </Text>
      </div>

      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic title="Organization" value={org?.name ?? "—"} prefix={<DatabaseOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="Workspace" value={workspace?.name ?? "—"} prefix={<AppstoreOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="Projects" value={projects.length} prefix={<AppstoreOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="Labs" value={labs.length} prefix={<ExperimentOutlined />} />
          </Card>
        </Col>
      </Row>

      <Divider style={{ margin: "8px 0" }} />

      <Segmented
        options={FILTERS.map((f) => ({ value: f.value, label: <Space>{f.icon}{f.label}</Space> }))}
        value={filter}
        onChange={(v) => setFilter(v as ResourceFilter)}
      />

      {isLoading ? (
        <Spin />
      ) : noScopeForFilter ? (
        <Empty
          description={`Pick an active ${filterNeedsLab ? "lab" : "project"} from the header switcher to see ${filter}.`}
        />
      ) : (
        <Table
          rowKey={(r: { id?: string; name?: string }) => r.id ?? r.name ?? Math.random().toString()}
          dataSource={table.rows as never[]}
          columns={table.columns as never}
          pagination={{ pageSize: 25 }}
          size="middle"
        />
      )}
    </Space>
  );
}
