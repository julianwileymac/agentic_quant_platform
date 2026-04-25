"use client";

import { ArrowLeftOutlined, NodeIndexOutlined } from "@ant-design/icons";
import {
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  List,
  Row,
  Skeleton,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { useRouter } from "next/navigation";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";

import { RelationshipGraph } from "./RelationshipGraph";

const { Text, Paragraph } = Typography;

interface IssuerDetailRow {
  id: string;
  name: string;
  legal_name?: string | null;
  kind: string;
  cik?: string | null;
  lei?: string | null;
  cusip?: string | null;
  isin?: string | null;
  figi?: string | null;
  sector?: string | null;
  industry?: string | null;
  country?: string | null;
  currency?: string | null;
  entity_status?: string | null;
  classifications: Array<{
    scheme: string;
    code: string;
    label?: string | null;
    level: number;
    parent_code?: string | null;
  }>;
  locations: Array<{
    country?: string | null;
    region?: string | null;
    state?: string | null;
    city?: string | null;
    is_headquarters?: boolean;
  }>;
  executives: Array<{
    name: string;
    title: string;
    tenure_start?: string | null;
    tenure_end?: string | null;
    compensation?: number | null;
    fiscal_year?: number | null;
  }>;
  relationships: Array<{
    relationship_type: string;
    from_entity_id: string;
    to_entity_id: string;
    ownership_pct?: number | null;
    valid_from?: string | null;
    valid_to?: string | null;
    source?: string | null;
  }>;
  instruments: Array<{
    id: string;
    vt_symbol: string;
    ticker?: string;
    exchange?: string | null;
    asset_class?: string | null;
    security_type?: string | null;
    is_active?: boolean;
  }>;
}

interface OwnershipPayload {
  holdings: Array<Record<string, unknown>>;
  insider: Array<Record<string, unknown>>;
}

export function EntityDetail({ entityId }: { entityId: string }) {
  const router = useRouter();
  const detail = useApiQuery<IssuerDetailRow>({
    queryKey: ["entities", "issuer", entityId],
    path: `/entities/issuers/${encodeURIComponent(entityId)}`,
  });
  const ownership = useApiQuery<OwnershipPayload>({
    queryKey: ["entities", "ownership", entityId],
    path: `/entities/issuers/${encodeURIComponent(entityId)}/ownership`,
  });
  const events = useApiQuery<Array<Record<string, unknown>>>({
    queryKey: ["entities", "events", entityId],
    path: `/entities/issuers/${encodeURIComponent(entityId)}/events`,
  });

  if (detail.isLoading || !detail.data) {
    return (
      <PageContainer title="Entity">
        <Skeleton active />
      </PageContainer>
    );
  }
  const e = detail.data;

  return (
    <PageContainer
      title={
        <Space>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => router.push("/data/kg")} />
          <NodeIndexOutlined />
          {e.name}
        </Space>
      }
      subtitle={e.legal_name ?? e.kind}
    >
      <Row gutter={16}>
        <Col xs={24} lg={10}>
          <Card title="Identity" size="small">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Kind">
                <Tag color="blue">{e.kind}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Sector">{e.sector ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="Industry">{e.industry ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="Country">{e.country ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="Currency">{e.currency ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="CIK">{e.cik ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="LEI">{e.lei ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="CUSIP">{e.cusip ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="ISIN">{e.isin ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="FIGI">{e.figi ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="Status">{e.entity_status ?? "—"}</Descriptions.Item>
            </Descriptions>
          </Card>
          <Card title="Locations" size="small" style={{ marginTop: 12 }}>
            {e.locations.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <List
                size="small"
                dataSource={e.locations}
                renderItem={(l, idx) => (
                  <List.Item key={idx}>
                    <Text>
                      {l.is_headquarters ? <Tag color="green">HQ</Tag> : null}
                      {[l.city, l.state, l.country].filter(Boolean).join(", ") || "—"}
                    </Text>
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card title="Relationship graph" size="small">
            <RelationshipGraph rootId={entityId} depth={2} />
          </Card>
        </Col>
      </Row>

      <Tabs
        style={{ marginTop: 16 }}
        items={[
          {
            key: "instruments",
            label: `Instruments (${e.instruments.length})`,
            children: (
              <Table
                size="small"
                rowKey="id"
                dataSource={e.instruments}
                pagination={{ pageSize: 25 }}
                columns={[
                  { title: "vt_symbol", dataIndex: "vt_symbol" },
                  { title: "Ticker", dataIndex: "ticker", width: 120 },
                  { title: "Exchange", dataIndex: "exchange", width: 120 },
                  { title: "Asset class", dataIndex: "asset_class", width: 140 },
                  { title: "Security type", dataIndex: "security_type", width: 140 },
                  {
                    title: "Active",
                    dataIndex: "is_active",
                    width: 80,
                    render: (a: boolean) =>
                      a ? <Tag color="green">yes</Tag> : <Tag>no</Tag>,
                  },
                ]}
              />
            ),
          },
          {
            key: "rels",
            label: `Relationships (${e.relationships.length})`,
            children: (
              <Table
                size="small"
                rowKey={(r, idx) => `${r.from_entity_id}-${r.to_entity_id}-${idx}`}
                dataSource={e.relationships}
                pagination={{ pageSize: 25 }}
                columns={[
                  { title: "Type", dataIndex: "relationship_type", width: 160 },
                  { title: "From", dataIndex: "from_entity_id" },
                  { title: "To", dataIndex: "to_entity_id" },
                  {
                    title: "Ownership %",
                    dataIndex: "ownership_pct",
                    render: (o: number | null) => (o == null ? "—" : `${(o * 100).toFixed(1)}%`),
                    width: 110,
                  },
                  { title: "From / To dates", render: (_, r) => `${r.valid_from ?? "—"} → ${r.valid_to ?? "—"}` },
                  { title: "Source", dataIndex: "source", width: 120 },
                ]}
              />
            ),
          },
          {
            key: "exec",
            label: `Executives (${e.executives.length})`,
            children: (
              <Table
                size="small"
                rowKey={(_, idx) => String(idx)}
                dataSource={e.executives}
                pagination={{ pageSize: 25 }}
                columns={[
                  { title: "Name", dataIndex: "name" },
                  { title: "Title", dataIndex: "title" },
                  { title: "Since", dataIndex: "tenure_start", width: 120 },
                  { title: "Until", dataIndex: "tenure_end", width: 120 },
                  {
                    title: "Compensation",
                    dataIndex: "compensation",
                    width: 140,
                    render: (c: number | null) =>
                      c == null ? "—" : c.toLocaleString(undefined, { maximumFractionDigits: 0 }),
                  },
                  { title: "FY", dataIndex: "fiscal_year", width: 80 },
                ]}
              />
            ),
          },
          {
            key: "cls",
            label: "Classifications",
            children: (
              <Table
                size="small"
                rowKey={(_, idx) => String(idx)}
                dataSource={e.classifications}
                pagination={false}
                columns={[
                  { title: "Scheme", dataIndex: "scheme", width: 120 },
                  { title: "Code", dataIndex: "code", width: 120 },
                  { title: "Label", dataIndex: "label" },
                  { title: "Level", dataIndex: "level", width: 80 },
                  { title: "Parent code", dataIndex: "parent_code", width: 140 },
                ]}
              />
            ),
          },
          {
            key: "own",
            label: `Ownership (${ownership.data?.holdings?.length ?? 0})`,
            children: ownership.data?.holdings?.length ? (
              <pre
                style={{
                  fontSize: 11,
                  maxHeight: 320,
                  overflow: "auto",
                  background: "var(--ant-color-bg-elevated)",
                  padding: 8,
                  borderRadius: 6,
                }}
              >
                {JSON.stringify(ownership.data.holdings.slice(0, 20), null, 2)}
              </pre>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No ownership data." />
            ),
          },
          {
            key: "events",
            label: `Events (${events.data?.length ?? 0})`,
            children: events.data?.length ? (
              <pre
                style={{
                  fontSize: 11,
                  maxHeight: 320,
                  overflow: "auto",
                  background: "var(--ant-color-bg-elevated)",
                  padding: 8,
                  borderRadius: 6,
                }}
              >
                {JSON.stringify(events.data.slice(0, 30), null, 2)}
              </pre>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No events." />
            ),
          },
        ]}
      />
    </PageContainer>
  );
}
