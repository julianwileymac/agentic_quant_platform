"use client";

import { ReloadOutlined, ThunderboltOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Input,
  List,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { useMemo, useState } from "react";

import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";

const { Text } = Typography;

export interface DataSourcePayload {
  id: string;
  name: string;
  kind: string;
  config: Record<string, unknown>;
}

interface DataSourceRow extends DataSourcePayload {
  enabled: boolean;
}

interface CatalogTable {
  iceberg_identifier: string;
  namespace: string;
  name: string;
  description?: string | null;
  domain?: string | null;
  tags?: string[];
  row_count?: number | null;
  file_count?: number | null;
}

interface PreviewBarsResponse {
  iceberg_identifier: string;
  n_rows: number;
  min_ts: string | null;
  max_ts: string | null;
  n_symbols: number | null;
  vt_symbols: string[];
  columns: string[];
  timestamp_column: string | null;
  symbol_column: string | null;
}

export interface DatasetCatalogPickerProps {
  value: DataSourcePayload | null;
  onChange: (payload: DataSourcePayload | null) => void;
  startHint?: string;
  endHint?: string;
  onSymbolsDetected?: (symbols: string[]) => void;
}

export function DatasetCatalogPicker({
  value,
  onChange,
  startHint,
  endHint,
  onSymbolsDetected,
}: DatasetCatalogPickerProps) {
  const dataSources = useApiQuery<DataSourceRow[]>({
    queryKey: ["backtest", "data-sources", "picker"],
    path: "/backtest/data-sources",
    staleTime: 15_000,
    select: (raw) => (Array.isArray(raw) ? (raw as DataSourceRow[]) : []),
  });
  const catalogTables = useApiQuery<CatalogTable[]>({
    queryKey: ["datasets", "tables", "picker"],
    path: "/datasets/tables",
    staleTime: 15_000,
    select: (raw) => (Array.isArray(raw) ? (raw as CatalogTable[]) : []),
  });

  const [activeTab, setActiveTab] = useState<"sources" | "iceberg" | "adhoc">("sources");
  const [icebergSearch, setIcebergSearch] = useState("");
  const [adHocKind, setAdHocKind] = useState<"parquet_root" | "iceberg_table">("parquet_root");
  const [adHocParquet, setAdHocParquet] = useState("");
  const [adHocIceberg, setAdHocIceberg] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [preview, setPreview] = useState<PreviewBarsResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const filteredCatalog = useMemo(() => {
    const q = icebergSearch.trim().toLowerCase();
    const all = catalogTables.data ?? [];
    if (!q) return all.slice(0, 200);
    return all
      .filter(
        (t) =>
          t.iceberg_identifier.toLowerCase().includes(q) ||
          (t.description ?? "").toLowerCase().includes(q) ||
          (t.tags ?? []).some((tag) => tag.toLowerCase().includes(q)),
      )
      .slice(0, 200);
  }, [catalogTables.data, icebergSearch]);

  function selectSourceRow(row: DataSourceRow) {
    onChange({
      id: row.id,
      name: row.name,
      kind: row.kind,
      config: row.config ?? {},
    });
    setPreview(null);
    setPreviewError(null);
  }

  function selectCatalogRow(row: CatalogTable) {
    onChange({
      id: `iceberg-${row.iceberg_identifier}`,
      name: `${row.namespace}.${row.name}`,
      kind: "iceberg_table",
      config: { iceberg_identifier: row.iceberg_identifier },
    });
    setPreview(null);
    setPreviewError(null);
  }

  function applyAdHoc() {
    if (adHocKind === "parquet_root" && adHocParquet.trim()) {
      onChange({
        id: "adhoc-parquet",
        name: "Ad-hoc parquet root",
        kind: "parquet_root",
        config: { parquet_root: adHocParquet.trim() },
      });
      setPreview(null);
      setPreviewError(null);
    } else if (adHocKind === "iceberg_table" && adHocIceberg.trim()) {
      onChange({
        id: "adhoc-iceberg",
        name: "Ad-hoc Iceberg table",
        kind: "iceberg_table",
        config: { iceberg_identifier: adHocIceberg.trim() },
      });
      setPreview(null);
      setPreviewError(null);
    }
  }

  async function runPreview() {
    if (!value) return;
    setPreviewLoading(true);
    setPreview(null);
    setPreviewError(null);
    try {
      if (value.kind === "iceberg_table") {
        const ident = String(value.config?.iceberg_identifier ?? "");
        const [ns, name] = ident.split(".");
        if (!ns || !name) {
          throw new Error("iceberg identifier must be 'namespace.name'");
        }
        const data = await apiFetch<PreviewBarsResponse>(
          `/datasets/${encodeURIComponent(ns)}/${encodeURIComponent(name)}/preview-bars`,
          { query: { start: startHint, end: endHint } },
        );
        setPreview(data);
        if (data.vt_symbols?.length && onSymbolsDetected) {
          onSymbolsDetected(data.vt_symbols);
        }
      } else if (value.kind === "parquet_root") {
        // No catalog-level preview; just acknowledge.
        setPreview({
          iceberg_identifier: "",
          n_rows: 0,
          min_ts: null,
          max_ts: null,
          n_symbols: null,
          vt_symbols: [],
          columns: [],
          timestamp_column: null,
          symbol_column: null,
        });
      } else {
        setPreview({
          iceberg_identifier: "",
          n_rows: 0,
          min_ts: null,
          max_ts: null,
          n_symbols: null,
          vt_symbols: [],
          columns: [],
          timestamp_column: null,
          symbol_column: null,
        });
      }
    } catch (err) {
      setPreviewError((err as Error).message);
    } finally {
      setPreviewLoading(false);
    }
  }

  return (
    <Card size="small">
      <Tabs
        activeKey={activeTab}
        onChange={(k) => setActiveTab(k as "sources" | "iceberg" | "adhoc")}
        items={[
          {
            key: "sources",
            label: "Configured sources",
            children: (
              <Space direction="vertical" style={{ width: "100%" }}>
                <Space>
                  <Button
                    size="small"
                    icon={<ReloadOutlined />}
                    onClick={() => dataSources.refetch()}
                  >
                    Refresh
                  </Button>
                  <Text type="secondary">
                    Manage these in <a href="/settings">Settings → Backtest data sources</a>.
                  </Text>
                </Space>
                <Table<DataSourceRow>
                  size="small"
                  rowKey="id"
                  loading={dataSources.isLoading}
                  pagination={{ pageSize: 6 }}
                  dataSource={(dataSources.data ?? []).filter((s) => s.enabled)}
                  rowSelection={{
                    type: "radio",
                    selectedRowKeys: value?.id ? [value.id] : [],
                    onChange: (_, rows) => {
                      if (rows[0]) selectSourceRow(rows[0]);
                    },
                  }}
                  onRow={(row) => ({
                    onClick: () => selectSourceRow(row),
                  })}
                  columns={[
                    { title: "Name", dataIndex: "name", key: "name" },
                    {
                      title: "Kind",
                      dataIndex: "kind",
                      key: "kind",
                      render: (v: string) => <Tag>{v}</Tag>,
                    },
                    {
                      title: "Config",
                      dataIndex: "config",
                      key: "config",
                      render: (cfg: unknown) => (
                        <code style={{ fontSize: 11 }}>{JSON.stringify(cfg ?? {})}</code>
                      ),
                    },
                  ]}
                />
              </Space>
            ),
          },
          {
            key: "iceberg",
            label: "Iceberg catalog",
            children: (
              <Space direction="vertical" style={{ width: "100%" }}>
                <Space style={{ width: "100%" }}>
                  <Input.Search
                    placeholder="Search by namespace, name, tag, description"
                    value={icebergSearch}
                    onChange={(e) => setIcebergSearch(e.target.value)}
                    allowClear
                    style={{ width: 360 }}
                  />
                  <Button
                    size="small"
                    icon={<ReloadOutlined />}
                    onClick={() => catalogTables.refetch()}
                  >
                    Refresh
                  </Button>
                </Space>
                <Table<CatalogTable>
                  size="small"
                  rowKey="iceberg_identifier"
                  loading={catalogTables.isLoading}
                  pagination={{ pageSize: 8 }}
                  dataSource={filteredCatalog}
                  rowSelection={{
                    type: "radio",
                    selectedRowKeys:
                      value?.kind === "iceberg_table"
                        ? [String(value.config?.iceberg_identifier ?? "")]
                        : [],
                    onChange: (_, rows) => {
                      if (rows[0]) selectCatalogRow(rows[0]);
                    },
                  }}
                  onRow={(row) => ({
                    onClick: () => selectCatalogRow(row),
                  })}
                  columns={[
                    {
                      title: "Identifier",
                      dataIndex: "iceberg_identifier",
                      key: "iceberg_identifier",
                      render: (v: string) => <code>{v}</code>,
                    },
                    { title: "Domain", dataIndex: "domain", key: "domain" },
                    {
                      title: "Tags",
                      dataIndex: "tags",
                      key: "tags",
                      render: (tags: string[] | undefined) => (
                        <Space wrap size={4}>
                          {(tags ?? []).slice(0, 4).map((t) => (
                            <Tag key={t}>{t}</Tag>
                          ))}
                        </Space>
                      ),
                    },
                    {
                      title: "Rows",
                      dataIndex: "row_count",
                      key: "row_count",
                      render: (v: number | null | undefined) =>
                        v == null ? "—" : v.toLocaleString(),
                    },
                  ]}
                />
              </Space>
            ),
          },
          {
            key: "adhoc",
            label: "Ad-hoc",
            children: (
              <Space direction="vertical" style={{ width: "100%" }}>
                <Row gutter={12}>
                  <Col span={6}>
                    <Select
                      style={{ width: "100%" }}
                      value={adHocKind}
                      onChange={(v) => setAdHocKind(v)}
                      options={[
                        { value: "parquet_root", label: "Parquet root" },
                        { value: "iceberg_table", label: "Iceberg table" },
                      ]}
                    />
                  </Col>
                  <Col span={14}>
                    {adHocKind === "parquet_root" ? (
                      <Input
                        value={adHocParquet}
                        onChange={(e) => setAdHocParquet(e.target.value)}
                        placeholder="C:/data/parquet/source"
                      />
                    ) : (
                      <Input
                        value={adHocIceberg}
                        onChange={(e) => setAdHocIceberg(e.target.value)}
                        placeholder="aqp.bars_yfinance"
                      />
                    )}
                  </Col>
                  <Col span={4}>
                    <Button type="primary" onClick={applyAdHoc} block>
                      Apply
                    </Button>
                  </Col>
                </Row>
                <Alert
                  type="info"
                  showIcon
                  message="Ad-hoc sources aren't persisted; for repeatable backtests, register them in Settings → Backtest data sources."
                />
              </Space>
            ),
          },
        ]}
      />

      <Card size="small" title="Selected source" style={{ marginTop: 12 }}>
        {value ? (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Descriptions column={2} size="small">
              <Descriptions.Item label="Name">{value.name}</Descriptions.Item>
              <Descriptions.Item label="Kind">
                <Tag>{value.kind}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Config" span={2}>
                <code style={{ fontSize: 11 }}>{JSON.stringify(value.config ?? {})}</code>
              </Descriptions.Item>
            </Descriptions>
            <Space>
              <Button
                size="small"
                type="primary"
                icon={<ThunderboltOutlined />}
                loading={previewLoading}
                onClick={runPreview}
              >
                Preview availability
              </Button>
              <Button size="small" onClick={() => onChange(null)} danger>
                Clear
              </Button>
            </Space>
            {previewError ? (
              <Alert type="error" showIcon message={previewError} />
            ) : null}
            {previewLoading ? <Spin /> : null}
            {preview && value.kind === "iceberg_table" ? (
              <Descriptions column={2} size="small" bordered>
                <Descriptions.Item label="Rows">
                  {preview.n_rows.toLocaleString()}
                </Descriptions.Item>
                <Descriptions.Item label="Symbols">
                  {preview.n_symbols ?? "—"}
                </Descriptions.Item>
                <Descriptions.Item label="Date range" span={2}>
                  {preview.min_ts ?? "—"} → {preview.max_ts ?? "—"}
                </Descriptions.Item>
                <Descriptions.Item label="Symbol column">
                  <code>{preview.symbol_column ?? "—"}</code>
                </Descriptions.Item>
                <Descriptions.Item label="Timestamp column">
                  <code>{preview.timestamp_column ?? "—"}</code>
                </Descriptions.Item>
                {preview.vt_symbols.length ? (
                  <Descriptions.Item label="Sample symbols" span={2}>
                    <Space wrap size={4}>
                      {preview.vt_symbols.slice(0, 30).map((s) => (
                        <Tag key={s}>{s}</Tag>
                      ))}
                      {preview.vt_symbols.length > 30 ? (
                        <Text type="secondary">+{preview.vt_symbols.length - 30} more</Text>
                      ) : null}
                    </Space>
                  </Descriptions.Item>
                ) : null}
                {preview.columns.length ? (
                  <Descriptions.Item label="Columns" span={2}>
                    <List
                      size="small"
                      grid={{ column: 4, gutter: 4 }}
                      dataSource={preview.columns}
                      renderItem={(c) => (
                        <List.Item style={{ padding: 0 }}>
                          <code style={{ fontSize: 11 }}>{c}</code>
                        </List.Item>
                      )}
                    />
                  </Descriptions.Item>
                ) : null}
              </Descriptions>
            ) : null}
          </Space>
        ) : (
          <Text type="secondary">Pick a configured source, an Iceberg table, or an ad-hoc path.</Text>
        )}
      </Card>
    </Card>
  );
}
