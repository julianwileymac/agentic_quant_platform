"use client";

import { Card, Empty, Input, Select, Space, Table, Tag, Typography } from "antd";
import Link from "next/link";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";

const { Text } = Typography;

interface IssuerSummary {
  id: string;
  name: string;
  legal_name?: string | null;
  kind: string;
  cik?: string | null;
  lei?: string | null;
  sector?: string | null;
  industry?: string | null;
  country?: string | null;
  currency?: string | null;
  entity_status?: string | null;
}

const KIND_OPTIONS = [
  { value: "", label: "All kinds" },
  { value: "corporate", label: "Corporate" },
  { value: "government", label: "Government" },
  { value: "fund", label: "Fund" },
  { value: "central_bank", label: "Central bank" },
];

export function EntityList() {
  const [q, setQ] = useState("");
  const [kind, setKind] = useState<string>("");
  const [country, setCountry] = useState<string>("");
  const list = useApiQuery<IssuerSummary[]>({
    queryKey: ["entities", "issuers", q, kind, country],
    path: "/entities/issuers",
    query: { q, kind: kind || undefined, country: country || undefined, limit: 100 },
    staleTime: 15_000,
  });
  const items = list.data ?? [];

  return (
    <PageContainer
      title="Knowledge Graph — Issuers"
      subtitle="Corporate / government / fund entity browser. Pick a row to drill into the relationship graph."
    >
      <Card size="small">
        <Space wrap style={{ marginBottom: 12 }}>
          <Input.Search
            placeholder="Search name / legal name"
            allowClear
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ width: 280 }}
          />
          <Select
            value={kind}
            onChange={setKind}
            options={KIND_OPTIONS}
            style={{ width: 160 }}
          />
          <Input
            placeholder="Country (e.g. United States)"
            value={country}
            onChange={(e) => setCountry(e.target.value)}
            style={{ width: 220 }}
          />
        </Space>
        {items.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No issuers." />
        ) : (
          <Table
            size="small"
            rowKey="id"
            dataSource={items}
            pagination={{ pageSize: 25 }}
            columns={[
              {
                title: "Name",
                dataIndex: "name",
                render: (n: string, row) => (
                  <Link href={`/data/kg/${encodeURIComponent(row.id)}`}>
                    <Text strong>{n}</Text>
                  </Link>
                ),
              },
              {
                title: "Kind",
                dataIndex: "kind",
                width: 120,
                render: (k: string) => <Tag color="blue">{k}</Tag>,
              },
              { title: "Sector", dataIndex: "sector", width: 160 },
              { title: "Country", dataIndex: "country", width: 140 },
              { title: "CIK", dataIndex: "cik", width: 100 },
              { title: "LEI", dataIndex: "lei", width: 200 },
              {
                title: "Status",
                dataIndex: "entity_status",
                width: 100,
                render: (s: string | null) =>
                  s ? <Tag color={s === "active" ? "green" : "default"}>{s}</Tag> : null,
              },
            ]}
          />
        )}
      </Card>
    </PageContainer>
  );
}
