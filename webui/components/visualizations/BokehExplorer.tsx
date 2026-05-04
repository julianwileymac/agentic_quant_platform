"use client";

import { ReloadOutlined } from "@ant-design/icons";
import {
  AutoComplete,
  Button,
  Card,
  Col,
  Form,
  InputNumber,
  Row,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";

import { BokehEmbed, type BokehChartSpec } from "@/components/visualizations/BokehEmbed";
import { useApiQuery } from "@/lib/api/hooks";

const { Text } = Typography;

interface DatasetSummary {
  identifier: string;
  schema: string;
  table: string;
  label: string;
  description?: string;
  tags?: string[];
  has_preset?: boolean;
}

interface DatasetColumn {
  name: string;
  dtype?: string;
}

const CHART_KINDS: BokehChartSpec["kind"][] = ["line", "scatter", "histogram", "candlestick", "table"];

/**
 * Interactive dataset / x / y / kind selector that re-mounts a `BokehEmbed`
 * whenever the user clicks "Render". The form is intentionally chatty (no
 * auto-render on every keystroke) so a heavy Iceberg scan only fires when
 * the user actually wants it.
 */
export function BokehExplorer() {
  const datasets = useApiQuery<{ datasets: DatasetSummary[] }>({
    queryKey: ["visualizations", "datasets"],
    path: "/visualizations/datasets",
  });

  const datasetOptions = useMemo(
    () =>
      (datasets.data?.datasets ?? []).map((ds) => ({
        label: `${ds.label}${ds.has_preset ? "" : " (live)"} — ${ds.identifier}`,
        value: ds.identifier,
        ds,
      })),
    [datasets.data],
  );

  const [identifier, setIdentifier] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (!identifier && datasetOptions.length > 0) {
      const equity = datasetOptions.find((opt) => opt.value === "aqp_equity.sp500_daily");
      setIdentifier(equity?.value ?? datasetOptions[0]?.value);
    }
  }, [datasetOptions, identifier]);

  const columns = useApiQuery<{ identifier: string; columns: DatasetColumn[] }>({
    queryKey: ["visualizations", "datasets", identifier ?? "", "columns"],
    path: identifier ? `/visualizations/datasets/${encodeURIComponent(identifier)}/columns` : "",
    enabled: Boolean(identifier),
  });

  const columnOptions = useMemo(
    () => (columns.data?.columns ?? []).map((col) => ({ label: `${col.name} (${col.dtype ?? "?"})`, value: col.name })),
    [columns.data],
  );

  const [kind, setKind] = useState<BokehChartSpec["kind"]>("line");
  const [x, setX] = useState<string>("timestamp");
  const [y, setY] = useState<string>("close");
  const [groupby, setGroupby] = useState<string>("vt_symbol");
  const [limit, setLimit] = useState<number>(1000);
  const [renderedSpec, setRenderedSpec] = useState<BokehChartSpec | null>(null);

  const activeDataset = datasetOptions.find((opt) => opt.value === identifier)?.ds;
  const tags = activeDataset?.tags ?? [];

  function handleRender() {
    if (!identifier) return;
    setRenderedSpec({
      kind,
      dataset_identifier: identifier,
      title: `${activeDataset?.label ?? identifier} (${kind})`,
      x,
      y,
      groupby: groupby || null,
      limit,
    });
  }

  return (
    <Card
      title="Interactive Bokeh Explorer"
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => datasets.refetch()}>
            Refresh datasets
          </Button>
        </Space>
      }
    >
      <Form layout="vertical">
        <Row gutter={[16, 16]}>
          <Col xs={24} md={12} lg={8}>
            <Form.Item label="Iceberg dataset">
              <Select
                showSearch
                placeholder="Select an Iceberg table"
                value={identifier}
                onChange={(val) => setIdentifier(val)}
                options={datasetOptions.map(({ label, value }) => ({ label, value }))}
                loading={datasets.isLoading}
                optionFilterProp="label"
              />
              {tags.length ? (
                <Space wrap style={{ marginTop: 8 }}>
                  {tags.map((tag) => (
                    <Tag key={tag}>{tag}</Tag>
                  ))}
                </Space>
              ) : null}
              {activeDataset?.description ? (
                <Text type="secondary" style={{ display: "block", marginTop: 8 }}>
                  {activeDataset.description}
                </Text>
              ) : null}
            </Form.Item>
          </Col>
          <Col xs={24} md={12} lg={4}>
            <Form.Item label="Kind">
              <Select<BokehChartSpec["kind"]>
                value={kind}
                onChange={(val) => setKind(val)}
                options={CHART_KINDS.map((k) => ({ label: k, value: k }))}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={12} lg={4}>
            <Form.Item label="x column">
              <AutoComplete
                value={x}
                onChange={(val) => setX(val)}
                options={columnOptions}
                placeholder="timestamp"
                filterOption
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={12} lg={4}>
            <Form.Item label="y column">
              <AutoComplete
                value={y}
                onChange={(val) => setY(val)}
                options={columnOptions}
                placeholder="close"
                filterOption
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={12} lg={4}>
            <Form.Item label="Group by">
              <AutoComplete
                value={groupby}
                onChange={(val) => setGroupby(val ?? "")}
                options={[{ label: "(none)", value: "" }, ...columnOptions]}
                placeholder="vt_symbol"
                filterOption
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={12} lg={4}>
            <Form.Item label="Row limit">
              <InputNumber
                value={limit}
                min={1}
                max={50000}
                onChange={(val) => setLimit(val ?? 1000)}
                style={{ width: "100%" }}
              />
            </Form.Item>
          </Col>
          <Col xs={24}>
            <Button type="primary" onClick={handleRender} disabled={!identifier}>
              Render chart
            </Button>
          </Col>
        </Row>
      </Form>

      {renderedSpec ? (
        <div style={{ marginTop: 24 }}>
          <BokehEmbed spec={renderedSpec} />
        </div>
      ) : (
        <Text type="secondary" style={{ display: "block", marginTop: 24 }}>
          Pick a dataset, choose a chart kind, then click Render. Charts are cached on the
          server (Redis + file) keyed on the Iceberg snapshot id, so re-rendering against
          unchanged data is effectively free.
        </Text>
      )}
    </Card>
  );
}
