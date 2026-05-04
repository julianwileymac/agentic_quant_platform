"use client";

import {
  CloudUploadOutlined,
  EditOutlined,
  ExperimentOutlined,
  MessageOutlined,
  PlayCircleOutlined,
  RocketOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { App, Button, Card, Empty, Space, Table, Tabs, Tag, Typography } from "antd";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import {
  BotsApi,
  type BotDeploymentOut,
  type BotDetail,
  type BotVersionOut,
} from "@/lib/api/bots";

import { BotBuilder } from "./BotBuilder";
import { ResearchBotChat } from "./ResearchBotChat";

const { Text, Paragraph } = Typography;

interface BotDetailPageProps {
  botRef: string;
}

export function BotDetailPage({ botRef }: BotDetailPageProps) {
  const { message } = App.useApp();
  const { data: bot, isLoading, refetch } = useQuery<BotDetail>({
    queryKey: ["bots", "detail", botRef],
    queryFn: () => BotsApi.get(botRef),
  });
  const { data: versions } = useQuery<BotVersionOut[]>({
    queryKey: ["bots", "versions", botRef],
    queryFn: () => BotsApi.versions(botRef),
    enabled: Boolean(bot),
  });
  const { data: deployments, refetch: refetchDeployments } = useQuery<BotDeploymentOut[]>({
    queryKey: ["bots", "deployments", botRef],
    queryFn: () => BotsApi.deployments(botRef),
    enabled: Boolean(bot),
  });
  const [busy, setBusy] = useState<string | null>(null);

  if (isLoading || !bot) {
    return (
      <PageContainer title="Bot" subtitle="Loading…">
        <Card loading />
      </PageContainer>
    );
  }

  async function trigger(label: string, action: () => Promise<{ task_id: string; stream_url?: string | null }>): Promise<void> {
    setBusy(label);
    try {
      const result = await action();
      message.success(`${label} queued (task ${result.task_id})`);
      await refetchDeployments();
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const tabs = [
    {
      key: "overview",
      label: "Overview",
      children: (
        <Card size="small">
          <Space direction="vertical" style={{ width: "100%" }}>
            <Text strong>{bot.name}</Text>
            <Tag color={bot.kind === "research" ? "purple" : "blue"}>{bot.kind}</Tag>
            {bot.description ? <Paragraph type="secondary">{bot.description}</Paragraph> : null}
            <Text type="secondary" style={{ fontSize: 12 }}>
              slug: {bot.slug} · current version: {bot.current_version} · status: {bot.status}
            </Text>
            <Space wrap>
              <Button
                icon={<ExperimentOutlined />}
                loading={busy === "Backtest"}
                onClick={() => trigger("Backtest", () => BotsApi.backtest(bot.id))}
                disabled={!bot.spec.strategy || !bot.spec.backtest}
              >
                Backtest
              </Button>
              <Button
                icon={<PlayCircleOutlined />}
                loading={busy === "Paper"}
                onClick={() => trigger("Paper start", () => BotsApi.startPaper(bot.id))}
                disabled={bot.kind !== "trading"}
              >
                Start paper
              </Button>
              <Button
                type="primary"
                icon={<RocketOutlined />}
                loading={busy === "Deploy"}
                onClick={() => trigger("Deploy", () => BotsApi.deploy(bot.id))}
              >
                Deploy
              </Button>
              <Button
                icon={<CloudUploadOutlined />}
                loading={busy === "K8s render"}
                onClick={() =>
                  trigger("K8s render", () => BotsApi.deploy(bot.id, { target: "kubernetes" }))
                }
              >
                Render K8s manifest
              </Button>
            </Space>
          </Space>
        </Card>
      ),
    },
    {
      key: "builder",
      label: (
        <span>
          <EditOutlined /> Builder
        </span>
      ),
      children: <BotBuilder bot={bot} onSaved={() => refetch()} />,
    },
    {
      key: "deployments",
      label: "Deployments",
      children: (
        <Card size="small">
          {!deployments || deployments.length === 0 ? (
            <Empty description="No deployments yet" />
          ) : (
            <Table<BotDeploymentOut>
              rowKey="id"
              size="small"
              dataSource={deployments}
              pagination={{ pageSize: 25 }}
              columns={[
                { title: "Target", dataIndex: "target" },
                {
                  title: "Status",
                  dataIndex: "status",
                  render: (s: string) => (
                    <Tag color={s === "completed" ? "green" : s === "error" ? "red" : "gold"}>{s}</Tag>
                  ),
                },
                { title: "Task", dataIndex: "task_id", width: 220, ellipsis: true },
                { title: "Started", dataIndex: "started_at", width: 200 },
                { title: "Ended", dataIndex: "ended_at", width: 200 },
                { title: "Error", dataIndex: "error", ellipsis: true },
              ]}
            />
          )}
        </Card>
      ),
    },
    {
      key: "versions",
      label: "Versions",
      children: (
        <Card size="small">
          {!versions || versions.length === 0 ? (
            <Empty description="No versions" />
          ) : (
            <Table<BotVersionOut>
              rowKey="id"
              size="small"
              dataSource={versions}
              pagination={{ pageSize: 25 }}
              columns={[
                { title: "Version", dataIndex: "version", width: 100 },
                { title: "Hash", dataIndex: "spec_hash", ellipsis: true },
                { title: "Created", dataIndex: "created_at" },
                { title: "Notes", dataIndex: "notes" },
              ]}
            />
          )}
        </Card>
      ),
    },
  ];

  if (bot.kind === "research") {
    tabs.push({
      key: "chat",
      label: (
        <span>
          <MessageOutlined /> Chat
        </span>
      ),
      children: <ResearchBotChat botRef={bot.id} />,
    });
  }

  return (
    <PageContainer title={bot.name} subtitle={`Bot · ${bot.slug}`} full>
      <Tabs items={tabs} destroyOnHidden defaultActiveKey="overview" />
    </PageContainer>
  );
}
