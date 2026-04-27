"use client";

import { ExperimentOutlined, ThunderboltOutlined } from "@ant-design/icons";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Collapse,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Row,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { useMemo, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiMutation, useApiQuery } from "@/lib/api/hooks";

const { Text, Paragraph } = Typography;

interface IndicatorParam {
  name: string;
  default: number | string | null;
  type: "int" | "float" | "str";
  description?: string;
}

interface IndicatorEntry {
  id: string;
  name: string;
  group: string;
  description: string;
  inputs: string[];
  outputs: string[];
  params: IndicatorParam[];
  engine: "talib" | "pandas_ta" | "native" | "none";
  can_compute: boolean;
}

interface CatalogResponse {
  engines: { talib: boolean; pandas_ta: boolean };
  groups: { name: string; indicators: IndicatorEntry[] }[];
  total: number;
}

interface PreviewResponse {
  vt_symbol: string;
  count: number;
  overlays: string[];
  bars: Record<string, number | string>[];
}

const ENGINE_COLORS: Record<string, string> = {
  talib: "geekblue",
  pandas_ta: "purple",
  native: "green",
  none: "default",
};

export function IndicatorCatalog() {
  const [search, setSearch] = useState("");
  const [groupFilter, setGroupFilter] = useState<string | null>(null);
  const [engineFilter, setEngineFilter] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<IndicatorEntry | null>(null);
  const [vtSymbol, setVtSymbol] = useState("AAPL.NASDAQ");
  const [paramValues, setParamValues] = useState<Record<string, number | string>>({});

  const catalog = useApiQuery<CatalogResponse>({
    queryKey: ["indicator-catalog"],
    path: "/data/indicators/catalog",
    staleTime: 5 * 60 * 1000,
  });

  const filteredGroups = useMemo(() => {
    if (!catalog.data) return [];
    const q = search.trim().toLowerCase();
    return catalog.data.groups
      .filter((g) => !groupFilter || g.name === groupFilter)
      .map((g) => ({
        ...g,
        indicators: g.indicators.filter(
          (ind) =>
            (!engineFilter || ind.engine === engineFilter) &&
            (!q ||
              ind.name.toLowerCase().includes(q) ||
              ind.description.toLowerCase().includes(q)),
        ),
      }))
      .filter((g) => g.indicators.length > 0);
  }, [catalog.data, search, groupFilter, engineFilter]);

  const preview = useApiMutation<
    { vt_symbol: string; indicators: string[] },
    PreviewResponse
  >({
    path: "/data/indicators/preview",
  });

  function openDrawer(ind: IndicatorEntry) {
    const initial: Record<string, number | string> = {};
    for (const p of ind.params) {
      if (p.default !== null && p.default !== undefined) initial[p.name] = p.default;
    }
    setParamValues(initial);
    setDrawer(ind);
    preview.reset();
  }

  function buildSpec(ind: IndicatorEntry): string {
    const tail = ind.params
      .map((p) => {
        const v = paramValues[p.name];
        if (v === undefined || v === "" || v === null) return null;
        return `${p.name}=${v}`;
      })
      .filter(Boolean)
      .join(",");
    return tail ? `${ind.name}:${tail}` : ind.name;
  }

  function runPreview() {
    if (!drawer) return;
    const spec = buildSpec(drawer);
    preview.mutate({ vt_symbol: vtSymbol, indicators: [spec] });
  }

  if (catalog.isLoading) {
    return (
      <PageContainer title="Indicator Catalog">
        <Spin />
      </PageContainer>
    );
  }
  if (catalog.error) {
    return (
      <PageContainer title="Indicator Catalog">
        <Alert type="error" message={catalog.error.message} />
      </PageContainer>
    );
  }

  const engines = catalog.data?.engines;
  const total = catalog.data?.total ?? 0;
  const groups = catalog.data?.groups ?? [];

  return (
    <PageContainer
      title="Indicator Catalog"
      subtitle={`${total} TA-Lib indicators across ${groups.length} groups`}
      extra={
        <Space>
          <Tooltip title="Computed via real TA-Lib (C-FFI) when available">
            <Tag color={engines?.talib ? "geekblue" : "default"}>
              talib: {engines?.talib ? "yes" : "no"}
            </Tag>
          </Tooltip>
          <Tooltip title="Pure-Python pandas-ta-classic fallback">
            <Tag color={engines?.pandas_ta ? "purple" : "default"}>
              pandas_ta: {engines?.pandas_ta ? "yes" : "no"}
            </Tag>
          </Tooltip>
        </Space>
      }
    >
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input.Search
            allowClear
            placeholder="Search by name or description"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 280 }}
          />
          <Space size={4}>
            <Tag.CheckableTag
              checked={groupFilter === null}
              onChange={() => setGroupFilter(null)}
            >
              all groups
            </Tag.CheckableTag>
            {groups.map((g) => (
              <Tag.CheckableTag
                key={g.name}
                checked={groupFilter === g.name}
                onChange={() => setGroupFilter(groupFilter === g.name ? null : g.name)}
              >
                {g.name}
              </Tag.CheckableTag>
            ))}
          </Space>
          <Space size={4}>
            <Tag.CheckableTag
              checked={engineFilter === null}
              onChange={() => setEngineFilter(null)}
            >
              all engines
            </Tag.CheckableTag>
            {(["talib", "pandas_ta", "native", "none"] as const).map((eng) => (
              <Tag.CheckableTag
                key={eng}
                checked={engineFilter === eng}
                onChange={() => setEngineFilter(engineFilter === eng ? null : eng)}
              >
                {eng}
              </Tag.CheckableTag>
            ))}
          </Space>
        </Space>
      </Card>
      {filteredGroups.length === 0 ? (
        <Empty description="No indicators match the current filters" />
      ) : (
        <Collapse
          defaultActiveKey={filteredGroups.map((g) => g.name)}
          items={filteredGroups.map((g) => ({
            key: g.name,
            label: (
              <Space>
                <Text strong>{g.name}</Text>
                <Badge count={g.indicators.length} />
              </Space>
            ),
            children: (
              <Row gutter={[12, 12]}>
                {g.indicators.map((ind) => (
                  <Col xs={24} sm={12} lg={8} xl={6} key={ind.id}>
                    <Card
                      size="small"
                      hoverable
                      onClick={() => openDrawer(ind)}
                      title={
                        <Space>
                          <ExperimentOutlined />
                          <Text strong>{ind.name}</Text>
                        </Space>
                      }
                      extra={<Tag color={ENGINE_COLORS[ind.engine]}>{ind.engine}</Tag>}
                    >
                      <Paragraph
                        type="secondary"
                        style={{ fontSize: 12, marginBottom: 6 }}
                        ellipsis={{ rows: 2 }}
                      >
                        {ind.description || "—"}
                      </Paragraph>
                      <div style={{ fontSize: 11 }}>
                        <Text type="secondary">inputs: </Text>
                        {ind.inputs.map((i) => (
                          <Tag key={i} color="blue">
                            {i}
                          </Tag>
                        ))}
                      </div>
                      <div style={{ fontSize: 11, marginTop: 4 }}>
                        <Text type="secondary">outputs: </Text>
                        {ind.outputs.map((o) => (
                          <Tag key={o} color="cyan">
                            {o}
                          </Tag>
                        ))}
                      </div>
                    </Card>
                  </Col>
                ))}
              </Row>
            ),
          }))}
        />
      )}
      <Drawer
        open={Boolean(drawer)}
        onClose={() => setDrawer(null)}
        title={drawer ? `${drawer.name} — ${drawer.group}` : ""}
        width={520}
      >
        {drawer ? (
          <>
            <Paragraph>{drawer.description}</Paragraph>
            <Tag color={ENGINE_COLORS[drawer.engine]}>engine: {drawer.engine}</Tag>
            <Tag color={drawer.can_compute ? "green" : "red"}>
              {drawer.can_compute ? "computable" : "metadata-only"}
            </Tag>
            <Form layout="vertical" style={{ marginTop: 16 }}>
              <Form.Item label="Symbol">
                <Input
                  value={vtSymbol}
                  onChange={(e) => setVtSymbol(e.target.value)}
                  placeholder="AAPL.NASDAQ"
                />
              </Form.Item>
              {drawer.params.map((p) => (
                <Form.Item
                  key={p.name}
                  label={
                    <Space>
                      <Text>{p.name}</Text>
                      {p.description ? (
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          ({p.description})
                        </Text>
                      ) : null}
                    </Space>
                  }
                >
                  {p.type === "str" ? (
                    <Input
                      value={(paramValues[p.name] ?? "") as string}
                      onChange={(e) =>
                        setParamValues({ ...paramValues, [p.name]: e.target.value })
                      }
                    />
                  ) : (
                    <InputNumber
                      style={{ width: "100%" }}
                      step={p.type === "float" ? 0.01 : 1}
                      value={paramValues[p.name] as number}
                      onChange={(v) =>
                        setParamValues({ ...paramValues, [p.name]: v ?? "" })
                      }
                    />
                  )}
                </Form.Item>
              ))}
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                onClick={runPreview}
                loading={preview.isPending}
                disabled={!drawer.can_compute}
              >
                Preview on {vtSymbol}
              </Button>
              {!drawer.can_compute ? (
                <Alert
                  style={{ marginTop: 8 }}
                  type="warning"
                  showIcon
                  message="No engine available to compute this indicator. Install talib or pandas-ta-classic."
                />
              ) : null}
            </Form>
            {preview.error ? (
              <Alert
                type="error"
                style={{ marginTop: 12 }}
                message={preview.error.message}
              />
            ) : null}
            {preview.data ? (
              <Card size="small" title="Preview" style={{ marginTop: 12 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {preview.data.count} rows · overlays: {preview.data.overlays.join(", ")}
                </Text>
                <Table
                  size="small"
                  rowKey={(r) => String(r.timestamp)}
                  pagination={{ pageSize: 10 }}
                  dataSource={preview.data.bars.slice(-50)}
                  columns={[
                    { title: "ts", dataIndex: "timestamp", width: 160 },
                    { title: "close", dataIndex: "close", width: 100 },
                    ...preview.data.overlays.map((o) => ({
                      title: o,
                      dataIndex: o,
                      width: 120,
                      render: (v: number | string) =>
                        typeof v === "number" && !Number.isNaN(v)
                          ? v.toFixed(4)
                          : String(v ?? "—"),
                    })),
                  ]}
                  scroll={{ x: 600 }}
                />
              </Card>
            ) : null}
          </>
        ) : null}
      </Drawer>
    </PageContainer>
  );
}
