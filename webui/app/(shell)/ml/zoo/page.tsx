"use client";

import {
  Card,
  Col,
  Empty,
  Input,
  Row,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";

const { Title, Paragraph, Text } = Typography;

interface RegistryEntry {
  alias: string;
  module: string;
  source?: string | null;
  category?: string | null;
  tags?: string[];
  doc?: string | null;
}

const SOURCE_OPTIONS = [
  { value: "all", label: "All sources" },
  { value: "stock_prediction_models", label: "Stock-Prediction-Models" },
  { value: "notebooks", label: "Notebooks" },
  { value: "akquant", label: "Akquant" },
  { value: "sae", label: "Stock-Analysis-Engine" },
];

export default function MlZooPage() {
  const [entries, setEntries] = useState<RegistryEntry[]>([]);
  const [filter, setFilter] = useState("");
  const [source, setSource] = useState<string>("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    apiFetch("/registry/model")
      .then((d) => {
        const arr: RegistryEntry[] = Array.isArray(d) ? d : Object.values(d ?? {});
        setEntries(arr);
      })
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    return entries.filter((e) => {
      const matchesText =
        !filter ||
        e.alias.toLowerCase().includes(filter.toLowerCase()) ||
        (e.module ?? "").toLowerCase().includes(filter.toLowerCase());
      const matchesSource = source === "all" || e.source === source;
      return matchesText && matchesSource;
    });
  }, [entries, filter, source]);

  return (
    <PageContainer title="ML Model Zoo">
      <Paragraph>
        Browseable catalog of every ML forecaster registered in the platform.
        Use a card&apos;s &quot;Train from this template&quot; link to launch the
        ML Training wizard with the model preselected.
      </Paragraph>

      <Space style={{ marginBottom: 16 }}>
        <Input.Search
          placeholder="Search by name or module"
          onChange={(e) => setFilter(e.target.value)}
          style={{ width: 320 }}
          allowClear
        />
        <Select
          value={source}
          onChange={setSource}
          style={{ width: 240 }}
          options={SOURCE_OPTIONS}
        />
      </Space>

      {loading ? (
        <Empty description="Loading..." />
      ) : filtered.length === 0 ? (
        <Empty description="No matching ML models" />
      ) : (
        <Row gutter={[16, 16]}>
          {filtered.map((e) => (
            <Col key={e.alias} xs={24} sm={12} md={8} lg={6}>
              <Card
                title={e.alias}
                extra={e.source ? <Tag color="blue">{e.source}</Tag> : null}
                actions={[
                  <a
                    key="train"
                    href={`/ml/training?model=${encodeURIComponent(e.alias)}`}
                  >
                    Train from this template
                  </a>,
                ]}
              >
                <Paragraph style={{ marginBottom: 8 }}>
                  <Text type="secondary">{e.module}</Text>
                </Paragraph>
                {e.category && <Tag>{e.category}</Tag>}
                {e.tags?.map((t) => (
                  <Tag key={t}>{t}</Tag>
                ))}
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </PageContainer>
  );
}
