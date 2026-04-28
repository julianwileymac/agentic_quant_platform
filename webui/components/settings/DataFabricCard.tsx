"use client";

import { ReloadOutlined } from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Descriptions,
  InputNumber,
  Row,
  Space,
  Statistic,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";

import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";

const { Text, Paragraph } = Typography;

interface PartitionField {
  source_column: string;
  transform: string;
  name: string;
}

interface AlphaVantageEndpoint {
  id: string;
  label: string;
  category: string;
  iceberg_table?: string | null;
  iceberg_identifier?: string | null;
  partition_spec?: PartitionField[];
  domain?: string;
  cache_ttl_seconds?: number;
  cache_ttl_override?: number | null;
  enabled_for_bulk?: boolean;
  last_refreshed_at?: string | null;
}

interface SourceSummary {
  name: string;
  display_name: string;
  kind: string;
  vendor?: string;
  enabled: boolean;
  domains?: string[];
}

interface CatalogEntry {
  name: string;
  provider: string;
  domain: string;
  iceberg_identifier?: string | null;
  load_mode: string;
  updated_at?: string | null;
}

interface FabricOverview {
  sources: SourceSummary[];
  namespaces: string[];
  namespace_count: number;
  table_count: number;
  instrument_count: number;
  identifier_link_count: number;
  catalog_recent: CatalogEntry[];
  alpha_vantage_endpoints: AlphaVantageEndpoint[];
}

export function DataFabricCard() {
  const { message } = App.useApp();
  const overview = useApiQuery<FabricOverview>({
    queryKey: ["data-fabric", "overview"],
    path: "/data/fabric/overview",
    refetchInterval: 60_000,
  });
  const functions = useApiQuery<{ functions: AlphaVantageEndpoint[] }>({
    queryKey: ["alpha-vantage", "functions", "settings"],
    path: "/alpha-vantage/functions",
    refetchInterval: 60_000,
  });

  async function patchFunction(id: string, body: { enabled_for_bulk?: boolean; cache_ttl_seconds?: number }) {
    try {
      await apiFetch(`/alpha-vantage/functions/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      functions.refetch();
      overview.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <Card
      title="Data fabric"
      extra={
        <Button icon={<ReloadOutlined />} onClick={() => overview.refetch()}>
          Refresh
        </Button>
      }
    >
      {overview.error ? (
        <Alert
          type="error"
          showIcon
          message="Failed to load data fabric overview"
          description={(overview.error as Error).message}
        />
      ) : null}

      <Row gutter={16}>
        <Col xs={24} md={6}>
          <Statistic title="Data sources" value={overview.data?.sources?.length ?? 0} />
        </Col>
        <Col xs={24} md={6}>
          <Statistic title="Iceberg namespaces" value={overview.data?.namespace_count ?? 0} />
        </Col>
        <Col xs={24} md={6}>
          <Statistic title="Tables" value={overview.data?.table_count ?? 0} />
        </Col>
        <Col xs={24} md={6}>
          <Statistic
            title="Instruments / identifier links"
            value={`${overview.data?.instrument_count ?? 0} / ${overview.data?.identifier_link_count ?? 0}`}
          />
        </Col>
      </Row>

      <Card size="small" title="Sources" style={{ marginTop: 16 }}>
        <Table
          size="small"
          rowKey="name"
          dataSource={overview.data?.sources ?? []}
          loading={overview.isLoading}
          pagination={false}
          columns={[
            { title: "Name", dataIndex: "display_name", key: "display_name" },
            { title: "Vendor", dataIndex: "vendor", key: "vendor", render: (v) => v ?? "—" },
            { title: "Kind", dataIndex: "kind", key: "kind" },
            {
              title: "Enabled",
              dataIndex: "enabled",
              key: "enabled",
              render: (value: boolean) => (
                <Tag color={value ? "green" : "default"}>{value ? "yes" : "no"}</Tag>
              ),
            },
            {
              title: "Domains",
              dataIndex: "domains",
              key: "domains",
              render: (values: string[]) =>
                values && values.length ? (
                  <Space size={4} wrap>
                    {values.slice(0, 6).map((v) => (
                      <Tag key={v}>{v}</Tag>
                    ))}
                  </Space>
                ) : (
                  "—"
                ),
            },
          ]}
        />
      </Card>

      <Card
        size="small"
        title="AlphaVantage endpoint tables"
        style={{ marginTop: 16 }}
        extra={<Tag>aqp_alpha_vantage namespace</Tag>}
      >
        <Paragraph>
          Each AlphaVantage endpoint writes to a dedicated Iceberg table. Time-series tables are
          partitioned by symbol bucket + month; reference / fundamental tables are partitioned by
          symbol or month only.
        </Paragraph>
        <Table
          size="small"
          rowKey="id"
          dataSource={(functions.data?.functions ?? overview.data?.alpha_vantage_endpoints ?? []).filter(
            (entry) => entry.iceberg_identifier,
          )}
          pagination={false}
          columns={[
            { title: "Endpoint", dataIndex: "label", key: "label" },
            { title: "Category", dataIndex: "category", key: "category" },
            { title: "Iceberg table", dataIndex: "iceberg_identifier", key: "iceberg_identifier" },
            {
              title: "Partition spec",
              dataIndex: "partition_spec",
              key: "partition_spec",
              render: (values: PartitionField[] | undefined) =>
                values && values.length ? (
                  <Space size={4} wrap>
                    {values.map((f) => (
                      <Tag key={f.name}>{`${f.transform}(${f.source_column})`}</Tag>
                    ))}
                  </Space>
                ) : (
                  "—"
                ),
            },
            {
              title: "Bulk enabled",
              key: "enabled_for_bulk",
              render: (_value, row: AlphaVantageEndpoint) => (
                <Switch
                  size="small"
                  checked={Boolean(row.enabled_for_bulk)}
                  onChange={(checked) => patchFunction(row.id, { enabled_for_bulk: checked })}
                />
              ),
            },
            {
              title: "Cache TTL",
              key: "cache_ttl",
              render: (_value, row: AlphaVantageEndpoint) => (
                <Space size={4}>
                  <InputNumber
                    size="small"
                    min={0}
                    style={{ width: 90 }}
                    value={row.cache_ttl_override ?? row.cache_ttl_seconds ?? undefined}
                    onChange={(value) => {
                      const seconds = value === null ? 0 : Number(value);
                      patchFunction(row.id, { cache_ttl_seconds: seconds });
                    }}
                  />
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    s
                  </Text>
                </Space>
              ),
            },
            {
              title: "Last refresh",
              dataIndex: "last_refreshed_at",
              key: "last_refreshed_at",
              render: (value?: string | null) => value ?? "—",
            },
            {
              title: "Catalog",
              key: "open",
              render: (_value, row: AlphaVantageEndpoint) => {
                const ident = row.iceberg_identifier;
                if (!ident) {
                  return <Text type="secondary">—</Text>;
                }
                const dot = ident.indexOf(".");
                const ns = dot >= 0 ? ident.slice(0, dot) : ident;
                const table = dot >= 0 ? ident.slice(dot + 1) : "";
                const href = `/data/catalog/${encodeURIComponent(ns)}/${encodeURIComponent(table)}`;
                return (
                  <Button size="small" type="link" href={href}>
                    Open
                  </Button>
                );
              },
            },
          ]}
        />
      </Card>

      <Card size="small" title="Recent catalog entries" style={{ marginTop: 16 }}>
        <Table
          size="small"
          rowKey={(row) => `${row.iceberg_identifier ?? row.name}-${row.updated_at ?? ""}`}
          dataSource={overview.data?.catalog_recent ?? []}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: "Name", dataIndex: "name", key: "name" },
            { title: "Provider", dataIndex: "provider", key: "provider" },
            { title: "Domain", dataIndex: "domain", key: "domain" },
            { title: "Iceberg", dataIndex: "iceberg_identifier", key: "iceberg_identifier" },
            { title: "Load mode", dataIndex: "load_mode", key: "load_mode" },
            { title: "Updated", dataIndex: "updated_at", key: "updated_at" },
          ]}
        />
      </Card>

      <Descriptions style={{ marginTop: 16 }} size="small" column={1}>
        <Descriptions.Item label="Namespaces">
          {(overview.data?.namespaces ?? []).map((ns) => (
            <Tag key={ns}>{ns}</Tag>
          ))}
        </Descriptions.Item>
      </Descriptions>
    </Card>
  );
}
