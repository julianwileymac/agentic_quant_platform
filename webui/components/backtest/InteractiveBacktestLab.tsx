"use client";

import { PlayCircleOutlined, ReloadOutlined, RocketOutlined } from "@ant-design/icons";
import {
  App,
  Button,
  Card,
  Col,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";

import { STRATEGY_PALETTE } from "@/components/flow/palettes";
import { serializeStrategy } from "@/components/flow/serializers";
import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import type { FlowGraph } from "@/components/flow/types";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { useChatStream } from "@/lib/ws";

const { Paragraph, Text } = Typography;

const ACCENTS: Record<string, string> = {
  Signal: "#10b981",
  Factor: "#a855f7",
  Rule: "#3b82f6",
  Sizing: "#3b82f6",
  Risk: "#ef4444",
  Portfolio: "#f59e0b",
  Execution: "#f59e0b",
};

interface TaskAccepted {
  task_id: string;
  stream_url?: string;
}

interface BacktestSummary {
  id: string;
  status: string;
  sharpe?: number | null;
  sortino?: number | null;
  max_drawdown?: number | null;
  total_return?: number | null;
  final_equity?: number | null;
  created_at: string;
}

interface ScenarioPreset {
  label: string;
  description: string;
  graph: FlowGraph;
  symbols: string[];
  start: string;
  end: string;
  cash: number;
  lookbackRange: [number, number, number];
  topQuantileRange: [number, number, number];
}

const SCENARIOS: Record<string, ScenarioPreset> = {
  momentum: {
    label: "Momentum baseline",
    description: "Trend-following starter with momentum signal and equal-weight sizing.",
    symbols: ["SPY", "AAPL", "MSFT", "NVDA"],
    start: "2021-01-01",
    end: "2024-12-31",
    cash: 100000,
    lookbackRange: [30, 180, 30],
    topQuantileRange: [0.2, 0.5, 0.1],
    graph: {
      domain: "strategy",
      version: 1,
      nodes: [
        {
          id: "sig-momentum",
          type: "aqp",
          position: { x: 80, y: 80 },
          data: {
            kind: "Signal",
            label: "Momentum",
            params: { kind: "momentum", lookback: 90 },
          },
        },
        {
          id: "size-ew",
          type: "aqp",
          position: { x: 360, y: 80 },
          data: { kind: "Sizing", label: "Equal weight", params: { kind: "equal_weight" } },
        },
        {
          id: "risk-dd",
          type: "aqp",
          position: { x: 620, y: 80 },
          data: { kind: "Risk", label: "Max DD halt", params: { max_dd: 0.2 } },
        },
        {
          id: "portfolio",
          type: "aqp",
          position: { x: 880, y: 80 },
          data: { kind: "Portfolio", label: "Portfolio assembler", params: {} },
        },
      ],
      edges: [
        { id: "e1", source: "sig-momentum", target: "size-ew" },
        { id: "e2", source: "size-ew", target: "risk-dd" },
        { id: "e3", source: "risk-dd", target: "portfolio" },
      ],
    },
  },
  mean_reversion: {
    label: "Mean reversion",
    description: "Short-horizon reversal setup with risk-parity sizing and tighter drawdown controls.",
    symbols: ["SPY", "QQQ", "IWM", "DIA"],
    start: "2022-01-01",
    end: "2024-12-31",
    cash: 125000,
    lookbackRange: [10, 60, 10],
    topQuantileRange: [0.1, 0.3, 0.05],
    graph: {
      domain: "strategy",
      version: 1,
      nodes: [
        {
          id: "sig-meanrev",
          type: "aqp",
          position: { x: 80, y: 80 },
          data: {
            kind: "Signal",
            label: "Mean reversion",
            params: { kind: "mean_reversion", window: 20, z_threshold: 2.0 },
          },
        },
        {
          id: "size-rp",
          type: "aqp",
          position: { x: 360, y: 80 },
          data: { kind: "Sizing", label: "Risk parity", params: { kind: "risk_parity" } },
        },
        {
          id: "risk-stop",
          type: "aqp",
          position: { x: 620, y: 80 },
          data: { kind: "Risk", label: "Stop loss", params: { stop_pct: 0.04 } },
        },
        {
          id: "portfolio",
          type: "aqp",
          position: { x: 880, y: 80 },
          data: { kind: "Portfolio", label: "Portfolio assembler", params: {} },
        },
      ],
      edges: [
        { id: "e1", source: "sig-meanrev", target: "size-rp" },
        { id: "e2", source: "size-rp", target: "risk-stop" },
        { id: "e3", source: "risk-stop", target: "portfolio" },
      ],
    },
  },
  regime_mix: {
    label: "Market regime mix",
    description: "Blend momentum + mean reversion with a rule gate for regime-style experiments.",
    symbols: ["SPY", "AAPL", "MSFT", "NVDA", "XLE", "XLF"],
    start: "2020-01-01",
    end: "2024-12-31",
    cash: 150000,
    lookbackRange: [30, 240, 30],
    topQuantileRange: [0.2, 0.6, 0.1],
    graph: {
      domain: "strategy",
      version: 1,
      nodes: [
        {
          id: "sig-momentum",
          type: "aqp",
          position: { x: 80, y: 40 },
          data: {
            kind: "Signal",
            label: "Momentum",
            params: { kind: "momentum", lookback: 120 },
          },
        },
        {
          id: "sig-meanrev",
          type: "aqp",
          position: { x: 80, y: 160 },
          data: {
            kind: "Signal",
            label: "Mean reversion",
            params: { kind: "mean_reversion", window: 20, z_threshold: 1.8 },
          },
        },
        {
          id: "rule",
          type: "aqp",
          position: { x: 360, y: 100 },
          data: { kind: "Rule", label: "Long/Short", params: { kind: "long_short" } },
        },
        {
          id: "size",
          type: "aqp",
          position: { x: 620, y: 100 },
          data: { kind: "Sizing", label: "Equal weight", params: { kind: "equal_weight" } },
        },
        {
          id: "portfolio",
          type: "aqp",
          position: { x: 880, y: 100 },
          data: { kind: "Portfolio", label: "Portfolio assembler", params: {} },
        },
      ],
      edges: [
        { id: "e1", source: "sig-momentum", target: "rule" },
        { id: "e2", source: "sig-meanrev", target: "rule" },
        { id: "e3", source: "rule", target: "size" },
        { id: "e4", source: "size", target: "portfolio" },
      ],
    },
  },
};

const DEFAULT_SCENARIO_KEY = "momentum";
const DEFAULT_SCENARIO: ScenarioPreset =
  SCENARIOS[DEFAULT_SCENARIO_KEY] ?? Object.values(SCENARIOS)[0]!;

function parseSymbols(raw: string): string[] {
  return Array.from(
    new Set(
      String(raw || "")
        .split(/[,\s]+/)
        .map((item) => item.trim().toUpperCase())
        .filter(Boolean),
    ),
  );
}

function asNumber(value: unknown, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function graphToBacktestConfig(
  graph: FlowGraph,
  opts: {
    symbols: string[];
    start: string;
    end: string;
    initialCash: number;
    engine: string;
  },
): Record<string, unknown> {
  const signalParams = graph.nodes
    .filter((node) => node.data.kind === "Signal")
    .map((node) => node.data.params ?? {});
  const firstSignal = signalParams[0] ?? {};
  const lookback = asNumber(firstSignal.lookback ?? firstSignal.fast ?? firstSignal.window, 90);
  const topQuantile = asNumber(firstSignal.top_quantile, 0.3);
  const riskNode = graph.nodes.find((node) => node.data.kind === "Risk")?.data.params ?? {};
  const maxDrawdownPct = asNumber(riskNode.max_dd ?? riskNode.max_drawdown_pct, 0.2);
  const maxPositions = Math.max(1, Math.min(opts.symbols.length, 10));

  return {
    strategy: {
      class: "FrameworkAlgorithm",
      module_path: "aqp.strategies.framework",
      kwargs: {
        universe_model: {
          class: "StaticUniverse",
          module_path: "aqp.strategies.universes",
          kwargs: { symbols: opts.symbols },
        },
        alpha_model: {
          class: "MomentumAlpha",
          module_path: "aqp.strategies.momentum",
          kwargs: {
            lookback,
            top_quantile: topQuantile,
            bottom_quantile: topQuantile,
            allow_short: true,
          },
        },
        portfolio_model: {
          class: "EqualWeightPortfolio",
          module_path: "aqp.strategies.portfolio",
          kwargs: { max_positions: maxPositions },
        },
        risk_model: {
          class: "BasicRiskModel",
          module_path: "aqp.strategies.risk_models",
          kwargs: {
            max_position_pct: 1 / maxPositions,
            max_drawdown_pct: maxDrawdownPct,
          },
        },
        execution_model: {
          class: "MarketOrderExecution",
          module_path: "aqp.strategies.execution",
          kwargs: {},
        },
      },
    },
    backtest: {
      engine: opts.engine,
      kwargs: {
        initial_cash: opts.initialCash,
        commission_pct: 0.0005,
        slippage_bps: 2,
        start: opts.start,
        end: opts.end,
      },
    },
  };
}

function StreamCard({
  title,
  taskId,
  status,
  done,
  events,
}: {
  title: string;
  taskId: string | null;
  status: string;
  done: boolean;
  events: unknown[];
}) {
  return (
    <Card title={title} size="small">
      {!taskId ? (
        <Text type="secondary">No task queued yet.</Text>
      ) : (
        <Space direction="vertical" style={{ width: "100%" }}>
          <Tag color={status === "open" ? "blue" : done ? "green" : "default"}>
            {status} {done ? "(done)" : ""}
          </Tag>
          <Paragraph copyable={{ text: taskId }}>Task: {taskId}</Paragraph>
          <pre
            style={{
              fontSize: 11,
              maxHeight: 220,
              overflow: "auto",
              background: "var(--ant-color-bg-elevated)",
              padding: 8,
              borderRadius: 6,
            }}
          >
            {events.map((event, idx) => `[${idx}] ${JSON.stringify(event)}`).join("\n") || "Waiting for events…"}
          </pre>
        </Space>
      )}
    </Card>
  );
}

export function InteractiveBacktestLab() {
  const { message } = App.useApp();
  const [scenario, setScenario] = useState<string>(DEFAULT_SCENARIO_KEY);
  const [editorSeed, setEditorSeed] = useState(0);
  const preset = SCENARIOS[scenario] ?? DEFAULT_SCENARIO;

  const [runName, setRunName] = useState(`interactive-${scenario}`);
  const [symbolsRaw, setSymbolsRaw] = useState(preset.symbols.join(", "));
  const [start, setStart] = useState(preset.start);
  const [end, setEnd] = useState(preset.end);
  const [initialCash, setInitialCash] = useState<number>(preset.cash);
  const [engine, setEngine] = useState("event");
  const [runTaskId, setRunTaskId] = useState<string | null>(null);
  const [optTaskId, setOptTaskId] = useState<string | null>(null);
  const [latestConfig, setLatestConfig] = useState<Record<string, unknown> | null>(null);
  const [latestStrategyYaml, setLatestStrategyYaml] = useState<string>("");

  const [sweepMethod, setSweepMethod] = useState<"grid" | "random">("grid");
  const [sweepMetric, setSweepMetric] = useState("sharpe");
  const [lookbackLow, setLookbackLow] = useState<number>(preset.lookbackRange[0]);
  const [lookbackHigh, setLookbackHigh] = useState<number>(preset.lookbackRange[1]);
  const [lookbackStep, setLookbackStep] = useState<number>(preset.lookbackRange[2]);
  const [topQLow, setTopQLow] = useState<number>(preset.topQuantileRange[0]);
  const [topQHigh, setTopQHigh] = useState<number>(preset.topQuantileRange[1]);
  const [topQStep, setTopQStep] = useState<number>(preset.topQuantileRange[2]);
  const [maxTrials, setMaxTrials] = useState<number>(200);
  const [nRandom, setNRandom] = useState<number>(32);

  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareRows, setCompareRows] = useState<BacktestSummary[]>([]);
  const [compareLoading, setCompareLoading] = useState(false);

  const runs = useApiQuery<BacktestSummary[]>({
    queryKey: ["backtest", "runs", "interactive-lab"],
    path: "/backtest/runs",
    select: (raw) => (Array.isArray(raw) ? (raw as BacktestSummary[]) : []),
  });

  const runStream = useChatStream(runTaskId);
  const optStream = useChatStream(optTaskId);

  useEffect(() => {
    if (!runStream.done) return;
    runs.refetch();
  }, [runStream.done, runs]);

  function applyScenario(nextScenario: string) {
    const next = SCENARIOS[nextScenario] ?? DEFAULT_SCENARIO;
    setScenario(nextScenario);
    setRunName(`interactive-${nextScenario}`);
    setSymbolsRaw(next.symbols.join(", "));
    setStart(next.start);
    setEnd(next.end);
    setInitialCash(next.cash);
    setLookbackLow(next.lookbackRange[0]);
    setLookbackHigh(next.lookbackRange[1]);
    setLookbackStep(next.lookbackRange[2]);
    setTopQLow(next.topQuantileRange[0]);
    setTopQHigh(next.topQuantileRange[1]);
    setTopQStep(next.topQuantileRange[2]);
    setLatestConfig(null);
    setLatestStrategyYaml("");
    setEditorSeed((prev) => prev + 1);
  }

  async function runGraph(graph: FlowGraph) {
    const symbols = parseSymbols(symbolsRaw);
    if (symbols.length === 0) {
      message.warning("Provide at least one symbol before running.");
      return;
    }
    const config = graphToBacktestConfig(graph, {
      symbols,
      start,
      end,
      initialCash: Number(initialCash || 0),
      engine,
    });
    const strategyYaml = serializeStrategy(graph, runName || `interactive-${scenario}`).config_yaml;
    setLatestStrategyYaml(strategyYaml);
    setLatestConfig(config);
    const response = await apiFetch<TaskAccepted>("/backtest/run", {
      method: "POST",
      body: JSON.stringify({
        config,
        run_name: runName || `interactive-${scenario}`,
      }),
    });
    setRunTaskId(response.task_id);
    message.success(`Backtest queued: ${response.task_id}`);
  }

  async function launchSweep() {
    if (!latestConfig) {
      message.warning("Run the graph once to materialize a base config for sweeps.");
      return;
    }
    const payload = {
      config: latestConfig,
      method: sweepMethod,
      metric: sweepMetric,
      n_random: nRandom,
      max_trials: maxTrials,
      run_name: `${runName || `interactive-${scenario}`}-sweep`,
      parameters: [
        {
          path: "strategy.kwargs.alpha_model.kwargs.lookback",
          low: lookbackLow,
          high: lookbackHigh,
          step: lookbackStep,
        },
        {
          path: "strategy.kwargs.alpha_model.kwargs.top_quantile",
          low: topQLow,
          high: topQHigh,
          step: topQStep,
        },
      ],
    };
    const response = await apiFetch<TaskAccepted>("/backtest/optimize", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setOptTaskId(response.task_id);
    message.success(`Optimization queued: ${response.task_id}`);
  }

  async function loadComparisonBoard() {
    if (compareIds.length === 0) {
      setCompareRows([]);
      return;
    }
    try {
      setCompareLoading(true);
      const rows = await Promise.all(
        compareIds.map((id) => apiFetch<BacktestSummary>(`/backtest/runs/${encodeURIComponent(id)}`)),
      );
      setCompareRows(rows);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setCompareLoading(false);
    }
  }

  const scenarioOptions = useMemo(
    () =>
      Object.entries(SCENARIOS).map(([value, item]) => ({
        value,
        label: item.label,
      })),
    [],
  );

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Card
        size="small"
        title="Interactive backtest lab"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => runs.refetch()}>
              Refresh runs
            </Button>
            <Button type="primary" icon={<RocketOutlined />} onClick={launchSweep}>
              Launch sweep
            </Button>
          </Space>
        }
      >
        <Paragraph type="secondary">
          Compose strategies with drag/drop blocks, run backtests from the graph, launch parameter sweeps, and compare multiple runs side-by-side.
        </Paragraph>
        <Space wrap align="start">
          <Space direction="vertical" size={2}>
            <Text type="secondary">Scenario preset</Text>
            <Select
              value={scenario}
              onChange={applyScenario}
              style={{ minWidth: 220 }}
              options={scenarioOptions}
            />
          </Space>
          <Space direction="vertical" size={2}>
            <Text type="secondary">Run name</Text>
            <Input value={runName} onChange={(event) => setRunName(event.target.value)} style={{ width: 220 }} />
          </Space>
          <Space direction="vertical" size={2}>
            <Text type="secondary">Symbols</Text>
            <Input
              value={symbolsRaw}
              onChange={(event) => setSymbolsRaw(event.target.value)}
              style={{ width: 260 }}
              placeholder="SPY, AAPL, MSFT"
            />
          </Space>
          <Space direction="vertical" size={2}>
            <Text type="secondary">Start</Text>
            <Input value={start} onChange={(event) => setStart(event.target.value)} style={{ width: 140 }} />
          </Space>
          <Space direction="vertical" size={2}>
            <Text type="secondary">End</Text>
            <Input value={end} onChange={(event) => setEnd(event.target.value)} style={{ width: 140 }} />
          </Space>
          <Space direction="vertical" size={2}>
            <Text type="secondary">Initial cash</Text>
            <InputNumber min={1000} step={5000} value={initialCash} onChange={(value) => setInitialCash(Number(value || 0))} />
          </Space>
          <Space direction="vertical" size={2}>
            <Text type="secondary">Engine</Text>
            <Select
              value={engine}
              onChange={setEngine}
              style={{ minWidth: 140 }}
              options={[
                { value: "event", label: "event" },
                { value: "vectorbt-pro", label: "vectorbt-pro" },
                { value: "vectorbt", label: "vectorbt" },
                { value: "backtesting", label: "backtesting" },
                { value: "fallback", label: "fallback" },
              ]}
            />
          </Space>
        </Space>
        <Paragraph style={{ marginTop: 8, marginBottom: 0 }}>
          <Tag color="blue">{preset.label}</Tag> {preset.description}
        </Paragraph>
      </Card>

      <WorkflowEditor
        key={`${scenario}-${editorSeed}`}
        domain="strategy"
        paletteSections={STRATEGY_PALETTE}
        initialGraph={preset.graph}
        accentByKind={ACCENTS}
        onRun={runGraph}
        toolbarExtras={
          <Button icon={<PlayCircleOutlined />} onClick={() => applyScenario(scenario)}>
            Reset preset
          </Button>
        }
        height="560px"
      />

      <Row gutter={12}>
        <Col xs={24} lg={12}>
          <StreamCard
            title="Backtest run stream"
            taskId={runTaskId}
            status={runStream.status}
            done={runStream.done}
            events={runStream.events}
          />
        </Col>
        <Col xs={24} lg={12}>
          <StreamCard
            title="Optimization stream"
            taskId={optTaskId}
            status={optStream.status}
            done={optStream.done}
            events={optStream.events}
          />
        </Col>
      </Row>

      <Card size="small" title="Sweep controls">
        <Space wrap align="start">
          <Space direction="vertical" size={2}>
            <Text type="secondary">Method</Text>
            <Select
              value={sweepMethod}
              onChange={(value) => setSweepMethod(value as "grid" | "random")}
              style={{ width: 120 }}
              options={[
                { value: "grid", label: "grid" },
                { value: "random", label: "random" },
              ]}
            />
          </Space>
          <Space direction="vertical" size={2}>
            <Text type="secondary">Metric</Text>
            <Select
              value={sweepMetric}
              onChange={setSweepMetric}
              style={{ width: 140 }}
              options={[
                { value: "sharpe", label: "sharpe" },
                { value: "sortino", label: "sortino" },
                { value: "total_return", label: "total_return" },
              ]}
            />
          </Space>
          <Space direction="vertical" size={2}>
            <Text type="secondary">Lookback low/high/step</Text>
            <Space>
              <InputNumber value={lookbackLow} onChange={(value) => setLookbackLow(Number(value || 0))} />
              <InputNumber value={lookbackHigh} onChange={(value) => setLookbackHigh(Number(value || 0))} />
              <InputNumber value={lookbackStep} onChange={(value) => setLookbackStep(Number(value || 1))} />
            </Space>
          </Space>
          <Space direction="vertical" size={2}>
            <Text type="secondary">Top-quantile low/high/step</Text>
            <Space>
              <InputNumber value={topQLow} step={0.05} onChange={(value) => setTopQLow(Number(value || 0))} />
              <InputNumber value={topQHigh} step={0.05} onChange={(value) => setTopQHigh(Number(value || 0))} />
              <InputNumber value={topQStep} step={0.01} onChange={(value) => setTopQStep(Number(value || 0.01))} />
            </Space>
          </Space>
          <Space direction="vertical" size={2}>
            <Text type="secondary">max_trials / n_random</Text>
            <Space>
              <InputNumber value={maxTrials} min={1} max={2048} onChange={(value) => setMaxTrials(Number(value || 1))} />
              <InputNumber value={nRandom} min={1} max={1024} onChange={(value) => setNRandom(Number(value || 1))} />
            </Space>
          </Space>
        </Space>
      </Card>

      <Card size="small" title="Side-by-side comparison board">
        <Space direction="vertical" style={{ width: "100%" }}>
          <Space>
            <Select
              mode="multiple"
              value={compareIds}
              onChange={(values) => setCompareIds(values.map(String))}
              style={{ minWidth: 420 }}
              placeholder="Select run ids"
              options={(runs.data ?? []).map((item) => ({
                value: item.id,
                label: `${item.id.slice(0, 8)} · ${item.status} · sharpe=${item.sharpe ?? "—"}`,
              }))}
            />
            <Button onClick={loadComparisonBoard} loading={compareLoading}>
              Load comparison
            </Button>
          </Space>
          <Row gutter={12}>
            {compareRows.length === 0 ? (
              <Col span={24}>
                <Text type="secondary">Select run IDs and load comparison to inspect metrics side-by-side.</Text>
              </Col>
            ) : (
              compareRows.map((row) => (
                <Col key={row.id} xs={24} md={12} lg={8}>
                  <Card
                    size="small"
                    title={<Text code>{row.id.slice(0, 8)}</Text>}
                    extra={<Tag>{row.status}</Tag>}
                  >
                    <Space direction="vertical" size={2}>
                      <Text>Sharpe: {row.sharpe ?? "—"}</Text>
                      <Text>Sortino: {row.sortino ?? "—"}</Text>
                      <Text>Total return: {row.total_return ?? "—"}</Text>
                      <Text>Max drawdown: {row.max_drawdown ?? "—"}</Text>
                      <Text>Final equity: {row.final_equity ?? "—"}</Text>
                    </Space>
                  </Card>
                </Col>
              ))
            )}
          </Row>
        </Space>
      </Card>

      <Card size="small" title="Latest serialized strategy">
        <pre
          style={{
            fontSize: 11,
            maxHeight: 240,
            overflow: "auto",
            background: "var(--ant-color-bg-elevated)",
            padding: 8,
            borderRadius: 6,
          }}
        >
          {latestStrategyYaml || "Run the graph to preview serialized strategy YAML."}
        </pre>
      </Card>
    </Space>
  );
}
