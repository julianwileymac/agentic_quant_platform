import type { Metadata } from "next";
import {
  Activity,
  BookOpen,
  Box,
  Cpu,
  Gauge,
  Layers,
  LineChart,
  Network,
  Sparkles,
  TrendingUp,
  Zap,
} from "lucide-react";

import { CallToActionBlock } from "@/components/marketing/CallToActionBlock";
import { CodeBlock } from "@/components/marketing/CodeBlock";
import { FaqAccordion } from "@/components/marketing/FaqAccordion";
import { FeatureBreakdown } from "@/components/marketing/FeatureBreakdown";
import { FeatureCard } from "@/components/marketing/FeatureCard";
import { FeatureGrid } from "@/components/marketing/FeatureGrid";
import { Hero } from "@/components/marketing/Hero";
import { MetricSparkline } from "@/components/marketing/MetricSparkline";
import { MotionInView } from "@/components/marketing/MotionInView";
import { ProductNav } from "@/components/marketing/ProductNav";
import { SectionHeader } from "@/components/marketing/SectionHeader";
import { StatStrip } from "@/components/marketing/StatStrip";

export const metadata: Metadata = {
  title: "Backtesting",
  description:
    "Nine backtest engines under one capability-driven dispatch. Per-bar agent dispatcher. RL injection via context['rl_agent']. JAX-compiled HJB solvers for market making and optimal execution.",
};

export const dynamic = "force-static";
export const revalidate = 3600;

const NAV_ITEMS = [
  { id: "overview", label: "Overview" },
  { id: "engines", label: "9 engines" },
  { id: "dispatch", label: "Capability dispatch" },
  { id: "agents", label: "Per-bar agents" },
  { id: "rl", label: "RL injection" },
  { id: "optimal", label: "Optimal control" },
  { id: "faq", label: "FAQ" },
];

export default function BacktestingPage() {
  return (
    <>
      <Hero
        eyebrow="Product · Backtesting"
        eyebrowIcon={Activity}
        title="One API. Nine engines. The right tool for every workflow."
        titleHighlight="Nine engines"
        subtitle="Capability-driven dispatch picks vectorbt-pro for the fast path, the event-driven engine for agent-aware loops, hftbacktest for LOB simulation, and six more for parity / fallback. Inject agents and RL policies through the same context."
        primaryCta={{ label: "Start free", href: "/signup" }}
        secondaryCta={{ label: "Backtest engines docs", href: "/docs/backtest" }}
        illustration={
          <div
            className="space-y-3 rounded-xl p-4"
            style={{
              background: "var(--glass-bg)",
              border: "1px solid var(--glass-border)",
              backdropFilter: "blur(var(--glass-blur))",
            }}
          >
            <div className="grid grid-cols-2 gap-3">
              <MetricSparkline
                data={EQUITY_CURVE}
                label="Equity"
                value="+38.2%"
                tone="tertiary"
                height={84}
                showDelta={false}
              />
              <MetricSparkline
                data={DRAWDOWN_CURVE}
                label="Drawdown"
                value="-6.5%"
                tone="neg"
                height={84}
                showDelta={false}
              />
            </div>
            <div className="grid grid-cols-3 gap-2">
              {[
                { l: "Sharpe", v: "1.94" },
                { l: "Sortino", v: "2.81" },
                { l: "Calmar", v: "3.20" },
              ].map((s) => (
                <div
                  key={s.l}
                  className="rounded-md px-2 py-1 text-center"
                  style={{
                    background: "var(--bg-elevated)",
                    border: "1px solid var(--border-default)",
                  }}
                >
                  <div
                    className="text-[10px] uppercase tracking-wider"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {s.l}
                  </div>
                  <div
                    className="text-sm font-bold tabular"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {s.v}
                  </div>
                </div>
              ))}
            </div>
          </div>
        }
      />

      <ProductNav items={NAV_ITEMS} />

      <StatStrip
        stats={[
          { value: 9, label: "Backtest engines", tone: "primary" },
          { value: 12, label: "Capabilities tracked", tone: "secondary" },
          { value: 2, label: "HJB solvers (JAX)", tone: "tertiary" },
          { value: 5, label: "Modes (vectorbt-pro)", tone: "warn" },
        ]}
      />

      {/* Overview */}
      <section id="overview" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Overview"
            title="Backtest as a typed system, not a script collection"
            subtitle="Every engine implements BaseBacktestEngine. Every engine declares an EngineCapabilities dataclass. The runner picks the engine that satisfies your strategy's needs and degrades gracefully through a documented fallback cascade."
          />
          <FeatureGrid columns={3}>
            <FeatureCard
              icon={Layers}
              tone="primary"
              title="Shared ABC"
              body="BaseBacktestEngine guarantees one .run(strategy, **ctx) entry-point and one BacktestResult dataclass — across all nine engines."
            />
            <FeatureCard
              icon={Cpu}
              tone="secondary"
              title="Capability dispatch"
              body="EngineCapabilities (supports_options, supports_lob, supports_agent_injection, supports_rl_injection, ...) selects the right engine for your strategy."
            />
            <FeatureCard
              icon={Network}
              tone="tertiary"
              title="Plug-in agents + RL"
              body="The event-driven engine surfaces context['agents'] and context['rl_agent']. Strategies query agents per bar without leaking from the agentic stack."
            />
            <FeatureCard
              icon={Box}
              tone="warn"
              title="Optimal control"
              body="JAX-compiled HJB solvers (Avellaneda-Stoikov, Cartea-Jaimungal-Penalva) ship as reference policies alongside the LOB engine."
            />
            <FeatureCard
              icon={LineChart}
              tone="primary"
              title="QuantStats tearsheets"
              body="POST /analytics/portfolio/tearsheet renders interactive HTML reports off the gold-tier rl.equity_curves / backtest_runs ledger."
            />
            <FeatureCard
              icon={Gauge}
              tone="tertiary"
              title="Fast metrics fast path"
              body="POST /analytics/portfolio/metrics for synchronous Sharpe / Sortino / vol / max-DD / Calmar without the full tearsheet render."
            />
          </FeatureGrid>
        </div>
      </section>

      {/* 9 engines */}
      <section
        id="engines"
        className="px-6 py-24"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="The cascade"
            title="Nine engines, one capability matrix"
            subtitle="Each engine has a sweet spot. The dispatcher picks the highest-priority engine that satisfies the strategy's declared needs and falls back when a dep is missing."
          />
          <div className="overflow-hidden rounded-xl" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", backdropFilter: "blur(var(--glass-blur))" }}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b" style={{ borderColor: "var(--border-default)" }}>
                    <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>Engine</th>
                    <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>Sweet spot</th>
                    <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>Capabilities</th>
                  </tr>
                </thead>
                <tbody>
                  {ENGINES.map((e) => (
                    <tr key={e.name} className="border-t" style={{ borderColor: "var(--border-default)" }}>
                      <td className="px-4 py-3">
                        <div className="font-mono text-sm font-bold" style={{ color: "var(--accent-primary)" }}>{e.name}</div>
                        <div className="text-xs" style={{ color: "var(--text-muted)" }}>{e.module}</div>
                      </td>
                      <td className="px-4 py-3" style={{ color: "var(--text-primary)" }}>{e.sweet}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {e.caps.map((c) => (
                            <code
                              key={c}
                              className="rounded px-1.5 py-0.5 text-[10px] font-mono"
                              style={{
                                background: "var(--bg-elevated)",
                                border: "1px solid var(--border-default)",
                                color: "var(--text-secondary)",
                              }}
                            >
                              {c}
                            </code>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>

      {/* Capability dispatch */}
      <section id="dispatch" className="px-6">
        <FeatureBreakdown
          eyebrow="Capability dispatch"
          tone="primary"
          title="Pick the right engine without naming the engine."
          body="Declare what your strategy needs (options? LOB? agents? RL?) and the runner picks the highest-priority engine that satisfies you. Missing optional deps degrade through a documented fallback cascade. No engine? Then you get a clear error, not a silent vbt-pro stub."
          bullets={[
            "EngineCapabilities is a dataclass on the engine class — typed contract, not docstring",
            "Required: supports_panel | supports_event | supports_options | supports_lob",
            "Optional: supports_agent_injection | supports_rl_injection | supports_factor_panel | supports_walk_forward | supports_param_sweep | supports_indicator_factory",
            "Fallback cascade documented in BaseBacktestEngine subclass docs",
          ]}
          cta={{ label: "Capability matrix", href: "/docs/backtest/capabilities" }}
          visual={
            <CodeBlock
              filename="dispatch.py"
              language="python"
              code={`from aqp.backtest import dispatch_engine, EngineCapabilities

# Declare what your strategy needs.
strategy = build_my_strategy(...)
needs = EngineCapabilities(
    supports_panel=True,
    supports_agent_injection=True,
    supports_param_sweep=True,
)

# Dispatcher picks vectorbt-pro (primary) → event-driven (fallback)
# → backtesting.py (last-resort) based on which satisfies \`needs\`
# and is importable.
engine = dispatch_engine(strategy, needs=needs)
result = engine.run(
    strategy,
    universe="spy_top_50",
    start="2024-01-01",
    end="2026-04-30",
    context={"agents": agent_dispatcher},
)

print(engine.name, result.sharpe, result.max_drawdown)`}
            />
          }
        />
      </section>

      {/* Per-bar agents */}
      <section
        id="agents"
        className="px-6"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <FeatureBreakdown
          eyebrow="Per-bar agents"
          tone="secondary"
          title="Strategies that consult agents on every bar."
          body="The event-driven engine surfaces context['agents'] (the AgentDispatcher). From inside on_bar, call dispatcher.consult(spec_name, inputs, ttl=...). The dispatcher caches by content-hash so the same input doesn't double-pay the LLM."
          bullets={[
            "AgentDispatcher routes through AgentRuntime (cost cap + rate limit apply)",
            "Per-spec TTL cache on (inputs hash) avoids duplicate paid calls",
            "Async consult() variant lets you start the call early and wait at bar close",
            "Failed consults degrade to a configurable fallback signal",
          ]}
          cta={{ label: "Agent dispatcher docs", href: "/docs/backtest/agents" }}
          reverse
          visual={
            <CodeBlock
              filename="agent_strategy.py"
              language="python"
              code={`from aqp.strategies.base import EventDrivenStrategy
from aqp.core.registry import register

@register("MyAgenticAlpha", kind="strategy")
class MyAgenticAlpha(EventDrivenStrategy):
    def on_bar(self, bar, context):
        agents = context["agents"]   # AgentDispatcher

        # Consult the LLM agent once every 5 bars, cached for 1h.
        if bar.idx % 5 == 0:
            verdict = agents.consult(
                spec_name="research.debate_team",
                inputs={"symbol": bar.symbol, "window": bar.lookback_30},
                ttl=3600,
            )
            self.regime = verdict["regime"]

        # Use the agent verdict alongside fast indicators.
        if self.regime == "bull" and bar.rsi_14 > 60:
            self.buy(size=self.position_sizer(bar))
        elif self.regime == "bear" and bar.rsi_14 < 40:
            self.sell()`}
            />
          }
        />
      </section>

      {/* RL injection */}
      <section id="rl" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="RL injection"
            title="Inject a trained RL policy as a portfolio engine."
            subtitle="Engines that opt-in to supports_rl_injection accept context['rl_agent'] — an instance of WeightCentricPipeline. The pipeline runs the FinRL-X four-stage protocol (Selector → Allocator → Timing → Risk overlay) for every step."
          />
          <div className="grid gap-6 lg:grid-cols-2">
            <MotionInView from="left">
              <div
                className="rounded-xl p-6"
                style={{
                  background: "var(--glass-bg)",
                  border: "1px solid var(--glass-border)",
                  backdropFilter: "blur(var(--glass-blur))",
                }}
              >
                <div
                  className="text-xs font-bold uppercase tracking-wider"
                  style={{ color: "var(--accent-secondary)" }}
                >
                  Deployment-consistent
                </div>
                <h3
                  className="mt-2 text-xl font-bold"
                  style={{ color: "var(--text-primary)" }}
                >
                  Same code path: offline → paper → live.
                </h3>
                <p
                  className="mt-3 text-sm leading-relaxed"
                  style={{ color: "var(--text-secondary)" }}
                >
                  Offline backtests via context['rl_agent']. Live paper trading
                  via the same WeightCentricPipeline. Same target weights, same
                  risk overlay, same code path. No silent offline-online drift.
                </p>
                <a
                  href="/product/reinforcement-learning"
                  className="mt-4 inline-flex items-center gap-1 text-sm font-semibold"
                  style={{ color: "var(--accent-secondary)" }}
                >
                  Read more about the FinRL-X pipeline →
                </a>
              </div>
            </MotionInView>
            <MotionInView from="right">
              <CodeBlock
                filename="rl_inject.py"
                language="python"
                code={`from aqp_rl import RLRuntime
from aqp.backtest import dispatch_engine, EngineCapabilities

# Load a trained RL experiment by version_id.
rt = RLRuntime.from_version("9a4f...c1d3")

# Dispatch an engine that supports RL injection.
engine = dispatch_engine(
    strategy=None,           # the policy IS the strategy
    needs=EngineCapabilities(
        supports_panel=True,
        supports_rl_injection=True,
    ),
)

result = engine.run(
    strategy=None,
    universe="spy_top_50",
    start="2024-01-01",
    end="2026-04-30",
    context={"rl_agent": rt.weight_centric_pipeline()},
)

print(result.sharpe, result.max_drawdown)`}
              />
            </MotionInView>
          </div>
        </div>
      </section>

      {/* Optimal control */}
      <section
        id="optimal"
        className="px-6"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <FeatureBreakdown
          eyebrow="Optimal control"
          tone="warn"
          title="JAX-compiled HJB solvers for market making + execution."
          body="Two canonical Hamilton-Jacobi-Bellman problems shipped as reference policies: Avellaneda-Stoikov (2008) for market making and Cartea-Jaimungal-Penalva (2015) for inventory-penalised optimal liquidation. Pure-JAX kernels run on CPU or GPU."
          bullets={[
            "AvellanedaStoikovSolver — closed-form quote skewing with inventory penalty",
            "CarteaJaimungalPenalvaSolver — finite-difference HJB for parent-order slicing",
            "Drive directly via aqp/optimal_control/hjb_solver.py or expose as data.optimal_control.* MCP tools",
            "Use as RL benchmarks (does PPO beat A-S quoting on the same MarketMakingEnv?)",
          ]}
          cta={{ label: "Optimal control docs", href: "/docs/optimal-control" }}
          visual={
            <CodeBlock
              filename="optimal_control.py"
              language="python"
              code={`import jax
from aqp.optimal_control import AvellanedaStoikovSolver

solver = AvellanedaStoikovSolver(
    gamma=0.1,              # risk aversion
    kappa=1.5,              # order-flow intensity
    sigma=0.02,             # mid-quote volatility
    horizon_seconds=3600,
)

# JIT-compile the quote function for the hot path.
quote_fn = jax.jit(solver.optimal_quotes)

# Use inside a hftbacktest LOB strategy or live market-making bot.
bid, ask = quote_fn(
    mid_price=mid,
    inventory=current_inventory,
    time_remaining=t_remaining,
)`}
            />
          }
        />
      </section>

      {/* Wrap-up */}
      <section className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="vectorbt-pro deep integration"
            title="Five modes, walk-forward, IndicatorFactory bridge."
          />
          <FeatureGrid columns={4}>
            <FeatureCard
              icon={Sparkles}
              tone="primary"
              title="signals / orders / optimizer / holding / random"
              body="VectorbtProEngine selects the right mode based on what your strategy emits. Single dispatcher, five behaviours."
            />
            <FeatureCard
              icon={TrendingUp}
              tone="tertiary"
              title="Walk-forward via Splitter"
              body="In-sample / out-of-sample splits with vbt-pro Splitter. Reproducible folds with hash-locked spec versions."
            />
            <FeatureCard
              icon={Zap}
              tone="secondary"
              title="Param sweeps via Param"
              body="Grid + random + Optuna search over Param-typed knobs. Sweep results land in backtest_runs ledger rows."
            />
            <FeatureCard
              icon={Box}
              tone="warn"
              title="IndicatorFactory bridge"
              body="Author an indicator once, surface it in vbt-pro signal generation and the event-driven engine the same way."
            />
          </FeatureGrid>
        </div>
      </section>

      {/* FAQ */}
      <section
        id="faq"
        className="px-6 py-20"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="FAQ"
            title="Backtesting questions"
          />
          <FaqAccordion items={FAQ_ITEMS} />
        </div>
      </section>

      <CallToActionBlock
        eyebrow="Ready to backtest"
        title="From notebook to walk-forward in five minutes."
        subtitle="The Strategies dashboard ships a starter Alpaca paper recipe. Author once; backtest, paper, and deploy through the same spec."
        primaryCta={{ label: "Start free", href: "/signup" }}
        secondaryCta={{ label: "Backtest engines docs", href: "/docs/backtest" }}
      />
    </>
  );
}

const ENGINES = [
  {
    name: "vbtpro",
    module: "aqp/backtest/vbtpro/",
    sweet: "Vectorised signals + portfolio. Five modes. Optuna sweeps.",
    caps: ["supports_panel", "supports_param_sweep", "supports_walk_forward", "supports_indicator_factory"],
  },
  {
    name: "event_driven",
    module: "aqp/backtest/event_driven/",
    sweet: "Bar-by-bar agent + RL injection. The reference for live-replicating strategies.",
    caps: ["supports_event", "supports_agent_injection", "supports_rl_injection"],
  },
  {
    name: "vectorbt_oss",
    module: "aqp/backtest/vectorbt_oss/",
    sweet: "OSS vectorbt fallback when vbt-pro is not licensed.",
    caps: ["supports_panel"],
  },
  {
    name: "backtesting_py",
    module: "aqp/backtest/backtesting_py/",
    sweet: "Quick reference port for community strategies.",
    caps: ["supports_event"],
  },
  {
    name: "hft",
    module: "aqp/backtest/hft.py",
    sweet: "hftbacktest LOB engine. Drives the 5 HFT strategies under aqp/strategies/hft/.",
    caps: ["supports_lob", "supports_options"],
  },
  {
    name: "zvt",
    module: "aqp/backtest/zvt/",
    sweet: "Equity / factor research with ZVT's wide universe.",
    caps: ["supports_panel", "supports_factor_panel"],
  },
  {
    name: "aat",
    module: "aqp/backtest/aat/",
    sweet: "AAT trading framework parity layer.",
    caps: ["supports_event"],
  },
  {
    name: "ccxt_paper",
    module: "aqp/backtest/ccxt_paper/",
    sweet: "Crypto-only paper engine using CCXT historical OHLCV.",
    caps: ["supports_panel", "supports_event"],
  },
  {
    name: "backtrader_bridge",
    module: "aqp/backtest/backtrader/",
    sweet: "Optional bridge to the legacy backtrader engine via Cerebro.",
    caps: ["supports_event"],
  },
];

const EQUITY_CURVE = [
  100, 102, 104, 103, 107, 110, 113, 117, 122, 119, 125, 130, 128, 134, 138,
  142, 139, 145, 148, 152, 150, 156, 162, 168, 175, 180, 178, 183, 188, 192,
  195, 199, 202, 207, 213, 218, 225, 232, 238,
];
const DRAWDOWN_CURVE = [
  0, 0, -0.2, -0.8, -1.5, -1.8, -2.4, -2.9, -3.6, -4.0, -4.3, -4.8, -5.4, -5.9,
  -6.5, -6.5, -6.2, -5.8, -5.4, -5.0, -4.6, -4.2, -3.8, -3.4, -3.0, -2.8,
  -2.6, -2.4, -2.2, -2.0,
];

const FAQ_ITEMS = [
  {
    question: "Which engine does the dispatcher pick by default?",
    answer:
      "vectorbt-pro is the primary engine for panel/vectorised work. The dispatcher falls back to the event-driven engine when your strategy needs per-bar agent or RL injection, hftbacktest for LOB simulation, OSS vectorbt when vbt-pro isn't licensed, and clearly-named fallbacks for ZVT, AAT, backtesting.py, ccxt_paper, and the backtrader bridge.",
  },
  {
    question: "Do agent consult costs hit my LLM budget during a backtest?",
    answer:
      "Yes — every agent consult routes through AgentRuntime which enforces the AgentSpec's cost_budget_usd. The AgentDispatcher's per-spec TTL cache de-duplicates identical (inputs hash) calls so a 5-year backtest doesn't pay 5×252 separate LLM calls per agent per day; only the unique inputs do.",
  },
  {
    question: "Can I plug in a custom backtest engine?",
    answer:
      "Yes. Subclass BaseBacktestEngine, declare an EngineCapabilities class attribute, decorate with @register('YourEngine'). Add a shortcut to aqp/backtest/runner.py::_ENGINE_SHORTCUTS and the dispatcher will consider it on the next request.",
  },
  {
    question: "How do walk-forward splits work with vbt-pro?",
    answer:
      "VectorbtProEngine uses vbt-pro's Splitter to define folds (rolling, expanding, or custom). Each fold runs its own param-sweep + out-of-sample evaluation. Results aggregate into a single backtest_runs ledger row with per-fold metrics — replay any fold via the spec_version_id.",
  },
  {
    question: "Can I run a backtest from the dashboard without writing code?",
    answer:
      "Yes. The Strategies dashboard ships a starter Alpaca paper-trading recipe (the StrategyForm). Pick a universe, indicators, signals, and portfolio model — backtest, paper-run, or deploy through the same hash-locked spec. Code is the escape hatch, not the default path.",
  },
];
