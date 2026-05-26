import type { Metadata } from "next";

import { CodeBlock } from "@/components/marketing/CodeBlock";
import { LearnArticleLayout } from "@/components/marketing/LearnArticleLayout";

export const metadata: Metadata = {
  title: "FinRL-X four-stage portfolio pipeline",
  description:
    "Selector → Allocator → Timing → Risk overlay. The four pure functions that close the offline-to-live RL gap and give you a deployment-consistent portfolio policy.",
};

export const dynamic = "force-static";
export const revalidate = 86400;

export default function FinRLXPipelinePage() {
  return (
    <LearnArticleLayout
      eyebrow="RL · 9 min read"
      title="The FinRL-X four-stage portfolio pipeline"
      readMinutes={9}
      dateLine="Updated May 2026"
      toc={[
        { id: "the-contract", label: "The contract" },
        { id: "f_s", label: "f_S — Selector" },
        { id: "f_a", label: "f_A — Allocator" },
        { id: "f_t", label: "f_T — Timing adjuster" },
        { id: "f_r", label: "f_R — Risk overlay" },
        { id: "deployment", label: "Deployment-consistent by construction" },
        { id: "engine-injection", label: "Engine injection contract" },
        { id: "when-to-skip", label: "When to skip stages" },
      ]}
      related={[
        {
          href: "/learn/reinforcement-learning-in-finance",
          title: "RL in finance",
          category: "RL",
        },
        {
          href: "/product/reinforcement-learning",
          title: "RL product page",
          category: "Product",
        },
        {
          href: "/product/backtesting#rl",
          title: "Backtesting + RL injection",
          category: "Product",
        },
      ]}
      cta={{
        title: "Inject an RL policy",
        body: "AQP's backtest engines that opt-in to supports_rl_injection accept a WeightCentricPipeline via context['rl_agent'].",
        label: "Open the RL Lab",
        href: "/signup",
      }}
    >
      <p
        className="rounded-lg p-4 text-base"
        style={{
          background: "rgba(167,139,250,0.06)",
          border: "1px solid rgba(167,139,250,0.3)",
          color: "var(--text-primary)",
        }}
      >
        <strong>TL;DR.</strong> FinRL-X is the four-stage protocol that
        guarantees a portfolio RL policy produces the <em>same</em> target
        weights in an offline backtest and in a live broker. Selector,
        Allocator, Timing adjuster, Risk overlay — four pure functions, one
        code path, no offline-online drift.
      </p>

      <h2 id="the-contract">The contract</h2>
      <p>
        The FinRL-X pipeline ships in <code>aqp_rl</code> as the{" "}
        <code>WeightCentricPipeline</code> class. It composes four stages:
      </p>
      <ul>
        <li>
          <code>f_S</code> — Selector (universe restriction)
        </li>
        <li>
          <code>f_A</code> — Allocator (RL policy emits raw weights)
        </li>
        <li>
          <code>f_T</code> — Timing adjuster (slippage / latency / smoothing)
        </li>
        <li>
          <code>f_R</code> — Risk overlay (per-name caps, turnover caps)
        </li>
      </ul>
      <p>
        Each stage is a <strong>pure function</strong> of its inputs. No
        hidden global state, no time-dependent randomness without an
        explicit seed. The same inputs always produce the same outputs.
      </p>

      <h2 id="f_s">f_S — Selector</h2>
      <p>
        The Selector restricts the universe before the policy sees it. Why
        not let the policy do its own selection? Three reasons:
      </p>
      <ul>
        <li>
          <strong>Action space size.</strong> A 3,000-name universe is a
          3,000-dim action space. Most policy backbones blow up at that
          scale. Selecting down to top-200 by score before the allocator
          makes the action space manageable.
        </li>
        <li>
          <strong>Compliance.</strong> The Selector is the natural place to
          enforce a "do not trade list", sector exclusions, ESG screens.
          Doing it here keeps the policy from learning around the
          constraint.
        </li>
        <li>
          <strong>Regime-awareness.</strong> Some Selectors filter by
          regime (only growth names in growth regimes; only defensives in
          contraction). The Selector is the right home for that logic, not
          the policy.
        </li>
      </ul>
      <p>
        Concrete shipped Selectors: top-k by alpha score, sector cap,
        regime-conditioned filter, do-not-trade list, custom score
        threshold. Compose them via <code>CompositeSelector</code>.
      </p>

      <h2 id="f_a">f_A — Allocator</h2>
      <p>
        The Allocator is the RL policy itself. It takes the restricted
        universe and the observation (features for each name) and emits raw
        weights. The exact shape of the output depends on the action space:
      </p>
      <ul>
        <li>
          <code>ContinuousActionSpace</code> — fractional weights in
          [-1, 1] per name. Use for long/short relative-value strategies.
        </li>
        <li>
          <code>SoftmaxActionSpace</code> — weights sum to 1, long-only.
          Use for vanilla long-only portfolios.
        </li>
        <li>
          <code>IntegerSharesActionSpace</code> — discrete integer share
          deltas. Use when you want the policy to reason about discrete
          orders directly.
        </li>
        <li>
          <code>TargetPositionActionSpace</code> — target absolute position
          per name. Use when you have a tight margin profile and need
          explicit position control.
        </li>
      </ul>

      <h2 id="f_t">f_T — Timing adjuster</h2>
      <p>
        The Timing adjuster translates a "target weight as of close" into
        an "executable weight given the next session's open price, slippage
        model, and any latency budget you want to enforce in backtest."
        This is where the backtest matches reality.
      </p>
      <p>
        Timing models often look like: <code>w_executed = clip(w_target,
        max_turnover) ⊕ slippage_model(volume, σ) ⊕ latency(t)</code>. The
        crucial property: the <em>same</em> Timing adjuster is invoked in
        live paper trading and in offline backtests. If the live broker
        rounds to lot sizes, the backtest's Timing adjuster rounds to lot
        sizes.
      </p>

      <h2 id="f_r">f_R — Risk overlay</h2>
      <p>
        The Risk overlay enforces per-name caps, gross-exposure caps,
        turnover caps, sector caps — anything that needs to be true after
        Timing but before broker. AQP composes the existing{" "}
        <code>RiskLimits</code> and{" "}
        <code>TargetWeightsRebalancer</code> classes so the offline
        backtest and the live paper-trading session produce identical
        post-overlay weights.
      </p>
      <p>
        A canonical Risk overlay enforces: max 10% per name, max 30%
        per sector, max 50% gross, max 200% daily turnover. The overlay
        is composable; you can add a "no rebalance during the first hour
        of the session" rule by registering an additional check.
      </p>

      <h2 id="deployment">Deployment-consistent by construction</h2>
      <p>
        The whole pipeline is a method on <code>WeightCentricPipeline</code>:
      </p>
      <CodeBlock
        filename="weight_centric_pipeline.py"
        language="python"
        code={`class WeightCentricPipeline:
    def __init__(
        self,
        selector: BaseSelector,
        allocator: BaseRLAgent,
        timing: BaseTimingAdjuster,
        risk_overlay: BaseRiskOverlay,
    ):
        self.f_S = selector
        self.f_A = allocator
        self.f_T = timing
        self.f_R = risk_overlay

    def step(self, observation, context) -> TargetWeights:
        # f_S: restrict the universe
        restricted = self.f_S(observation.universe, context)

        # f_A: RL policy emits raw weights
        raw_weights = self.f_A.predict(observation.for_universe(restricted))

        # f_T: apply slippage / latency / smoothing
        executable = self.f_T(raw_weights, observation.price_action, context)

        # f_R: cap per-name + gross + turnover
        return self.f_R(executable, context.portfolio_state)`}
      />

      <p>
        Now look at how the offline backtest engine invokes it:
      </p>

      <CodeBlock
        filename="offline_engine.py"
        language="python"
        code={`# Inside the event-driven backtest engine's on_bar
def on_bar(self, bar, context):
    rl_agent = context["rl_agent"]   # WeightCentricPipeline instance
    target = rl_agent.step(
        observation=self.observation_at(bar),
        context=context,
    )
    self.rebalance_to(target)`}
      />

      <p>
        And how the live paper-trading loop invokes it:
      </p>

      <CodeBlock
        filename="live_paper.py"
        language="python"
        code={`# Inside aqp.trading.session loop
async def on_bar(self, bar):
    target = self.pipeline.step(
        observation=self.observation_at(bar),
        context=self.context,
    )
    await self.broker.rebalance_to(target)`}
      />

      <p>
        Same <code>WeightCentricPipeline</code>, same four functions, same
        target weights. The path from "policy weights" to "broker order"
        is one code path, exercised identically in offline tests and live
        runs. That is what "deployment-consistent" means.
      </p>

      <h2 id="engine-injection">Engine injection contract</h2>
      <p>
        Backtest engines opt in to RL injection by setting{" "}
        <code>EngineCapabilities.supports_rl_injection=True</code>. The
        runner passes the <code>WeightCentricPipeline</code> through{" "}
        <code>context['rl_agent']</code>. Strategies can ignore it (engines
        that don't opt in get a None) or consume it (engines that do opt in
        treat the RL pipeline as their position model).
      </p>
      <p>
        The contract scales: each engine that opts in is choosing to honour
        the same <code>WeightCentricPipeline.step()</code> semantics. That
        means a new engine can be added to the cascade and immediately
        inherit RL-policy compatibility without rewriting the policy.
      </p>

      <h2 id="when-to-skip">When to skip stages</h2>
      <p>
        Three of the four stages can default to identity functions. The
        Allocator (f_A) is mandatory — it IS the policy. The others have
        sensible defaults:
      </p>
      <ul>
        <li>
          <strong>f_S = identity:</strong> the policy sees the full
          universe. Fine for small universes (under 100 names) and
          research-only policies.
        </li>
        <li>
          <strong>f_T = identity:</strong> no slippage, no latency, no
          smoothing. Fine for hourly+ holding periods on liquid universes.
        </li>
        <li>
          <strong>f_R = identity:</strong> no caps. Reasonable for
          research; <strong>not</strong> reasonable for live capital. The
          first thing to wire in before going live is a Risk overlay.
        </li>
      </ul>
      <p>
        The progression is typical: start research-only with three
        identities; add a Risk overlay for paper trading; add a Timing
        adjuster that matches your broker's slippage profile; add a
        Selector when the universe outgrows the policy's action space. At
        every step, the offline backtest and the live system call the same
        four functions.
      </p>
    </LearnArticleLayout>
  );
}
