"use client";

import { ReloadOutlined, WarningOutlined } from "@ant-design/icons";
import {
  App,
  Button,
  Card,
  Col,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { useState } from "react";
import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RTooltip,
} from "recharts";

import { EquityChart } from "@/components/charts";
import {
  DataGrid,
  fillColumns,
  ledgerColumns,
  orderColumns,
  positionColumns,
} from "@/components/data-grid";
import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import type { FillRow, LedgerEntryRow, OrderRow, PositionRow } from "@/lib/api/domains";

const PIE_PALETTE = [
  "#3b82f6",
  "#22c55e",
  "#f59e0b",
  "#a855f7",
  "#ef4444",
  "#06b6d4",
  "#84cc16",
  "#ec4899",
  "#0ea5e9",
  "#f97316",
];

const { Text } = Typography;

interface PositionResp {
  positions: PositionRow[];
  n_symbols: number;
}

interface PnlSeries {
  index: string[];
  equity: number[];
  daily_pnl: number[];
}

interface AllocationsResp {
  by: string;
  buckets: Array<{ name: string; value: number; weight: number }>;
}

interface ExposuresResp {
  long_exposure: number;
  short_exposure: number;
  gross_exposure: number;
  net_exposure: number;
  n_long: number;
  n_short: number;
}

interface RiskResp {
  sharpe?: number | null;
  max_drawdown?: number | null;
  var_95?: number | null;
  cvar_95?: number | null;
  ann_vol?: number | null;
  ann_return?: number | null;
  beta?: number | null;
}

interface KillSwitchState {
  active: boolean;
  reason?: string | null;
  set_at?: string | null;
}

export function PortfolioPage() {
  const { message, modal } = App.useApp();
  const [refreshTick, setRefreshTick] = useState(0);

  const orders = useApiQuery<OrderRow[]>({
    queryKey: ["portfolio", "orders", refreshTick],
    path: "/portfolio/orders",
    select: (raw) => (Array.isArray(raw) ? (raw as OrderRow[]) : []),
  });
  const fills = useApiQuery<FillRow[]>({
    queryKey: ["portfolio", "fills", refreshTick],
    path: "/portfolio/fills",
    select: (raw) => (Array.isArray(raw) ? (raw as FillRow[]) : []),
  });
  const ledger = useApiQuery<LedgerEntryRow[]>({
    queryKey: ["portfolio", "ledger", refreshTick],
    path: "/portfolio/ledger",
    select: (raw) => (Array.isArray(raw) ? (raw as LedgerEntryRow[]) : []),
  });
  const positionsResp = useApiQuery<PositionResp>({
    queryKey: ["portfolio", "positions", refreshTick],
    path: "/portfolio/positions",
  });
  const positions = (positionsResp.data?.positions ?? []) as PositionRow[];
  const pnlSeries = useApiQuery<PnlSeries>({
    queryKey: ["portfolio", "pnl", refreshTick],
    path: "/portfolio/pnl",
  });
  const [allocationBy, setAllocationBy] = useState<string>("sector");
  const allocations = useApiQuery<AllocationsResp>({
    queryKey: ["portfolio", "allocations", allocationBy, refreshTick],
    path: "/portfolio/allocations",
    query: { by: allocationBy },
  });
  const exposures = useApiQuery<ExposuresResp>({
    queryKey: ["portfolio", "exposures", refreshTick],
    path: "/portfolio/exposures",
  });
  const risk = useApiQuery<RiskResp>({
    queryKey: ["portfolio", "risk", refreshTick],
    path: "/portfolio/risk",
  });
  const kill = useApiQuery<KillSwitchState>({
    queryKey: ["portfolio", "kill", refreshTick],
    path: "/portfolio/kill_switch",
    refetchInterval: 5000,
  });

  async function setKillSwitch(active: boolean) {
    if (active) {
      const proceed = await new Promise<boolean>((resolve) => {
        modal.confirm({
          title: "Engage kill switch?",
          icon: <WarningOutlined style={{ color: "#ef4444" }} />,
          content: "All trading halts immediately and any open orders are cancelled.",
          onOk: () => resolve(true),
          onCancel: () => resolve(false),
        });
      });
      if (!proceed) return;
    }
    try {
      await apiFetch("/portfolio/kill_switch", {
        method: "POST",
        body: JSON.stringify({ active, reason: active ? "manual via webui" : "" }),
      });
      message.success(`Kill switch ${active ? "engaged" : "released"}`);
      setRefreshTick((t) => t + 1);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  const totalEquity = positions.reduce(
    (acc, p) => acc + (Number(p.market_value) || 0),
    0,
  );
  const totalPnl = positions.reduce(
    (acc, p) => acc + (Number(p.unrealized_pnl) || 0),
    0,
  );

  const equityCurve = (pnlSeries.data?.index ?? []).map((ts, i) => ({
    timestamp: ts,
    value: Number(pnlSeries.data?.equity?.[i] ?? 0),
  }));

  return (
    <PageContainer
      title={
        <Space>
          Portfolio
          {kill.data?.active ? (
            <Tag color="red" icon={<WarningOutlined />}>
              Kill switch engaged
            </Tag>
          ) : null}
        </Space>
      }
      subtitle="Orders, fills, positions, ledger, and the master kill switch."
      extra={
        <Space>
          <Switch
            checkedChildren="Killed"
            unCheckedChildren="Live"
            checked={Boolean(kill.data?.active)}
            onChange={(v) => setKillSwitch(v)}
          />
          <Button icon={<ReloadOutlined />} onClick={() => setRefreshTick((t) => t + 1)}>
            Refresh
          </Button>
        </Space>
      }
    >
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="Positions" value={positions.length} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="Open orders" value={orders.data?.filter((o) => (o.status ?? "").toLowerCase() === "open").length ?? 0} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="Market value" value={totalEquity} precision={2} prefix="$" />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="Unrealized PnL"
              value={totalPnl}
              precision={2}
              prefix="$"
              valueStyle={{ color: totalPnl >= 0 ? "#10b981" : "#ef4444" }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={24} md={6}>
          <Card>
            <Statistic
              title="Sharpe"
              value={risk.data?.sharpe ?? 0}
              precision={2}
              valueStyle={{
                color: (risk.data?.sharpe ?? 0) >= 0 ? "#10b981" : "#ef4444",
              }}
            />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic
              title="Max drawdown"
              value={(risk.data?.max_drawdown ?? 0) * 100}
              precision={2}
              suffix="%"
              valueStyle={{ color: "#ef4444" }}
            />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic
              title="Ann. volatility"
              value={(risk.data?.ann_vol ?? 0) * 100}
              precision={2}
              suffix="%"
            />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic
              title="VaR 95%"
              value={(risk.data?.var_95 ?? 0) * 100}
              precision={2}
              suffix="%"
              valueStyle={{ color: "#ef4444" }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={16}>
          <Card title="Live equity curve" size="small">
            {equityCurve.length ? (
              <EquityChart data={equityCurve} height={280} />
            ) : (
              <Text type="secondary">No fills yet — run a backtest or paper-trade to populate the equity curve.</Text>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card
            size="small"
            title="Allocation"
            extra={
              <Select
                size="small"
                value={allocationBy}
                style={{ width: 130 }}
                onChange={setAllocationBy}
                options={[
                  { value: "sector", label: "Sector" },
                  { value: "industry", label: "Industry" },
                  { value: "asset_class", label: "Asset class" },
                  { value: "country", label: "Country" },
                  { value: "currency", label: "Currency" },
                ]}
              />
            }
          >
            {allocations.data?.buckets?.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={allocations.data.buckets}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={50}
                    outerRadius={90}
                    label={(entry) =>
                      `${entry.name}: ${(Number(entry.weight ?? 0) * 100).toFixed(0)}%`
                    }
                  >
                    {allocations.data.buckets.map((_, idx) => (
                      <Cell
                        key={`cell-${idx}`}
                        fill={PIE_PALETTE[idx % PIE_PALETTE.length]}
                      />
                    ))}
                  </Pie>
                  <RTooltip
                    formatter={(value: number, _name, props) => [
                      Number(value).toLocaleString(undefined, {
                        maximumFractionDigits: 2,
                      }),
                      String(props.payload?.name ?? ""),
                    ]}
                  />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <Text type="secondary">No allocation data.</Text>
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={24} md={6}>
          <Card>
            <Statistic
              title="Long exposure"
              value={exposures.data?.long_exposure ?? 0}
              precision={2}
              prefix="$"
            />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic
              title="Short exposure"
              value={exposures.data?.short_exposure ?? 0}
              precision={2}
              prefix="$"
            />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic
              title="Gross exposure"
              value={exposures.data?.gross_exposure ?? 0}
              precision={2}
              prefix="$"
            />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic
              title="Net exposure"
              value={exposures.data?.net_exposure ?? 0}
              precision={2}
              prefix="$"
            />
          </Card>
        </Col>
      </Row>
      <Tabs
        items={[
          {
            key: "positions",
            label: "Positions",
            children: (
              <DataGrid<PositionRow>
                rowData={positions}
                loading={positionsResp.isLoading}
                columnDefs={positionColumns}
                height={420}
              />
            ),
          },
          {
            key: "orders",
            label: "Orders",
            children: (
              <DataGrid<OrderRow>
                rowData={orders.data ?? []}
                loading={orders.isLoading}
                columnDefs={orderColumns}
                height={420}
              />
            ),
          },
          {
            key: "fills",
            label: "Fills",
            children: (
              <DataGrid<FillRow>
                rowData={fills.data ?? []}
                loading={fills.isLoading}
                columnDefs={fillColumns}
                height={420}
              />
            ),
          },
          {
            key: "ledger",
            label: "Ledger",
            children: (
              <DataGrid<LedgerEntryRow>
                rowData={ledger.data ?? []}
                loading={ledger.isLoading}
                columnDefs={ledgerColumns}
                height={420}
              />
            ),
          },
        ]}
      />
      {kill.data?.active && kill.data?.reason ? (
        <Card size="small" style={{ marginTop: 16 }}>
          <Text type="danger">Kill switch reason:</Text> <Text>{kill.data.reason}</Text>
        </Card>
      ) : null}
    </PageContainer>
  );
}
