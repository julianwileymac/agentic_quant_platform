"use client";

import {
  Card,
  Col,
  Empty,
  Input,
  Row,
  Space,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";

const { Paragraph, Text } = Typography;

interface RegistryEntry {
  alias: string;
  module: string;
  source?: string | null;
  category?: string | null;
  tags?: string[];
}

export default function RlZooPage() {
  const [entries, setEntries] = useState<RegistryEntry[]>([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    apiFetch("/registry/agent")
      .then((d) => {
        const arr: RegistryEntry[] = Array.isArray(d) ? d : Object.values(d ?? {});
        setEntries(arr);
      })
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(
    () =>
      entries.filter(
        (e) =>
          !filter ||
          e.alias.toLowerCase().includes(filter.toLowerCase()) ||
          (e.module ?? "").toLowerCase().includes(filter.toLowerCase()),
      ),
    [entries, filter],
  );

  return (
    <PageContainer title="RL Agent Zoo">
      <Paragraph>
        Reinforcement-learning agents available for training. Pair an agent
        with one of the existing envs (StockTradingEnv, PortfolioAllocationEnv)
        via the RL training UI.
      </Paragraph>

      <Space style={{ marginBottom: 16 }}>
        <Input.Search
          placeholder="Search by name or module"
          onChange={(e) => setFilter(e.target.value)}
          style={{ width: 320 }}
          allowClear
        />
      </Space>

      {loading ? (
        <Empty description="Loading..." />
      ) : filtered.length === 0 ? (
        <Empty description="No RL agents registered" />
      ) : (
        <Row gutter={[16, 16]}>
          {filtered.map((e) => (
            <Col key={e.alias} xs={24} sm={12} md={8}>
              <Card
                title={e.alias}
                extra={e.source ? <Tag color="purple">{e.source}</Tag> : null}
                actions={[
                  <a
                    key="train"
                    href={`/rl?agent=${encodeURIComponent(e.alias)}`}
                  >
                    Train agent
                  </a>,
                ]}
              >
                <Paragraph style={{ marginBottom: 8 }}>
                  <Text type="secondary">{e.module}</Text>
                </Paragraph>
                {e.category && <Tag>{e.category}</Tag>}
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </PageContainer>
  );
}
