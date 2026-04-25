"use client";

import { Card, Form, Input, InputNumber, Select, Space, Switch, Tag, Typography } from "antd";
import { useEffect } from "react";

import { useApiQuery } from "@/lib/api/hooks";

const { Text, Paragraph } = Typography;

export interface AgentCapabilitiesValue {
  tools: string[];
  mcp_servers: Array<{
    name: string;
    transport: string;
    command?: string;
    url?: string;
    args: string[];
    env: Record<string, string>;
    tools: string[];
    timeout_s?: number;
  }>;
  memory: {
    kind: "none" | "bm25" | "hybrid";
    role: string;
    persist_dir?: string | null;
    retrieval_top_k: number;
    write_through: boolean;
  };
  guardrails: {
    output_schema?: string | Record<string, unknown> | null;
    cost_budget_usd: number;
    rate_limit_per_minute: number;
    pii_redact: boolean;
    forbidden_terms: string[];
    require_rationale: boolean;
    min_confidence?: number | null;
  };
  output_schema?: string | Record<string, unknown> | null;
  max_cost_usd: number;
  max_calls: number;
}

export const DEFAULT_CAPABILITIES: AgentCapabilitiesValue = {
  tools: [],
  mcp_servers: [],
  memory: {
    kind: "bm25",
    role: "default",
    persist_dir: null,
    retrieval_top_k: 3,
    write_through: true,
  },
  guardrails: {
    output_schema: null,
    cost_budget_usd: 1.0,
    rate_limit_per_minute: 60,
    pii_redact: false,
    forbidden_terms: [],
    require_rationale: true,
    min_confidence: null,
  },
  output_schema: null,
  max_cost_usd: 1.0,
  max_calls: 20,
};

interface ToolListResp {
  tools: Array<{ name: string; qualname: string; doc?: string | null }>;
}

const SCHEMA_OPTIONS = [
  { value: "", label: "(none)" },
  {
    value: "aqp.agents.trading.types.AgentDecision",
    label: "AgentDecision (TradingAgents)",
  },
  {
    value: "aqp.backtest.llm_judge.JudgeReport",
    label: "JudgeReport (LLM judge)",
  },
];

interface AgentCapabilitiesPanelProps {
  value: AgentCapabilitiesValue;
  onChange: (next: AgentCapabilitiesValue) => void;
}

export function AgentCapabilitiesPanel({
  value,
  onChange,
}: AgentCapabilitiesPanelProps) {
  const tools = useApiQuery<ToolListResp>({
    queryKey: ["agents", "tools"],
    path: "/agents/tools",
    staleTime: 60_000,
  });

  const toolOptions = (tools.data?.tools ?? []).map((t) => ({
    value: t.name,
    label: t.name,
  }));

  function patch(part: Partial<AgentCapabilitiesValue>) {
    onChange({ ...value, ...part });
  }

  function patchMemory(part: Partial<AgentCapabilitiesValue["memory"]>) {
    onChange({ ...value, memory: { ...value.memory, ...part } });
  }

  function patchGuard(part: Partial<AgentCapabilitiesValue["guardrails"]>) {
    onChange({ ...value, guardrails: { ...value.guardrails, ...part } });
  }

  useEffect(() => {
    if (!value) onChange(DEFAULT_CAPABILITIES);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Card size="small" title="Agent capabilities">
      <Paragraph type="secondary">
        Tools, MCP servers, memory, guardrails, and structured output binding for
        the agentic alpha. Defaults preserve the legacy single-call behaviour.
      </Paragraph>
      <Form layout="vertical">
        <Form.Item label="Tools" tooltip="Names from /agents/tools registry">
          <Select
            mode="multiple"
            value={value.tools}
            onChange={(v) => patch({ tools: v })}
            options={toolOptions}
            allowClear
            showSearch
            placeholder="Pick tools the agent can call"
          />
        </Form.Item>
        <Form.Item label="Output schema" tooltip="Pydantic model qualname or '(none)'">
          <Select
            value={
              typeof value.guardrails.output_schema === "string"
                ? (value.guardrails.output_schema as string)
                : ""
            }
            options={SCHEMA_OPTIONS}
            onChange={(v) => patchGuard({ output_schema: v || null })}
          />
        </Form.Item>
        <Form.Item label="Memory">
          <Space wrap>
            <Select
              value={value.memory.kind}
              onChange={(v) => patchMemory({ kind: v as "none" | "bm25" | "hybrid" })}
              options={[
                { value: "none", label: "Disabled" },
                { value: "bm25", label: "BM25 (lexical)" },
                { value: "hybrid", label: "Hybrid (BM25 + Chroma)" },
              ]}
              style={{ width: 200 }}
            />
            <Input
              placeholder="role"
              value={value.memory.role}
              onChange={(e) => patchMemory({ role: e.target.value })}
              style={{ width: 160 }}
            />
            <InputNumber
              min={1}
              max={20}
              value={value.memory.retrieval_top_k}
              onChange={(v) => patchMemory({ retrieval_top_k: v ?? 3 })}
              style={{ width: 100 }}
              addonBefore="k"
            />
            <Switch
              checked={value.memory.write_through}
              onChange={(v) => patchMemory({ write_through: v })}
              checkedChildren="write"
              unCheckedChildren="ro"
            />
          </Space>
        </Form.Item>
        <Form.Item label="Guardrails">
          <Space wrap>
            <InputNumber
              min={0}
              step={0.1}
              addonBefore="$ budget"
              value={value.guardrails.cost_budget_usd}
              onChange={(v) => patchGuard({ cost_budget_usd: v ?? 1 })}
            />
            <InputNumber
              min={1}
              max={10000}
              addonBefore="rate / min"
              value={value.guardrails.rate_limit_per_minute}
              onChange={(v) => patchGuard({ rate_limit_per_minute: v ?? 60 })}
            />
            <InputNumber
              min={0}
              max={1}
              step={0.05}
              placeholder="min conf"
              value={value.guardrails.min_confidence ?? undefined}
              onChange={(v) => patchGuard({ min_confidence: v })}
            />
            <Switch
              checked={value.guardrails.pii_redact}
              onChange={(v) => patchGuard({ pii_redact: v })}
              checkedChildren="PII redact"
              unCheckedChildren="PII off"
            />
            <Switch
              checked={value.guardrails.require_rationale}
              onChange={(v) => patchGuard({ require_rationale: v })}
              checkedChildren="rationale"
              unCheckedChildren="optional"
            />
          </Space>
        </Form.Item>
        <Form.Item label="Forbidden terms (comma sep)">
          <Select
            mode="tags"
            tokenSeparators={[","]}
            value={value.guardrails.forbidden_terms}
            onChange={(v) => patchGuard({ forbidden_terms: v as string[] })}
          />
        </Form.Item>
        <Form.Item label="Caps">
          <Space>
            <InputNumber
              min={0}
              step={0.5}
              addonBefore="$ max total"
              value={value.max_cost_usd}
              onChange={(v) => patch({ max_cost_usd: v ?? 1 })}
            />
            <InputNumber
              min={1}
              max={2000}
              addonBefore="max calls"
              value={value.max_calls}
              onChange={(v) => patch({ max_calls: v ?? 20 })}
            />
          </Space>
        </Form.Item>
        <Form.Item label="MCP servers" tooltip="Optional Model Context Protocol servers">
          <Select
            mode="tags"
            tokenSeparators={[","]}
            value={value.mcp_servers.map((s) => s.name)}
            onChange={(names) => {
              const arr = (names as string[]).map(
                (n) =>
                  value.mcp_servers.find((s) => s.name === n) ?? {
                    name: n,
                    transport: "stdio",
                    args: [],
                    env: {},
                    tools: [],
                    timeout_s: 30,
                  },
              );
              patch({ mcp_servers: arr });
            }}
            placeholder="Type a server name and press enter"
          />
          {value.mcp_servers.length ? (
            <Space wrap style={{ marginTop: 8 }}>
              {value.mcp_servers.map((s) => (
                <Tag key={s.name}>{s.name}</Tag>
              ))}
            </Space>
          ) : (
            <Text type="secondary" style={{ fontSize: 12 }}>
              No MCP servers configured.
            </Text>
          )}
        </Form.Item>
      </Form>
    </Card>
  );
}
