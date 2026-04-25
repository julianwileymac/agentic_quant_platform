"use client";

import { ReloadOutlined } from "@ant-design/icons";
import { Button, Card, Col, Row, Space, Tag, Typography } from "antd";

import { DataGrid, NumberCellFormatter, PercentCellFormatter, StatusBadgeCell } from "@/components/data-grid";
import { Heatmap, type HeatmapCell } from "@/components/charts";
import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";

const { Text } = Typography;

interface OptimizationSummary {
  id: string;
  status: string;
  run_name: string;
  method: string;
  metric: string;
  n_trials: number;
  n_completed: number;
  best_metric_value?: number | null;
  strategy_id?: string | null;
  created_at: string;
  completed_at?: string | null;
}

interface OptimizationTrial {
  id: string;
  trial_index: number;
  status: string;
  parameters?: Record<string, number | string>;
  metric_value?: number | null;
  sharpe?: number | null;
  total_return?: number | null;
  max_drawdown?: number | null;
}

function buildHeatmap(trials: OptimizationTrial[]): {
  rows: string[];
  cols: string[];
  cells: HeatmapCell[];
} {
  if (trials.length === 0) return { rows: [], cols: [], cells: [] };
  const sample = trials.find((t) => t.parameters && Object.keys(t.parameters).length >= 2);
  if (!sample || !sample.parameters) return { rows: [], cols: [], cells: [] };
  const [p1, p2] = Object.keys(sample.parameters);
  if (!p1 || !p2) return { rows: [], cols: [], cells: [] };
  const rows = Array.from(new Set(trials.map((t) => String(t.parameters?.[p1])))).sort();
  const cols = Array.from(new Set(trials.map((t) => String(t.parameters?.[p2])))).sort();
  const cells = trials
    .filter((t) => t.metric_value != null && t.parameters?.[p1] != null && t.parameters?.[p2] != null)
    .map((t) => ({
      row: String(t.parameters?.[p1]),
      col: String(t.parameters?.[p2]),
      value: Number(t.metric_value),
    }));
  return { rows, cols, cells };
}

export function OptimizerPage() {
  const list = useApiQuery<OptimizationSummary[]>({
    queryKey: ["optimize", "list"],
    path: "/backtest/optimize/runs",
    select: (raw) => (Array.isArray(raw) ? (raw as OptimizationSummary[]) : []),
  });
  const latest = list.data?.[0];
  const trials = useApiQuery<OptimizationTrial[]>({
    queryKey: ["optimize", "trials", latest?.id ?? ""],
    path: latest ? `/backtest/optimize/runs/${latest.id}/trials` : "/",
    enabled: Boolean(latest),
    select: (raw) => (Array.isArray(raw) ? (raw as OptimizationTrial[]) : []),
  });

  const heatmap = trials.data ? buildHeatmap(trials.data) : { rows: [], cols: [], cells: [] };

  return (
    <PageContainer
      title="Optimizer"
      subtitle="Parameter sweeps, grid + random search, with a 2-D performance heatmap."
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => list.refetch()}>
            Refresh
          </Button>
        </Space>
      }
    >
      <Row gutter={16}>
        <Col xs={24} lg={14}>
          <Card title="Optimization runs" size="small">
            <DataGrid<OptimizationSummary>
              rowData={list.data ?? []}
              loading={list.isLoading}
              columnDefs={[
                { field: "run_name", headerName: "Name", flex: 2, minWidth: 200 },
                { field: "method", headerName: "Method", width: 110 },
                { field: "metric", headerName: "Metric", width: 110 },
                { field: "status", headerName: "Status", cellRenderer: StatusBadgeCell, width: 130 },
                { field: "n_completed", headerName: "Done", width: 90, valueFormatter: NumberCellFormatter },
                { field: "n_trials", headerName: "Trials", width: 90, valueFormatter: NumberCellFormatter },
                {
                  field: "best_metric_value",
                  headerName: "Best",
                  width: 120,
                  valueFormatter: NumberCellFormatter,
                },
              ]}
              height={420}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title={latest ? `Heatmap — ${latest.run_name}` : "Heatmap"} size="small">
            {heatmap.cells.length === 0 ? (
              <Text type="secondary">Need a 2-D parameter sweep with finished trials.</Text>
            ) : (
              <Heatmap rows={heatmap.rows} cols={heatmap.cols} cells={heatmap.cells} cellSize={32} />
            )}
            {latest ? (
              <div style={{ marginTop: 12 }}>
                <Tag>{latest.metric}</Tag>
                <Tag color="blue">best {latest.best_metric_value ?? "—"}</Tag>
              </div>
            ) : null}
          </Card>
        </Col>
      </Row>
      <Card title="Trials" size="small" style={{ marginTop: 16 }}>
        <DataGrid<OptimizationTrial>
          rowData={trials.data ?? []}
          loading={trials.isLoading}
          columnDefs={[
            { field: "trial_index", headerName: "#", width: 80 },
            { field: "status", headerName: "Status", cellRenderer: StatusBadgeCell, width: 110 },
            { field: "metric_value", headerName: "Metric", valueFormatter: NumberCellFormatter, width: 110 },
            { field: "sharpe", headerName: "Sharpe", valueFormatter: NumberCellFormatter, width: 110 },
            {
              field: "total_return",
              headerName: "Return",
              valueFormatter: PercentCellFormatter,
              width: 110,
            },
            {
              field: "max_drawdown",
              headerName: "Max DD",
              valueFormatter: PercentCellFormatter,
              width: 110,
            },
            {
              headerName: "Parameters",
              flex: 2,
              minWidth: 200,
              valueGetter: ({ data }) =>
                data?.parameters
                  ? Object.entries(data.parameters)
                      .map(([k, v]) => `${k}=${v}`)
                      .join(", ")
                  : "",
            },
          ]}
          height={360}
        />
      </Card>
    </PageContainer>
  );
}
