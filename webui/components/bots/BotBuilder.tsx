"use client";

import { App, Button, Form, Input, Select, Space, Typography } from "antd";
import { useState } from "react";

import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import type { FlowGraph } from "@/components/flow/types";
import { BotsApi, type BotDetail, type BotKind } from "@/lib/api/bots";

import {
  BOT_NODE_ACCENTS,
  BOT_PALETTE,
} from "./botPalette";
import {
  deserializeBotSpec,
  serializeBotSpec,
  slugify,
} from "./botSerializer";

const { Text } = Typography;

interface BotBuilderProps {
  /** When set, the builder edits an existing bot via PUT /bots/{id}. */
  bot?: BotDetail;
  /** Default kind for new bots (controls available palette filtering). */
  defaultKind?: BotKind;
  /** Project the bot should be created under. */
  projectId?: string;
  onSaved?: (bot: BotDetail) => void;
}

const STARTER_TRADING_GRAPH: FlowGraph = {
  domain: "bot",
  version: 1,
  nodes: [
    {
      id: "uni-1",
      type: "aqp",
      position: { x: 60, y: 60 },
      data: {
        kind: "Universe",
        label: "Static symbols",
        params: { symbols: ["AAPL.NASDAQ", "MSFT.NASDAQ"] },
      },
    },
    {
      id: "strat-1",
      type: "aqp",
      position: { x: 340, y: 60 },
      data: {
        kind: "Strategy",
        label: "FrameworkAlgorithm",
        params: {
          class: "FrameworkAlgorithm",
          module_path: "aqp.strategies.framework",
          kwargs: {
            alpha_model: { class: "DualMACrossoverAlpha", kwargs: { fast: 10, slow: 50 } },
            portfolio_model: { class: "EqualWeightPortfolio" },
            risk_model: { class: "NoOpRiskModel" },
            execution_model: { class: "ImmediateExecutionModel" },
          },
        },
      },
    },
    {
      id: "eng-1",
      type: "aqp",
      position: { x: 620, y: 60 },
      data: {
        kind: "Engine",
        label: "vbt-pro signals",
        params: { engine: "vbt-pro:signals", kwargs: { initial_cash: 100000.0 } },
      },
    },
    {
      id: "dep-1",
      type: "aqp",
      position: { x: 900, y: 60 },
      data: {
        kind: "Deploy",
        label: "Paper session",
        params: {
          target: "paper_session",
          brokerage: "simulated",
          feed: "deterministic_replay",
          dry_run: true,
        },
      },
    },
  ],
  edges: [
    { id: "e1", source: "uni-1", target: "strat-1" },
    { id: "e2", source: "strat-1", target: "eng-1" },
    { id: "e3", source: "eng-1", target: "dep-1" },
  ],
};

const STARTER_RESEARCH_GRAPH: FlowGraph = {
  domain: "bot",
  version: 1,
  nodes: [
    {
      id: "ag-1",
      type: "aqp",
      position: { x: 60, y: 60 },
      data: {
        kind: "Agent",
        label: "Equity researcher",
        params: { spec_name: "research.equity", role: "equity_analyst" },
      },
    },
    {
      id: "rag-1",
      type: "aqp",
      position: { x: 340, y: 60 },
      data: {
        kind: "RAG",
        label: "SEC + ratios",
        params: {
          levels: ["l1", "l2"],
          orders: ["second"],
          corpora: ["sec_filings", "financial_ratios", "earnings_call"],
          per_level_k: 5,
          final_k: 12,
        },
      },
    },
  ],
  edges: [{ id: "e1", source: "ag-1", target: "rag-1" }],
};

export function BotBuilder({ bot, defaultKind = "trading", projectId, onSaved }: BotBuilderProps) {
  const { message } = App.useApp();
  const initialKind: BotKind = (bot?.kind as BotKind | undefined) ?? defaultKind;
  const [name, setName] = useState(bot?.name ?? "New Bot");
  const [slug, setSlug] = useState(bot?.slug ?? slugify("New Bot"));
  const [kind, setKind] = useState<BotKind>(initialKind);
  const [description, setDescription] = useState(bot?.description ?? "");
  const [graph, setGraph] = useState<FlowGraph>(
    bot?.spec ? deserializeBotSpec(bot.spec) : initialKind === "research" ? STARTER_RESEARCH_GRAPH : STARTER_TRADING_GRAPH,
  );
  const [saving, setSaving] = useState(false);

  async function save(currentGraph: FlowGraph) {
    setSaving(true);
    try {
      const spec = serializeBotSpec(currentGraph, { name, slug, kind, description });
      const saved = bot
        ? await BotsApi.update(bot.id, { spec })
        : await BotsApi.create(spec, projectId);
      onSaved?.(saved);
      message.success(bot ? "Bot updated" : "Bot created");
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 100px)", gap: 12 }}>
      <Form layout="inline" style={{ padding: "0 16px" }}>
        <Form.Item label="Name" required>
          <Input
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (!bot) setSlug(slugify(e.target.value));
            }}
            style={{ width: 240 }}
          />
        </Form.Item>
        <Form.Item label="Slug" required>
          <Input
            value={slug}
            onChange={(e) => setSlug(slugify(e.target.value))}
            disabled={Boolean(bot)}
            style={{ width: 200 }}
          />
        </Form.Item>
        <Form.Item label="Kind">
          <Select
            value={kind}
            onChange={(v) => {
              setKind(v);
              if (!bot && v !== kind) {
                setGraph(v === "research" ? STARTER_RESEARCH_GRAPH : STARTER_TRADING_GRAPH);
              }
            }}
            options={[
              { value: "trading", label: "Trading" },
              { value: "research", label: "Research" },
            ]}
            style={{ width: 140 }}
            disabled={Boolean(bot)}
          />
        </Form.Item>
        <Form.Item label="Description" style={{ flex: 1, minWidth: 240 }}>
          <Input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What does this bot do?"
          />
        </Form.Item>
        <Space>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {graph.nodes.length} nodes · {graph.edges.length} edges
          </Text>
          <Button
            type="primary"
            loading={saving}
            onClick={() => save(graph)}
          >
            {bot ? "Save changes" : "Create bot"}
          </Button>
        </Space>
      </Form>

      <div style={{ flex: 1 }}>
        <WorkflowEditor
          domain="bot"
          paletteSections={BOT_PALETTE}
          initialGraph={graph}
          accentByKind={BOT_NODE_ACCENTS}
          onRun={save}
        />
      </div>
    </div>
  );
}
