"use client";

import { PlusOutlined, RobotOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, Empty, Space, Table, Tag, Typography } from "antd";
import Link from "next/link";

import { PageContainer } from "@/components/shell/PageContainer";
import { BotsApi, type BotSummary } from "@/lib/api/bots";

const { Text } = Typography;


export function BotsListPage() {
  const { data, isLoading } = useQuery<BotSummary[]>({
    queryKey: ["bots", "list"],
    queryFn: () => BotsApi.list({ limit: 200 }),
  });
  const bots: BotSummary[] = data ?? [];

  return (
    <PageContainer
      title="Bots"
      subtitle="The smallest self-contained, deployable unit on AQP."
      extra={
        <Link href="/bots/new">
          <Button type="primary" icon={<PlusOutlined />}>
            New Bot
          </Button>
        </Link>
      }
    >
      <Card size="small" loading={isLoading}>
        {bots.length === 0 && !isLoading ? (
          <Empty
            description="No bots yet."
            image={<RobotOutlined style={{ fontSize: 48, opacity: 0.3 }} />}
          >
            <Link href="/bots/new">
              <Button type="primary">Create your first bot</Button>
            </Link>
          </Empty>
        ) : (
          <Table<BotSummary>
            rowKey="id"
            size="small"
            pagination={{ pageSize: 25 }}
            dataSource={bots}
            columns={[
              {
                title: "Name",
                dataIndex: "name",
                render: (name: string, row: BotSummary) => (
                  <Link href={`/bots/${row.id}`}>
                    <Space direction="vertical" size={0}>
                      <Text strong>{name}</Text>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {row.slug}
                      </Text>
                    </Space>
                  </Link>
                ),
              },
              {
                title: "Kind",
                dataIndex: "kind",
                render: (kind: string) => (
                  <Tag color={kind === "research" ? "purple" : "blue"}>{kind}</Tag>
                ),
              },
              {
                title: "Status",
                dataIndex: "status",
                render: (status: string) => {
                  const colour =
                    status === "deployed" ? "green" : status === "ready" ? "blue" : status === "archived" ? "default" : "gold";
                  return <Tag color={colour}>{status}</Tag>;
                },
              },
              {
                title: "Version",
                dataIndex: "current_version",
                width: 90,
              },
              {
                title: "Updated",
                dataIndex: "updated_at",
                width: 200,
                render: (ts: string) => (
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {new Date(ts).toLocaleString()}
                  </Text>
                ),
              },
            ]}
          />
        )}
      </Card>
    </PageContainer>
  );
}
