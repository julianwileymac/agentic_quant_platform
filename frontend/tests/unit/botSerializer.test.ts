import { describe, expect, it } from "vitest";

import {
  deserializeBotSpec,
  serializeBotSpec,
  slugify,
} from "@/components/bots/botSerializer";

const SAMPLE_SPEC = {
  name: "AAPL Mean Rev",
  slug: "aapl-mean-rev",
  kind: "trading",
  description: "Test fixture",
  universe: { symbols: ["AAPL.NASDAQ", "MSFT.NASDAQ"], model: null },
  data_pipeline: { preset: "ohlcv-daily", source: "alpaca" },
  strategy: {
    class: "FrameworkAlgorithm",
    module_path: "aqp.strategies.framework",
    kwargs: {},
  },
  backtest: { engine: "vbt-pro:signals", kwargs: { initial_cash: 100_000 } },
  ml_models: [{ deployment_id: "alpha158-lgb", role: "alpha", weight: 1.0 }],
  agents: [{ spec_name: "research.equity", role: "advisor", inputs_template: {}, enabled: true }],
  rag: [
    {
      levels: ["l3"],
      orders: ["third"],
      corpora: ["strategies"],
      per_level_k: 4,
      final_k: 8,
      rerank: true,
      compress: true,
    },
  ],
  metrics: [{ name: "sharpe", threshold: 1.0, direction: "max" }],
  risk: { max_position_pct: 0.25, max_daily_loss_pct: 0.02, max_drawdown_pct: 0.2 },
  deployment: { target: "paper_session", brokerage: "simulated" },
};

describe("bot serializer", () => {
  it("round-trips every spec slot", () => {
    const graph = deserializeBotSpec(SAMPLE_SPEC);
    const reserialized = serializeBotSpec(graph, {
      name: "AAPL Mean Rev",
      slug: "aapl-mean-rev",
      kind: "trading",
      description: "Test fixture",
    });

    expect(reserialized.name).toBe(SAMPLE_SPEC.name);
    expect(reserialized.universe).toEqual(SAMPLE_SPEC.universe);
    expect(reserialized.data_pipeline).toEqual(SAMPLE_SPEC.data_pipeline);
    expect(reserialized.strategy).toEqual(SAMPLE_SPEC.strategy);
    expect(reserialized.backtest).toEqual(SAMPLE_SPEC.backtest);
    expect(reserialized.ml_models).toEqual(SAMPLE_SPEC.ml_models);
    expect(reserialized.agents).toEqual(SAMPLE_SPEC.agents);
    expect(reserialized.rag).toEqual(SAMPLE_SPEC.rag);
    expect(reserialized.metrics).toEqual(SAMPLE_SPEC.metrics);
    expect(reserialized.risk).toEqual(SAMPLE_SPEC.risk);
    expect(reserialized.deployment).toEqual(SAMPLE_SPEC.deployment);
  });

  it("slugifies sensibly", () => {
    expect(slugify("AAPL Mean Rev!!")).toBe("aapl-mean-rev");
    expect(slugify("  My Bot 2   ")).toBe("my-bot-2");
    expect(slugify("___")).toBe("");
  });

  it("emits a Universe slot from a graph with only symbols", () => {
    const graph = deserializeBotSpec({
      universe: { symbols: ["SPY"] },
    });
    expect(graph.nodes.length).toBeGreaterThanOrEqual(1);
    const universeNode = graph.nodes.find((n) => n.data.kind === "Universe");
    expect(universeNode).toBeDefined();
    expect(universeNode?.data.params).toMatchObject({ symbols: ["SPY"] });
  });
});
