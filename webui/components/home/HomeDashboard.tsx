"use client";

import {
  ArrowUpOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  ExclamationCircleOutlined,
} from "@ant-design/icons";
import { Card, Col, Empty, Row, Space, Statistic, Tag, Typography } from "antd";
import Link from "next/link";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";

const { Title, Text } = Typography;

export function HomeDashboard() {
  const health = useApiQuery<{ status: string; version?: string }>({
    queryKey: ["health"],
    path: "/health",
  });
  const root = useApiQuery<{ app: string; version: string; routes: string[] }>({
    queryKey: ["root"],
    path: "/",
  });
  const recentBacktests = useApiQuery<{ items?: unknown[] }>({
    queryKey: ["backtest", "runs", "recent"],
    path: "/backtest/runs?limit=10",
    enabled: true,
  });

  const status = health.data?.status;
  // Reachability: successful JSON from /health. ``degraded`` still means the gateway answered.
  const apiReachable = health.isSuccess;
  const apiDegraded = status === "degraded";

  return (
    <PageContainer
      title="Dashboard"
      subtitle="Overview of the agentic quant platform"
    >
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="API"
              value={
                !apiReachable
                  ? health.isPending
                    ? "Checking…"
                    : "Offline"
                  : apiDegraded
                    ? "Degraded"
                    : "Online"
              }
              prefix={
                apiReachable ? (
                  apiDegraded ? (
                    <ExclamationCircleOutlined style={{ color: "#f59e0b" }} />
                  ) : (
                    <CheckCircleOutlined style={{ color: "#10b981" }} />
                  )
                ) : (
                  <ExclamationCircleOutlined style={{ color: "#ef4444" }} />
                )
              }
              valueStyle={{
                color: apiReachable ? (apiDegraded ? "#f59e0b" : "#10b981") : "#ef4444",
                fontSize: 22,
              }}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {root.data?.version ? `v${root.data.version}` : "—"}
            </Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="Routes registered"
              value={root.data?.routes?.length ?? 0}
              prefix={<CloudServerOutlined />}
              valueStyle={{ fontSize: 22 }}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              FastAPI surface
            </Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="Recent backtests"
              value={Array.isArray(recentBacktests.data?.items) ? recentBacktests.data!.items!.length : 0}
              prefix={<ArrowUpOutlined />}
              valueStyle={{ fontSize: 22 }}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              Last 10 runs
            </Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Space direction="vertical" size={4} style={{ width: "100%" }}>
              <Text type="secondary">Environment</Text>
              <Title level={4} style={{ margin: 0 }}>
                {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}
              </Title>
              <Tag color="blue">Local first</Tag>
            </Space>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={16}>
          <Card title="Recent activity" bordered>
            <Empty description="Connect a backtest run or paper session to populate this feed" />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="Quick links" bordered>
            <Space direction="vertical" size={6} style={{ width: "100%" }}>
              <Link href="/strategies">Strategies browser →</Link>
              <Link href="/backtest/new">Run a backtest →</Link>
              <Link href="/data/explorer">Open data explorer →</Link>
              <Link href="/workflows/agent">Build an agent crew →</Link>
              <Link href="/chat">Chat with the assistant →</Link>
            </Space>
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
