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

interface AgentSpecRow {
  name: string;
  role: string;
  description?: string;
  annotations?: string[];
}

export default function AgentTemplatesPage() {
  const [specs, setSpecs] = useState<AgentSpecRow[]>([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    apiFetch("/agents/specs")
      .then((d) => setSpecs(Array.isArray(d) ? d : []))
      .catch(() => setSpecs([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(
    () =>
      specs.filter(
        (s) =>
          !filter ||
          s.name.toLowerCase().includes(filter.toLowerCase()) ||
          s.role.toLowerCase().includes(filter.toLowerCase()),
      ),
    [specs, filter],
  );

  return (
    <PageContainer title="Agent Templates">
      <Paragraph>
        Reusable agent personas. Click &quot;Use this template&quot; to launch
        the AgentBacktestWizard with the spec preselected.
      </Paragraph>

      <Space style={{ marginBottom: 16 }}>
        <Input.Search
          placeholder="Filter templates"
          onChange={(e) => setFilter(e.target.value)}
          style={{ width: 320 }}
          allowClear
        />
      </Space>

      {loading ? (
        <Empty description="Loading..." />
      ) : filtered.length === 0 ? (
        <Empty description="No agent templates available" />
      ) : (
        <Row gutter={[16, 16]}>
          {filtered.map((s) => (
            <Col key={s.name} xs={24} sm={12} md={8} lg={6}>
              <Card
                title={s.name}
                extra={<Tag color="cyan">{s.role}</Tag>}
                actions={[
                  <a
                    key="use"
                    href={`/backtest/new?agent=${encodeURIComponent(s.name)}`}
                  >
                    Use this template
                  </a>,
                ]}
              >
                <Paragraph
                  ellipsis={{ rows: 3, expandable: true, symbol: "more" }}
                >
                  <Text type="secondary">{s.description}</Text>
                </Paragraph>
                {s.annotations?.map((a) => (
                  <Tag key={a}>{a}</Tag>
                ))}
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </PageContainer>
  );
}
