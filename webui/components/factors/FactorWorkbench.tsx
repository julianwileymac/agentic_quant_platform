"use client";

import { ExportOutlined } from "@ant-design/icons";
import {
  App,
  Button,
  Card,
  Col,
  Drawer,
  Input,
  List,
  Modal,
  Row,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import dynamic from "next/dynamic";
import { useState } from "react";

import { DataGrid, NumberCellFormatter } from "@/components/data-grid";
import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";

const MonacoEditor = dynamic(() => import("@monaco-editor/react").then((m) => m.default), {
  ssr: false,
});

const { Text } = Typography;

interface FactorOperator {
  name: string;
  description?: string;
  signature?: string;
  category?: string;
}

interface FactorPreviewRow {
  vt_symbol: string;
  factor?: number | null;
  close?: number | null;
  timestamp?: string;
}

type IcMap = Record<string, number | Record<string, number>>;

interface FactorPreview {
  formula: string;
  rows?: FactorPreviewRow[];
  summary?: IcMap;
  n_rows?: number;
  n_symbols?: number;
  message?: string;
}

interface IndicatorEntry {
  id: string;
  name: string;
  group: string;
  description: string;
  outputs: string[];
}

interface CatalogResponse {
  groups: { name: string; indicators: IndicatorEntry[] }[];
}

interface UniverseEntry {
  ticker?: string;
  vt_symbol?: string;
}

interface UniverseResponse {
  items?: UniverseEntry[];
}

const DEFAULT_FORMULA = `# A factor expression in the AQP DSL.
# Rank-normalize the negative 1-month return; classic mean-reversion alpha.
Rank(Mul(-1, Sub(Ref(close, 0), Ref(close, 21))))`;

const DEFAULT_SYMBOLS = ["AAPL.NASDAQ", "MSFT.NASDAQ", "GOOG.NASDAQ"];

function meanIc(summary: IcMap | undefined): number | undefined {
  if (!summary) return undefined;
  for (const v of Object.values(summary)) {
    if (typeof v === "number") return v;
    if (v && typeof v === "object" && typeof v.mean === "number") return v.mean;
  }
  return undefined;
}

function maxIr(summary: IcMap | undefined): number | undefined {
  if (!summary) return undefined;
  let best: number | undefined;
  for (const v of Object.values(summary)) {
    if (v && typeof v === "object" && typeof v.ir === "number") {
      if (best === undefined || v.ir > best) best = v.ir;
    }
  }
  return best;
}

export function FactorWorkbench() {
  const { message } = App.useApp();
  const [formula, setFormula] = useState(DEFAULT_FORMULA);
  const [preview, setPreview] = useState<FactorPreview | null>(null);
  const [symbols, setSymbols] = useState<string[]>(DEFAULT_SYMBOLS);
  const [start, setStart] = useState<string>("2023-01-01");
  const [end, setEnd] = useState<string>("");
  const [drawer, setDrawer] = useState<"indicators" | "flink" | null>(null);
  const [flinkJob, setFlinkJob] = useState<string>("");

  const operators = useApiQuery<FactorOperator[]>({
    queryKey: ["factors", "operators"],
    path: "/factors/operators",
    select: (raw) => (Array.isArray(raw) ? (raw as FactorOperator[]) : []),
  });

  const catalog = useApiQuery<CatalogResponse>({
    queryKey: ["indicator-catalog"],
    path: "/data/indicators/catalog",
    staleTime: 5 * 60 * 1000,
  });

  const universe = useApiQuery<UniverseResponse>({
    queryKey: ["data", "universe", "factor-picker"],
    path: "/data/universe",
    query: { limit: 200 },
    staleTime: 5 * 60 * 1000,
  });

  async function evaluate() {
    if (symbols.length === 0) {
      message.warning("Pick at least one symbol");
      return;
    }
    try {
      const res = await apiFetch<FactorPreview>("/factors/preview", {
        method: "POST",
        body: JSON.stringify({ symbols, formula, start, end: end || undefined }),
      });
      setPreview(res);
      message.success(`Returned ${res.rows?.length ?? 0} rows · ${res.n_symbols ?? 0} symbols`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  function insertIndicator(ind: IndicatorEntry) {
    const snippet = `Mean(${ind.outputs[0] ?? "close"}, 14)  # via ${ind.name}`;
    setFormula((f) => `${f}\n${snippet}`);
    setDrawer(null);
  }

  async function exportToFlink() {
    if (!flinkJob.trim()) {
      message.warning("Enter a job name");
      return;
    }
    try {
      const res = await apiFetch<{ job_id: string; topic: string }>("/factors/export/flink", {
        method: "POST",
        body: JSON.stringify({
          job_name: flinkJob.trim(),
          formula,
          symbols,
        }),
      });
      message.success(`Flink job submitted: ${res.job_id} → ${res.topic}`);
      setDrawer(null);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  const universeOptions = (universe.data?.items ?? []).map((it) => {
    const vt = it.vt_symbol ?? `${it.ticker ?? ""}.NASDAQ`;
    return { value: vt, label: vt };
  });

  return (
    <PageContainer
      title="Factor Workbench"
      subtitle="Author and preview factor expressions; ICs are computed against forward returns."
      extra={
        <Space>
          <Button onClick={() => setDrawer("indicators")}>Indicators…</Button>
          <Button icon={<ExportOutlined />} onClick={() => setDrawer("flink")}>
            Export to Flink
          </Button>
          <Button type="primary" onClick={evaluate}>
            Evaluate
          </Button>
        </Space>
      }
    >
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select
            mode="multiple"
            placeholder="Symbols"
            value={symbols}
            onChange={setSymbols}
            options={universeOptions.length ? universeOptions : symbols.map((s) => ({ value: s, label: s }))}
            style={{ minWidth: 320 }}
            maxTagCount={5}
          />
          <Input
            placeholder="start (YYYY-MM-DD)"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            style={{ width: 160 }}
          />
          <Input
            placeholder="end (optional)"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            style={{ width: 160 }}
          />
        </Space>
      </Card>
      <Row gutter={16}>
        <Col xs={24} lg={16}>
          <Card title="Formula" size="small">
            <div style={{ height: 320 }}>
              <MonacoEditor
                height="100%"
                defaultLanguage="python"
                value={formula}
                onChange={(v) => setFormula(v ?? "")}
                theme="vs-dark"
                options={{ fontSize: 13, minimap: { enabled: false } }}
              />
            </div>
          </Card>
          <Card title="Preview" size="small" style={{ marginTop: 16 }}>
            {preview ? (
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                <Space>
                  <Tag color="blue">IC: {meanIc(preview.summary)?.toFixed(3) ?? "—"}</Tag>
                  <Tag color="purple">IR: {maxIr(preview.summary)?.toFixed(3) ?? "—"}</Tag>
                  <Tag>n_rows: {preview.n_rows ?? "—"}</Tag>
                  <Tag>n_symbols: {preview.n_symbols ?? "—"}</Tag>
                </Space>
                <DataGrid<FactorPreviewRow>
                  rowData={preview.rows ?? []}
                  columnDefs={[
                    { field: "vt_symbol", headerName: "Symbol", flex: 1 },
                    { field: "timestamp", headerName: "ts", width: 170 },
                    {
                      field: "factor",
                      headerName: "factor",
                      valueFormatter: NumberCellFormatter,
                      width: 130,
                    },
                    {
                      field: "close",
                      headerName: "close",
                      valueFormatter: NumberCellFormatter,
                      width: 110,
                    },
                  ]}
                  height={300}
                />
                {preview.message ? (
                  <Text type="warning" style={{ fontSize: 12 }}>
                    {preview.message}
                  </Text>
                ) : null}
              </Space>
            ) : (
              <Text type="secondary">Evaluate a formula to populate this section.</Text>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="Operators" size="small" extra={<Input.Search placeholder="filter" />}>
            <Space direction="vertical" size={4} style={{ width: "100%", maxHeight: 540, overflowY: "auto" }}>
              {(operators.data ?? []).map((op) => (
                <Card key={op.name} size="small" hoverable styles={{ body: { padding: "6px 10px" } }}>
                  <Text strong>{op.name}</Text>
                  {op.signature ? (
                    <Text style={{ fontFamily: "monospace", fontSize: 11, marginLeft: 6, opacity: 0.7 }}>
                      {op.signature}
                    </Text>
                  ) : null}
                  {op.description ? (
                    <div style={{ fontSize: 11, opacity: 0.7 }}>{op.description}</div>
                  ) : null}
                </Card>
              ))}
              {(operators.data ?? []).length === 0 ? <Text type="secondary">—</Text> : null}
            </Space>
          </Card>
        </Col>
      </Row>
      <Drawer
        open={drawer === "indicators"}
        title="Insert TA-Lib indicator"
        width={420}
        onClose={() => setDrawer(null)}
      >
        <List
          dataSource={(catalog.data?.groups ?? []).flatMap((g) => g.indicators)}
          pagination={{ pageSize: 25 }}
          renderItem={(ind) => (
            <List.Item
              actions={[
                <Button key="add" size="small" onClick={() => insertIndicator(ind)}>
                  Insert
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Space>
                    <Text strong>{ind.name}</Text>
                    <Tag>{ind.group}</Tag>
                  </Space>
                }
                description={ind.description}
              />
            </List.Item>
          )}
        />
      </Drawer>
      <Modal
        open={drawer === "flink"}
        title="Export factor to Flink job"
        onCancel={() => setDrawer(null)}
        onOk={exportToFlink}
        okText="Submit"
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Text type="secondary">
            Compiles the current formula into a Kafka Streams / Flink job that publishes factor values
            to <code>factors.preview.v1</code>.
          </Text>
          <Input
            placeholder="job name (e.g. mean_reversion_v1)"
            value={flinkJob}
            onChange={(e) => setFlinkJob(e.target.value)}
          />
          <Text style={{ fontFamily: "monospace", fontSize: 11 }}>
            symbols: {symbols.join(", ")}
          </Text>
        </Space>
      </Modal>
    </PageContainer>
  );
}
