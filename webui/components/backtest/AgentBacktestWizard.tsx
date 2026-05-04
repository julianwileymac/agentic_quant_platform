"use client";

import { ArrowLeftOutlined, RocketOutlined } from "@ant-design/icons";
import {
  App,
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Divider,
  Empty,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Skeleton,
  Space,
  Steps,
  Switch,
  Tabs,
  Tag,
  Typography,
} from "antd";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  AgentCapabilitiesPanel,
  DEFAULT_CAPABILITIES,
  type AgentCapabilitiesValue,
} from "@/components/agents/AgentCapabilitiesPanel";
import {
  DatasetCatalogPicker,
  type DataSourcePayload,
} from "@/components/backtest/DatasetCatalogPicker";
import { MlAlphaPreview } from "@/components/backtest/MlAlphaPreview";
import { FeatureSetPicker } from "@/components/features/FeatureSetPicker";
import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import {
  buildSpec,
  useRegistryComponent,
  useRegistryKind,
  type ComponentSummary,
  type ParamSchema,
} from "@/lib/api/registry";
import { useChatStream } from "@/lib/ws";

const MonacoEditor = dynamic(() => import("@monaco-editor/react").then((m) => m.default), {
  ssr: false,
  loading: () => <Skeleton active />,
});

const { Text, Paragraph, Title } = Typography;

interface SubmitResp {
  task_id: string;
  stream_url?: string;
}

interface ProviderCatalog {
  active: string;
  providers: Array<{
    slug: string;
    default_deep_model: string;
    default_quick_model: string;
  }>;
}

interface ProviderControl {
  provider: string;
  deep_model: string;
  quick_model: string;
}

interface DeploymentLite {
  id: string;
  name: string;
  status: string;
}

interface ModuleSpec {
  class: string;
  module_path?: string;
  kwargs: Record<string, unknown>;
}

const STEP_KEYS = [
  "metadata",
  "universe",
  "alpha",
  "portfolio",
  "risk",
  "execution",
  "judge",
  "review",
] as const;
type StepKey = (typeof STEP_KEYS)[number];

const PRIMARY_KINDS: Record<StepKey, string[]> = {
  metadata: [],
  universe: ["universe"],
  alpha: ["strategy", "agent"],
  portfolio: ["portfolio", "strategy"],
  risk: ["risk", "strategy"],
  execution: ["execution", "strategy"],
  judge: ["judge"],
  review: [],
};

const DEFAULT_ALIASES: Partial<Record<StepKey, { alias: string; kind: string }>> = {
  universe: { alias: "StaticUniverse", kind: "universe" },
  alpha: { alias: "AgenticAlpha", kind: "strategy" },
  portfolio: { alias: "EqualWeightPortfolio", kind: "portfolio" },
  risk: { alias: "BasicRiskModel", kind: "risk" },
  execution: { alias: "MarketOrderExecution", kind: "execution" },
  judge: { alias: "LLMJudge", kind: "judge" },
};

interface StepValue {
  alias: string | null;
  kind: string | null;
  values: Record<string, unknown>;
}

function defaultValuesFor(component: ComponentSummary | undefined): Record<string, unknown> {
  if (!component) return {};
  const out: Record<string, unknown> = {};
  for (const p of component.params) {
    if (p.default !== null && p.default !== undefined && p.default !== "") {
      out[p.name] = p.default;
    }
  }
  return out;
}

function ParamField({
  param,
  value,
  onChange,
}: {
  param: ParamSchema;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  if (param.enum && param.enum.length > 0) {
    return (
      <Select
        placeholder={param.annotation}
        value={(value as string | undefined) ?? undefined}
        onChange={onChange}
        options={param.enum.map((v) => ({ value: String(v), label: String(v) }))}
        allowClear
      />
    );
  }
  if (param.type === "boolean") {
    return <Switch checked={Boolean(value)} onChange={onChange} />;
  }
  if (param.type === "integer" || param.type === "number") {
    return (
      <InputNumber
        style={{ width: "100%" }}
        value={value as number | undefined}
        onChange={(v) => onChange(v ?? null)}
        step={param.type === "integer" ? 1 : 0.01}
      />
    );
  }
  if (param.type === "array") {
    const arr = Array.isArray(value)
      ? (value as unknown[]).map(String).join(",")
      : (value as string | undefined) ?? "";
    return (
      <Input
        placeholder="comma-separated values"
        value={arr}
        onChange={(e) => {
          const parts = e.target.value
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean);
          onChange(parts);
        }}
      />
    );
  }
  if (param.type === "object") {
    return (
      <Input.TextArea
        rows={3}
        placeholder='JSON object e.g. {"key": "value"}'
        value={typeof value === "string" ? value : JSON.stringify(value ?? "")}
        onChange={(e) => {
          try {
            onChange(JSON.parse(e.target.value));
          } catch {
            onChange(e.target.value);
          }
        }}
      />
    );
  }
  return (
    <Input
      placeholder={param.annotation}
      value={(value as string | undefined) ?? ""}
      onChange={(e) => onChange(e.target.value)}
      allowClear
    />
  );
}

function ComponentForm({
  step,
  components,
  selected,
  onSelect,
  onChange,
}: {
  step: StepKey;
  components: ComponentSummary[];
  selected: StepValue;
  onSelect: (alias: string | null, kind: string | null) => void;
  onChange: (values: Record<string, unknown>) => void;
}) {
  const detail = useRegistryComponent(selected.kind, selected.alias);
  return (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <div>
        <Text type="secondary">Component</Text>
        <Select
          style={{ width: "100%", marginTop: 4 }}
          showSearch
          placeholder={`Pick a ${step} component`}
          value={selected.alias ?? undefined}
          onChange={(alias) => {
            const c = components.find((c) => c.alias === alias);
            onSelect(alias, c?.kind ?? selected.kind);
          }}
          optionFilterProp="label"
          options={components.map((c) => ({
            value: c.alias,
            label: c.alias,
            kind: c.kind,
          }))}
        />
      </div>
      {detail.data?.full_doc ? (
        <Paragraph type="secondary" style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>
          {detail.data.full_doc.split("\n\n")[0]}
        </Paragraph>
      ) : null}
      {detail.isLoading ? <Skeleton active /> : null}
      {detail.data?.params?.length ? (
        <Form layout="vertical">
          {detail.data.params.map((p) => (
            <Form.Item
              key={p.name}
              label={
                <Space>
                  <Text>{p.name}</Text>
                  <Tag color="blue">{p.type}</Tag>
                  {p.required ? <Tag color="red">required</Tag> : null}
                </Space>
              }
              tooltip={p.annotation}
            >
              <ParamField
                param={p}
                value={selected.values[p.name]}
                onChange={(v) => onChange({ ...selected.values, [p.name]: v })}
              />
            </Form.Item>
          ))}
        </Form>
      ) : detail.data ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No constructor params." />
      ) : null}
    </Space>
  );
}

function buildResolvedConfig({
  metadata,
  steps,
  judgeEnabled,
  featureSetId,
  capabilities,
}: {
  metadata: {
    runName: string;
    symbols: string[];
    start: string;
    end: string;
    cash: number;
    useMlAlpha: boolean;
    ensembleAlpha: boolean;
    modelDeploymentId: string | null;
    selectedDataSource: DataSourcePayload | null;
  };
  steps: Record<StepKey, StepValue>;
  judgeEnabled: boolean;
  featureSetId: string | null;
  capabilities: AgentCapabilitiesValue;
}): Record<string, unknown> {
  const cfg: Record<string, unknown> = {
    name: metadata.runName,
    strategy: {
      class: "FrameworkAlgorithm",
      module_path: "aqp.strategies.framework",
      kwargs: {
        strategy_id: metadata.runName.replace(/[^a-z0-9_-]+/gi, "_").toLowerCase(),
        rebalance_every: 1,
      },
    },
    backtest: {
      class: "EventDrivenBacktester",
      module_path: "aqp.backtest.engine",
      kwargs: {
        initial_cash: metadata.cash,
        start: metadata.start,
        end: metadata.end,
      },
    },
  };

  const strat = cfg.strategy as { kwargs: Record<string, unknown> };
  const kwargs = strat.kwargs;

  const universeStep = steps.universe;
  if (universeStep.alias) {
    const kw = { ...universeStep.values };
    if (metadata.symbols.length && !kw.symbols) {
      kw.symbols = metadata.symbols;
    }
    kwargs.universe_model = {
      class: universeStep.alias,
      module_path: undefined,
      kwargs: kw,
    } as ModuleSpec;
  }
  for (const key of ["alpha", "portfolio", "risk", "execution"] as const) {
    const step = steps[key];
    if (step.alias) {
      const target = `${key === "alpha" ? "alpha_model" : `${key}_model`}` as
        | "alpha_model"
        | "portfolio_model"
        | "risk_model"
        | "execution_model";
      const stepKwargs = { ...step.values };
      // Thread capabilities into the AgenticAlpha kwargs only — other
      // alphas don't accept the capability layer.
      if (
        key === "alpha" &&
        (step.alias === "AgenticAlpha" || step.alias === "agentic_alpha")
      ) {
        stepKwargs.tools = capabilities.tools;
        stepKwargs.mcp_servers = capabilities.mcp_servers;
        stepKwargs.memory = capabilities.memory;
        stepKwargs.guardrails = capabilities.guardrails;
        stepKwargs.output_schema = capabilities.guardrails.output_schema ?? null;
        stepKwargs.max_cost_usd = capabilities.max_cost_usd;
        stepKwargs.max_calls = capabilities.max_calls;
      }
      kwargs[target] = {
        class: step.alias,
        module_path: undefined,
        kwargs: stepKwargs,
      } as ModuleSpec;
    }
  }

  if (judgeEnabled && steps.judge.alias) {
    cfg.judge = {
      class: steps.judge.alias,
      module_path: undefined,
      kwargs: steps.judge.values,
    } as ModuleSpec;
  }

  if (featureSetId) {
    cfg.feature_set_id = featureSetId;
  }
  if (metadata.useMlAlpha && metadata.modelDeploymentId) {
    const mlSpec: ModuleSpec = {
      class: "DeployedModelAlpha",
      module_path: "aqp.strategies.ml_alphas",
      kwargs: {
        deployment_id: metadata.modelDeploymentId,
      },
    };
    if (metadata.ensembleAlpha && kwargs.alpha_model) {
      const ruleAlpha = kwargs.alpha_model as ModuleSpec;
      kwargs.alpha_model = {
        class: "EnsembleAlpha",
        module_path: "aqp.strategies.ml_alphas",
        kwargs: {
          alphas: [ruleAlpha, mlSpec],
        },
      } as ModuleSpec;
    } else {
      kwargs.alpha_model = mlSpec;
    }
  }
  if (metadata.selectedDataSource) {
    cfg.data_source = metadata.selectedDataSource;
  }

  return cfg;
}

export function AgentBacktestWizard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const prefillAlpha = searchParams.get("alpha");
  const prefillAgent = searchParams.get("agent");
  const prefillDatasetPreset = searchParams.get("datasetPreset");
  const { message } = App.useApp();
  const [stepIdx, setStepIdx] = useState(0);
  const [runName, setRunName] = useState("agent-backtest");
  const [symbols, setSymbols] = useState<string[]>(["AAPL", "MSFT"]);
  const [start, setStart] = useState("2024-01-01");
  const [end, setEnd] = useState("2024-06-30");
  const [cash, setCash] = useState(100000);
  const [judgeEnabled, setJudgeEnabled] = useState(true);
  const [featureSetId, setFeatureSetId] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<AgentCapabilitiesValue>(DEFAULT_CAPABILITIES);
  const [provider, setProvider] = useState<string>("");
  const [deepModel, setDeepModel] = useState<string>("");
  const [quickModel, setQuickModel] = useState<string>("");
  const [maxDebateRounds, setMaxDebateRounds] = useState<number>(2);
  const [rebalanceFrequency, setRebalanceFrequency] = useState("weekly");
  const [mode, setMode] = useState("precompute");
  const [skipPrecompute, setSkipPrecompute] = useState(false);
  const [xBacktests, setXBacktests] = useState(1);
  const [maxSymbolsPerRun, setMaxSymbolsPerRun] = useState<number | null>(null);
  const [rotateSymbols, setRotateSymbols] = useState(true);
  const [windowMode, setWindowMode] = useState<"fixed" | "rolling">("fixed");
  const [entryCondition, setEntryCondition] = useState("");
  const [exitCondition, setExitCondition] = useState("");
  const [selectedDataSource, setSelectedDataSource] = useState<DataSourcePayload | null>(null);
  const [useMlAlpha, setUseMlAlpha] = useState(false);
  const [ensembleAlpha, setEnsembleAlpha] = useState(false);
  const [modelDeploymentId, setModelDeploymentId] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const stream = useChatStream(taskId);

  const providerCatalog = useApiQuery<ProviderCatalog>({
    queryKey: ["agentic", "providers", "wizard"],
    path: "/agentic/providers",
    staleTime: 60_000,
  });
  const providerControl = useApiQuery<ProviderControl>({
    queryKey: ["agentic", "provider-control", "wizard"],
    path: "/agentic/provider-control",
    staleTime: 15_000,
  });
  const deployments = useApiQuery<DeploymentLite[]>({
    queryKey: ["ml", "deployments", "wizard"],
    path: "/ml/deployments",
    staleTime: 15_000,
    select: (raw) => (Array.isArray(raw) ? (raw as DeploymentLite[]) : []),
  });

  const [steps, setSteps] = useState<Record<StepKey, StepValue>>(() => {
    const init: Record<StepKey, StepValue> = {
      metadata: { alias: null, kind: null, values: {} },
      universe: {
        alias: DEFAULT_ALIASES.universe?.alias ?? null,
        kind: DEFAULT_ALIASES.universe?.kind ?? null,
        values: {},
      },
      alpha: {
        alias: DEFAULT_ALIASES.alpha?.alias ?? null,
        kind: DEFAULT_ALIASES.alpha?.kind ?? null,
        values: {},
      },
      portfolio: {
        alias: DEFAULT_ALIASES.portfolio?.alias ?? null,
        kind: DEFAULT_ALIASES.portfolio?.kind ?? null,
        values: {},
      },
      risk: {
        alias: DEFAULT_ALIASES.risk?.alias ?? null,
        kind: DEFAULT_ALIASES.risk?.kind ?? null,
        values: {},
      },
      execution: {
        alias: DEFAULT_ALIASES.execution?.alias ?? null,
        kind: DEFAULT_ALIASES.execution?.kind ?? null,
        values: {},
      },
      judge: {
        alias: DEFAULT_ALIASES.judge?.alias ?? null,
        kind: DEFAULT_ALIASES.judge?.kind ?? null,
        values: {},
      },
      review: { alias: null, kind: null, values: {} },
    };
    return init;
  });

  useEffect(() => {
    if (prefillAlpha) {
      setSteps((prev) => ({
        ...prev,
        alpha: { alias: prefillAlpha, kind: "strategy", values: {} },
      }));
      setStepIdx(2);
    } else if (prefillAgent) {
      setSteps((prev) => ({
        ...prev,
        alpha: { alias: prefillAgent, kind: "agent", values: {} },
      }));
      setStepIdx(2);
    }
    if (prefillDatasetPreset) {
      setRunName((prev) =>
        prev === "agent-backtest" ? `preset-${prefillDatasetPreset}` : prev,
      );
    }
  }, [prefillAgent, prefillAlpha, prefillDatasetPreset]);

  useEffect(() => {
    if (!providerControl.data) return;
    setProvider((prev) => prev || providerControl.data?.provider || "");
    setDeepModel((prev) => prev || providerControl.data?.deep_model || "");
    setQuickModel((prev) => prev || providerControl.data?.quick_model || "");
  }, [providerControl.data]);

  const stepKey: StepKey = STEP_KEYS[stepIdx] ?? STEP_KEYS[0];
  const primaryKinds = PRIMARY_KINDS[stepKey] ?? [];

  // Always fetch the primary kind plus the optional secondary so the alpha
  // and portfolio steps see both ``strategy`` and ``agent`` aliases.
  const primary = useRegistryKind(primaryKinds[0]);
  const secondary = useRegistryKind(primaryKinds[1]);

  const components: ComponentSummary[] = useMemo(() => {
    const list = [...(primary.data ?? []), ...(secondary.data ?? [])];
    const seen = new Set<string>();
    return list.filter((c) => {
      const k = `${c.kind}:${c.alias}`;
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    });
  }, [primary.data, secondary.data]);

  const currentStep = steps[stepKey];
  const selectedDataSourcePayload = selectedDataSource;

  // Hydrate default values when a component is first selected.
  const detail = useRegistryComponent(currentStep.kind, currentStep.alias);
  const judgeDetail = useRegistryComponent(steps.judge.kind, steps.judge.alias);
  useEffect(() => {
    if (!detail.data) return;
    if (Object.keys(currentStep.values).length === 0) {
      const defaults = defaultValuesFor(detail.data);
      if (Object.keys(defaults).length) {
        setSteps((prev) => ({
          ...prev,
          [stepKey]: { ...prev[stepKey], values: defaults },
        }));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail.data?.alias]);

  const resolvedConfig = useMemo(
    () =>
      buildResolvedConfig({
        metadata: {
          runName,
          symbols,
          start,
          end,
          cash,
          useMlAlpha,
          ensembleAlpha,
          modelDeploymentId,
          selectedDataSource: selectedDataSourcePayload,
        },
        steps,
        judgeEnabled,
        featureSetId,
        capabilities,
      }),
    [
      runName,
      symbols,
      start,
      end,
      cash,
      useMlAlpha,
      ensembleAlpha,
      modelDeploymentId,
      selectedDataSourcePayload,
      steps,
      judgeEnabled,
      featureSetId,
      capabilities,
    ],
  );

  async function submit() {
    try {
      const judgeCfg =
        judgeEnabled && steps.judge.alias ? buildSpec(judgeDetail.data, steps.judge.values) : null;
      const res = await apiFetch<SubmitResp>("/agentic/pipeline", {
        method: "POST",
        body: JSON.stringify({
          config: resolvedConfig,
          symbols,
          start,
          end,
          run_name: runName,
          mode,
          x_backtests: xBacktests,
          provider,
          deep_model: deepModel,
          quick_model: quickModel,
          max_debate_rounds: maxDebateRounds,
          rebalance_frequency: rebalanceFrequency,
          skip_precompute: skipPrecompute,
          universe_filter: {
            max_symbols: maxSymbolsPerRun ?? undefined,
            rotate_symbols: rotateSymbols,
            sweep_mode: windowMode,
          },
          conditions: {
            entry_rule: entryCondition || undefined,
            exit_rule: exitCondition || undefined,
          },
          data_source: selectedDataSourcePayload,
          judge: judgeCfg || undefined,
        }),
      });
      setTaskId(res.task_id);
      message.success(`Backtest queued: ${res.task_id}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title={
        <Space>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => router.push("/backtest")} />
          New agent backtest
        </Space>
      }
      subtitle="Compose a Lean-style 5-stage agent strategy with a registered LLM judge."
      extra={
        <Button type="primary" icon={<RocketOutlined />} onClick={submit}>
          Run
        </Button>
      }
    >
      <Row gutter={16}>
        <Col xs={24} lg={16}>
          <Card size="small">
            <Steps
              current={stepIdx}
              onChange={setStepIdx}
              size="small"
              items={STEP_KEYS.map((k) => ({ title: k }))}
            />
          </Card>
          <Card size="small" style={{ marginTop: 16 }}>
            {stepKey === "metadata" && (
              <Form layout="vertical">
                {prefillAlpha || prefillAgent || prefillDatasetPreset ? (
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 12 }}
                    message="Prefilled from source library"
                    description={[
                      prefillAlpha ? `alpha=${prefillAlpha}` : null,
                      prefillAgent ? `agent=${prefillAgent}` : null,
                      prefillDatasetPreset ? `datasetPreset=${prefillDatasetPreset}` : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  />
                ) : null}
                <Form.Item label="Run name">
                  <Input value={runName} onChange={(e) => setRunName(e.target.value)} />
                </Form.Item>
                <Form.Item label="Symbols">
                  <Select
                    mode="tags"
                    style={{ width: "100%" }}
                    value={symbols}
                    tokenSeparators={[",", " "]}
                    onChange={(vals) => setSymbols(vals as string[])}
                  />
                </Form.Item>
                <Row gutter={12}>
                  <Col span={8}>
                    <Form.Item label="Start">
                      <Input value={start} onChange={(e) => setStart(e.target.value)} placeholder="YYYY-MM-DD" />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="End">
                      <Input value={end} onChange={(e) => setEnd(e.target.value)} placeholder="YYYY-MM-DD" />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="Initial cash">
                      <InputNumber style={{ width: "100%" }} value={cash} onChange={(v) => setCash(v ?? 0)} />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item
                  label="Feature set (optional)"
                  tooltip="Named indicator / model-prediction bundle consumed by every alpha that supports it."
                >
                  <FeatureSetPicker
                    value={featureSetId}
                    onChange={(id) => setFeatureSetId(id)}
                  />
                </Form.Item>
                <Divider orientation="left" style={{ marginTop: 0 }}>
                  Agentic runtime
                </Divider>
                <Row gutter={12}>
                  <Col span={8}>
                    <Form.Item label="Provider">
                      <Select
                        value={provider || undefined}
                        allowClear
                        options={(providerCatalog.data?.providers ?? []).map((p) => ({
                          value: p.slug,
                          label: p.slug,
                        }))}
                        onChange={(value) => setProvider(value ?? "")}
                      />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="Deep model">
                      <Input value={deepModel} onChange={(e) => setDeepModel(e.target.value)} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="Quick model">
                      <Input value={quickModel} onChange={(e) => setQuickModel(e.target.value)} />
                    </Form.Item>
                  </Col>
                </Row>
                <Row gutter={12}>
                  <Col span={6}>
                    <Form.Item label="Backtest runs (x_backtests)">
                      <InputNumber
                        min={1}
                        max={64}
                        style={{ width: "100%" }}
                        value={xBacktests}
                        onChange={(v) => setXBacktests(Number(v ?? 1))}
                      />
                    </Form.Item>
                  </Col>
                  <Col span={6}>
                    <Form.Item label="Max debate rounds">
                      <InputNumber
                        min={1}
                        max={12}
                        style={{ width: "100%" }}
                        value={maxDebateRounds}
                        onChange={(v) => setMaxDebateRounds(Number(v ?? 1))}
                      />
                    </Form.Item>
                  </Col>
                  <Col span={6}>
                    <Form.Item label="Rebalance">
                      <Select
                        value={rebalanceFrequency}
                        options={[
                          { value: "daily", label: "daily" },
                          { value: "weekly", label: "weekly" },
                          { value: "monthly", label: "monthly" },
                        ]}
                        onChange={setRebalanceFrequency}
                      />
                    </Form.Item>
                  </Col>
                  <Col span={6}>
                    <Form.Item label="Mode">
                      <Select
                        value={mode}
                        options={[
                          { value: "precompute", label: "precompute" },
                          { value: "live", label: "live" },
                        ]}
                        onChange={setMode}
                      />
                    </Form.Item>
                  </Col>
                </Row>
                <Row gutter={12}>
                  <Col span={8}>
                    <Form.Item label="Window sweep">
                      <Select
                        value={windowMode}
                        options={[
                          { value: "fixed", label: "fixed window" },
                          { value: "rolling", label: "rolling window" },
                        ]}
                        onChange={(v) => setWindowMode(v as "fixed" | "rolling")}
                      />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="Max symbols per run">
                      <InputNumber
                        min={1}
                        style={{ width: "100%" }}
                        value={maxSymbolsPerRun ?? undefined}
                        onChange={(v) => setMaxSymbolsPerRun(v ? Number(v) : null)}
                      />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="Rotate symbols">
                      <Switch checked={rotateSymbols} onChange={setRotateSymbols} />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label="Skip precompute (use existing decision cache)">
                  <Switch checked={skipPrecompute} onChange={setSkipPrecompute} />
                </Form.Item>
                <Row gutter={12}>
                  <Col span={12}>
                    <Form.Item label="Entry condition (optional)">
                      <Input
                        value={entryCondition}
                        onChange={(e) => setEntryCondition(e.target.value)}
                        placeholder="e.g. close > sma_20 and regime == 'risk_on'"
                      />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="Exit condition (optional)">
                      <Input
                        value={exitCondition}
                        onChange={(e) => setExitCondition(e.target.value)}
                        placeholder="e.g. drawdown > 0.08 or pnl < -0.03"
                      />
                    </Form.Item>
                  </Col>
                </Row>
                <Divider orientation="left">Data source</Divider>
                <DatasetCatalogPicker
                  value={selectedDataSource}
                  onChange={setSelectedDataSource}
                  startHint={start}
                  endHint={end}
                  onSymbolsDetected={(detected) => {
                    if (detected.length && symbols.length === 0) {
                      setSymbols(detected.slice(0, 20));
                    }
                  }}
                />
                <Divider orientation="left">ML alpha (optional)</Divider>
                <Form.Item>
                  <Space direction="vertical">
                    <Checkbox
                      checked={useMlAlpha}
                      onChange={(e) => setUseMlAlpha(e.target.checked)}
                    >
                      Use a deployed ML prediction alpha (DeployedModelAlpha)
                    </Checkbox>
                    {useMlAlpha ? (
                      <Checkbox
                        checked={ensembleAlpha}
                        onChange={(e) => setEnsembleAlpha(e.target.checked)}
                      >
                        Ensemble with rule-based alpha (EnsembleAlpha)
                      </Checkbox>
                    ) : null}
                  </Space>
                </Form.Item>
                {useMlAlpha ? (
                  <>
                    <Form.Item label="Model deployment">
                      <Select
                        value={modelDeploymentId ?? undefined}
                        onChange={(value) => setModelDeploymentId(value ?? null)}
                        options={(deployments.data ?? []).map((d) => ({
                          value: d.id,
                          label: `${d.name} (${d.status})`,
                        }))}
                      />
                    </Form.Item>
                    {modelDeploymentId ? (
                      <MlAlphaPreview
                        deploymentId={modelDeploymentId}
                        symbols={symbols}
                        start={start}
                        end={end}
                      />
                    ) : null}
                  </>
                ) : null}
              </Form>
            )}
            {stepKey === "judge" && (
              <Space direction="vertical" style={{ width: "100%" }} size="middle">
                <Checkbox checked={judgeEnabled} onChange={(e) => setJudgeEnabled(e.target.checked)}>
                  Run an LLM-as-judge after the backtest completes
                </Checkbox>
                {judgeEnabled ? (
                  <ComponentForm
                    step={stepKey}
                    components={components}
                    selected={currentStep}
                    onSelect={(alias, kind) =>
                      setSteps((prev) => ({
                        ...prev,
                        [stepKey]: { alias, kind, values: {} },
                      }))
                    }
                    onChange={(vals) =>
                      setSteps((prev) => ({
                        ...prev,
                        [stepKey]: { ...prev[stepKey], values: vals },
                      }))
                    }
                  />
                ) : (
                  <Alert
                    type="info"
                    message="Judge step skipped — no critique will be generated."
                    showIcon
                  />
                )}
              </Space>
            )}
            {stepKey === "review" && (
              <>
                <Title level={5}>Resolved YAML</Title>
                <MonacoEditor
                  height="400px"
                  defaultLanguage="json"
                  value={JSON.stringify(resolvedConfig, null, 2)}
                  options={{ readOnly: true, minimap: { enabled: false }, fontSize: 12 }}
                />
                <Paragraph type="secondary" style={{ marginTop: 12 }}>
                  Click <Tag color="blue">Run</Tag> in the top-right to submit. The judge will
                  fire automatically once the run completes if you enabled it.
                </Paragraph>
              </>
            )}
            {!["metadata", "judge", "review"].includes(stepKey) && (
              primary.isLoading ? (
                <Skeleton active />
              ) : (
                <>
                  <ComponentForm
                    step={stepKey}
                    components={components}
                    selected={currentStep}
                    onSelect={(alias, kind) =>
                      setSteps((prev) => ({
                        ...prev,
                        [stepKey]: { alias, kind, values: {} },
                      }))
                    }
                    onChange={(vals) =>
                      setSteps((prev) => ({
                        ...prev,
                        [stepKey]: { ...prev[stepKey], values: vals },
                      }))
                    }
                  />
                  {stepKey === "alpha" &&
                  (currentStep.alias === "AgenticAlpha" ||
                    currentStep.alias === "agentic_alpha") ? (
                    <div style={{ marginTop: 16 }}>
                      <AgentCapabilitiesPanel
                        value={capabilities}
                        onChange={setCapabilities}
                      />
                    </div>
                  ) : null}
                </>
              )
            )}
            <Space style={{ marginTop: 16 }}>
              <Button disabled={stepIdx === 0} onClick={() => setStepIdx((i) => Math.max(0, i - 1))}>
                Back
              </Button>
              <Button
                type="primary"
                disabled={stepIdx === STEP_KEYS.length - 1}
                onClick={() => setStepIdx((i) => Math.min(STEP_KEYS.length - 1, i + 1))}
              >
                Next
              </Button>
            </Space>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="Stream" size="small">
            {!taskId ? (
              <Text type="secondary">Run a backtest to see progress here.</Text>
            ) : (
              <>
                <Paragraph copyable={{ text: taskId }}>Task: {taskId}</Paragraph>
                <Text type="secondary">Status: {stream.status}</Text>
                {stream.error ? (
                  <Alert type="error" message={stream.error} style={{ marginTop: 8 }} />
                ) : null}
                <pre
                  style={{
                    fontSize: 11,
                    maxHeight: 320,
                    overflow: "auto",
                    background: "var(--ant-color-bg-elevated)",
                    padding: 12,
                    borderRadius: 6,
                  }}
                >
                  {(stream.events ?? []).map((e) => JSON.stringify(e)).join("\n")}
                </pre>
              </>
            )}
          </Card>
          <Card title="Resolved JSON" size="small" style={{ marginTop: 16 }}>
            <Tabs
              size="small"
              items={[
                {
                  key: "config",
                  label: "Config",
                  children: (
                    <pre style={{ fontSize: 11, maxHeight: 240, overflow: "auto" }}>
                      {JSON.stringify(resolvedConfig, null, 2)}
                    </pre>
                  ),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
