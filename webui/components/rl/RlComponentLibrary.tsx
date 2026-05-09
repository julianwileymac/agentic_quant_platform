"use client";

import { Card, Empty, Input, Skeleton, Space, Tabs, Tag, Typography } from "antd";
import { useMemo, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";

const { Text, Paragraph } = Typography;

interface ComponentSchema {
  alias: string;
  kind: string;
  module: string;
  class: string;
  doc: string;
  properties: Record<string, unknown>;
  required: string[];
  tags: string[];
  source?: string | null;
  category?: string | null;
}

const KIND_LABELS: Record<string, string> = {
  rl_env: "Environments",
  rl_observation: "Observations",
  rl_action: "Actions",
  rl_reward: "Rewards",
  rl_termination: "Terminations",
  rl_policy: "Policies",
  rl_agent: "Agents",
  rl_data: "Data pipelines",
  rl_ensembler: "Ensemblers",
  rl_experiment: "Experiments",
  rl_trajectory_store: "Trajectory stores",
};

function ComponentTab({ kind }: { kind: string }) {
  const [filter, setFilter] = useState("");
  const { data, isLoading } = useApiQuery<{
    kind: string;
    components: Record<string, ComponentSchema>;
  }>({
    queryKey: ["rl", "components", kind],
    path: `/rl/components/${kind}`,
    staleTime: 60_000,
  });

  const items = useMemo(() => {
    const list = data ? Object.values(data.components) : [];
    if (!filter.trim()) return list;
    const needle = filter.toLowerCase();
    return list.filter(
      (c) =>
        c.alias.toLowerCase().includes(needle) ||
        (c.source ?? "").toLowerCase().includes(needle) ||
        (c.category ?? "").toLowerCase().includes(needle) ||
        c.tags.some((t) => t.toLowerCase().includes(needle)),
    );
  }, [data, filter]);

  if (isLoading) return <Skeleton active />;
  if (!items.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No components registered." />;
  }

  return (
    <div>
      <Input.Search
        allowClear
        placeholder="Search by alias / tag / source / category"
        onChange={(e) => setFilter(e.target.value)}
        style={{ marginBottom: 12 }}
      />
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: 12,
        }}
      >
        {items.map((c) => (
          <Card key={c.alias} size="small" title={c.alias} bordered>
            <Paragraph type="secondary" style={{ marginBottom: 8, fontSize: 12 }}>
              {c.doc || <em>No description.</em>}
            </Paragraph>
            <Space direction="vertical" size={2} style={{ width: "100%" }}>
              <Text style={{ fontSize: 11, color: "var(--ant-color-text-tertiary)" }}>
                {c.module}.{c.class}
              </Text>
              <Space wrap size={[4, 4]}>
                {c.source ? <Tag color="blue">source:{c.source}</Tag> : null}
                {c.category ? <Tag color="purple">{c.category}</Tag> : null}
                {c.tags.map((t) => (
                  <Tag key={t}>{t}</Tag>
                ))}
              </Space>
              {c.required.length ? (
                <Text style={{ fontSize: 11 }}>
                  required: <Text code>{c.required.join(", ")}</Text>
                </Text>
              ) : null}
            </Space>
          </Card>
        ))}
      </div>
    </div>
  );
}

export function RlComponentLibrary() {
  const { data } = useApiQuery<{ kinds: Record<string, number> }>({
    queryKey: ["rl", "components", "kinds"],
    path: "/rl/components",
    staleTime: 60_000,
  });

  const kinds = data?.kinds ?? {};
  const items = Object.keys(KIND_LABELS).map((kind) => ({
    key: kind,
    label: `${KIND_LABELS[kind]} (${kinds[kind] ?? 0})`,
    children: <ComponentTab kind={kind} />,
  }));

  return (
    <PageContainer
      title="RL component library"
      subtitle="Browse every registered env, reward, observation, action, policy, agent, data pipeline, ensembler, experiment, and trajectory store."
    >
      <Tabs items={items} />
    </PageContainer>
  );
}
