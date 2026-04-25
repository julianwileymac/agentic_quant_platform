"use client";

import { App, Button, Card, Col, Input, Row, Space, Tag, Typography } from "antd";
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
}

interface FactorPreviewRow {
  vt_symbol: string;
  factor_value?: number | null;
  rank?: number | null;
  z_score?: number | null;
}

interface FactorPreview {
  rows?: FactorPreviewRow[];
  ic?: number | null;
  ir?: number | null;
}

const DEFAULT_FORMULA = `# A factor expression in the AQP DSL.
# Rank-normalize the negative 1-month return; classic mean-reversion alpha.
rank(neg(returns(close, 21)))`;

export function FactorWorkbench() {
  const { message } = App.useApp();
  const [formula, setFormula] = useState(DEFAULT_FORMULA);
  const [preview, setPreview] = useState<FactorPreview | null>(null);

  const operators = useApiQuery<FactorOperator[]>({
    queryKey: ["factors", "operators"],
    path: "/factors/operators",
    select: (raw) => (Array.isArray(raw) ? (raw as FactorOperator[]) : []),
  });

  async function evaluate() {
    try {
      const res = await apiFetch<FactorPreview>("/factors/preview", {
        method: "POST",
        body: JSON.stringify({ formula }),
      });
      setPreview(res);
      message.success(`Returned ${res.rows?.length ?? 0} rows`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title="Factor Workbench"
      subtitle="Author and preview factor expressions; ICs are computed against forward returns."
      extra={
        <Button type="primary" onClick={evaluate}>
          Evaluate
        </Button>
      }
    >
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
                  <Tag color="blue">IC: {preview.ic?.toFixed?.(3) ?? "—"}</Tag>
                  <Tag color="purple">IR: {preview.ir?.toFixed?.(3) ?? "—"}</Tag>
                </Space>
                <DataGrid<FactorPreviewRow>
                  rowData={preview.rows ?? []}
                  columnDefs={[
                    { field: "vt_symbol", headerName: "Symbol", flex: 1 },
                    {
                      field: "factor_value",
                      headerName: "Value",
                      valueFormatter: NumberCellFormatter,
                      width: 130,
                    },
                    { field: "rank", headerName: "Rank", valueFormatter: NumberCellFormatter, width: 110 },
                    { field: "z_score", headerName: "Z", valueFormatter: NumberCellFormatter, width: 110 },
                  ]}
                  height={300}
                />
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
    </PageContainer>
  );
}
