"use client";

import { Card, Col, Empty, Row, Skeleton, Space, Table, Tabs, Tag, Typography } from "antd";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";

const { Text, Paragraph, Title } = Typography;

interface TaxonomyMember {
  name: string;
  registered: boolean;
}

interface TaxonomyGroup {
  label: string;
  members?: TaxonomyMember[];
  install?: string;
  paradigms?: string[];
  framework?: string;
}

interface TaxonomyItem {
  key: string;
  label: string;
  description?: string;
  module?: string;
  class?: string;
}

interface TaxonomySection {
  title: string;
  groups?: Record<string, TaxonomyGroup>;
  items?: TaxonomyItem[];
}

interface TaxonomyAll {
  models?: TaxonomySection;
  forecasters?: TaxonomySection;
  paradigms?: TaxonomySection;
  time_series?: TaxonomySection;
  rl_envs?: TaxonomySection;
  rl_algos?: TaxonomySection;
  rl_applications?: TaxonomySection;
}

function GroupSection({ section }: { section: TaxonomySection }) {
  if (section.groups) {
    return (
      <Row gutter={[16, 16]}>
        {Object.entries(section.groups).map(([key, group]) => (
          <Col xs={24} md={12} key={key}>
            <Card size="small" title={group.label}>
              {group.install ? (
                <Paragraph type="secondary" style={{ marginBottom: 6 }}>
                  Install: <Text code>{group.install}</Text>
                </Paragraph>
              ) : null}
              {group.framework ? (
                <Paragraph type="secondary" style={{ marginBottom: 6 }}>
                  Framework: <Text code>{group.framework}</Text>
                </Paragraph>
              ) : null}
              {group.paradigms?.length ? (
                <Space wrap style={{ marginBottom: 8 }}>
                  {group.paradigms.map((p) => (
                    <Tag key={p} color="purple">
                      {p}
                    </Tag>
                  ))}
                </Space>
              ) : null}
              <Space wrap>
                {(group.members ?? []).map((m) => (
                  <Tag key={m.name} color={m.registered ? "blue" : "default"}>
                    {m.name}
                    {!m.registered ? " (not installed)" : ""}
                  </Tag>
                ))}
              </Space>
            </Card>
          </Col>
        ))}
      </Row>
    );
  }
  if (section.items) {
    return (
      <Table
        size="small"
        rowKey="key"
        dataSource={section.items}
        pagination={false}
        columns={[
          { title: "Key", dataIndex: "key", width: 220 },
          { title: "Label", dataIndex: "label" },
          { title: "Module / Class", render: (_, row) => row.module ? `${row.module}${row.class ? "." + row.class : ""}` : "—" },
          { title: "Description", dataIndex: "description" },
        ]}
      />
    );
  }
  return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />;
}

export function TaxonomyExplorer() {
  const { data, isLoading } = useApiQuery<TaxonomyAll>({
    queryKey: ["registry", "taxonomy", "all"],
    path: "/registry/taxonomy/all",
    staleTime: 60_000,
  });

  return (
    <PageContainer
      title="Learn / Taxonomy"
      subtitle="Catalog of supported ML models, forecasters, training paradigms, time-series methods, RL envs / algos / applications."
    >
      {isLoading || !data ? (
        <Skeleton active />
      ) : (
        <Tabs
          items={[
            {
              key: "models",
              label: "ML Models",
              children: data.models ? (
                <>
                  <Title level={4}>{data.models.title}</Title>
                  <GroupSection section={data.models} />
                </>
              ) : (
                <Empty />
              ),
            },
            {
              key: "forecasters",
              label: "Forecasters",
              children: data.forecasters ? (
                <>
                  <Title level={4}>{data.forecasters.title}</Title>
                  <GroupSection section={data.forecasters} />
                </>
              ) : (
                <Empty />
              ),
            },
            {
              key: "paradigms",
              label: "Paradigms",
              children: data.paradigms ? (
                <>
                  <Title level={4}>{data.paradigms.title}</Title>
                  <GroupSection section={data.paradigms} />
                </>
              ) : (
                <Empty />
              ),
            },
            {
              key: "ts",
              label: "Time series",
              children: data.time_series ? (
                <>
                  <Title level={4}>{data.time_series.title}</Title>
                  <GroupSection section={data.time_series} />
                </>
              ) : (
                <Empty />
              ),
            },
            {
              key: "rl_envs",
              label: "RL envs",
              children: data.rl_envs ? (
                <>
                  <Title level={4}>{data.rl_envs.title}</Title>
                  <GroupSection section={data.rl_envs} />
                </>
              ) : (
                <Empty />
              ),
            },
            {
              key: "rl_algos",
              label: "RL algos",
              children: data.rl_algos ? (
                <>
                  <Title level={4}>{data.rl_algos.title}</Title>
                  <GroupSection section={data.rl_algos} />
                </>
              ) : (
                <Empty />
              ),
            },
            {
              key: "rl_apps",
              label: "RL applications",
              children: data.rl_applications ? (
                <>
                  <Title level={4}>{data.rl_applications.title}</Title>
                  <GroupSection section={data.rl_applications} />
                </>
              ) : (
                <Empty />
              ),
            },
          ]}
        />
      )}
    </PageContainer>
  );
}
