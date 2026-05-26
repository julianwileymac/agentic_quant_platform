import type { Metadata } from "next";

import { CodeBlock } from "@/components/marketing/CodeBlock";
import { LearnArticleLayout } from "@/components/marketing/LearnArticleLayout";
import { MetricSparkline } from "@/components/marketing/MetricSparkline";
import { RLLoopDiagram } from "@/components/marketing/illustrations/RLLoopDiagram";

export const metadata: Metadata = {
  title: "Reinforcement learning in finance",
  description:
    "From the Markowitz objective to deployment-consistent weight pipelines. Why offline-online drift is the boss-fight, and how FinRL-X closes it.",
};

export const dynamic = "force-static";
export const revalidate = 86400;

export default function RLInFinancePage() {
  return (
    <LearnArticleLayout
      eyebrow="RL · 12 min read"
      title="Reinforcement learning in finance"
      readMinutes={12}
      dateLine="Updated May 2026"
      toc={[
        { id: "why-rl", label: "Why RL for portfolios?" },
        { id: "the-objectives", label: "Three objectives, one policy" },
        { id: "the-boss-fight", label: "The boss-fight: offline-online drift" },
        { id: "deployment-consistent", label: "Deployment-consistent pipelines" },
        { id: "frameworks", label: "Six frameworks, one adapter API" },
        { id: "advantage-estimators", label: "Advantage estimators that don't lie" },
        { id: "evaluation", label: "Evaluation beyond Sharpe" },
        { id: "trajectories", label: "Trajectories as data" },
        { id: "where-it-fails", label: "Where it fails" },
      ]}
      related={[
        {
          href: "/learn/finrl-x-portfolio-pipeline",
          title: "FinRL-X four-stage pipeline",
          category: "RL",
        },
        {
          href: "/product/reinforcement-learning",
          title: "RL product page",
          category: "Product",
        },
        {
          href: "/learn/hash-locked-specs",
          title: "Hash-locked specs",
          category: "Agentic",
        },
      ]}
      cta={{
        title: "Open the RL Lab",
        body: "AQP's RL Lab gives you a visual builder for envs, rewards, observations, actions — backed by hash-locked specs and Iceberg trajectories.",
        label: "Try it free",
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
        <strong>TL;DR.</strong> RL is the obvious tool for sequential
        decision-making under uncertainty. Portfolio allocation, market
        making, optimal execution are all sequential decision problems. The
        boss-fight isn't training — it's making sure the policy that worked
        in the offline backtest produces the same target weights when it hits
        the live broker. AQP solves this with the FinRL-X four-stage
        weight-centric pipeline.
      </p>

      <h2 id="why-rl">Why RL for portfolios?</h2>
      <p>
        Traditional portfolio construction (Markowitz mean-variance,
        risk-parity, Black-Litterman) solves a one-shot optimisation: given
        expected returns and a covariance matrix, find the weights that
        maximise utility. That is a fine answer to a fine question. It is
        not the question portfolio managers actually face.
      </p>
      <p>
        The real question is sequential: <em>given today's information, what
        weights should I hold? And tomorrow? And given the transaction cost
        of getting there?</em> The optimal solution depends on the dynamics
        of returns, the path of volatility, and the cost of turning over the
        book — all of which RL can natively model and one-shot optimisation
        cannot.
      </p>

      <div className="my-8">
        <div
          className="overflow-hidden rounded-xl p-2"
          style={{
            background: "var(--glass-bg)",
            border: "1px solid var(--glass-border)",
            backdropFilter: "blur(var(--glass-blur))",
          }}
        >
          <RLLoopDiagram />
        </div>
      </div>

      <h2 id="the-objectives">Three objectives, one policy</h2>
      <p>
        Most RL-for-finance projects fail because they treat the reward
        function as an afterthought. The reward function <strong>is</strong>{" "}
        the objective. Get it wrong and the policy converges to a useless
        local optimum. Three reward families do most of the work in practice:
      </p>
      <ul>
        <li>
          <strong>Log-return + drawdown penalty.</strong> The straightforward
          "go up, don't go down too hard" reward. Use it for long-only
          equity allocation when you don't have a strong utility theory.
        </li>
        <li>
          <strong>Differential Sharpe.</strong> Reward the marginal
          contribution to Sharpe at each step. Avoids the trap of converging
          to a high-volatility policy that happens to have positive total
          return.
        </li>
        <li>
          <strong>Constrained max-utility.</strong> Reward a CRRA utility
          function with a Lagrangian penalty on tracking error / turnover /
          per-name exposure. Use when you have explicit constraints
          (compliance, mandate, prime-broker margin).
        </li>
      </ul>
      <p>
        AQP's <code>CompositeReward</code> composes weighted terms with
        per-step decomposition, so you can see which term is driving the
        gradient at every step. That is the difference between a debuggable
        RL run and a black-box one.
      </p>

      <h2 id="the-boss-fight">The boss-fight: offline-online drift</h2>
      <p>
        Train an RL policy on five years of backtest data. The policy looks
        amazing. You deploy it to paper trading. The Sharpe collapses by 60%
        in two weeks. Why?
      </p>
      <p>
        Three possible causes, all of them about <em>drift</em> between
        offline and online code paths:
      </p>
      <ul>
        <li>
          <strong>Different feature engineering.</strong> The backtest
          computed stockstats features one way; the live system computes
          them another. The policy is consuming slightly different
          observations.
        </li>
        <li>
          <strong>Different action interpretation.</strong> The backtest
          assumed continuous fractional shares; the broker rounds to integer
          shares plus a lot size. The actual position taken doesn't match
          the policy's output.
        </li>
        <li>
          <strong>Different risk overlay.</strong> The backtest had no
          turnover cap; the live system enforces one via the prime-broker
          rules. Same target weights, different realised exposures.
        </li>
      </ul>
      <p>
        Each one is a small drift. Compound three small drifts and you have
        a different system.
      </p>

      <h2 id="deployment-consistent">Deployment-consistent pipelines</h2>
      <p>
        The FinRL-X four-stage weight-centric pipeline (<code>f_S → f_A →
        f_T → f_R</code>) is the structural fix. Each stage is a{" "}
        <em>pure function</em> of its inputs — no hidden global state, no
        time-dependent randomness without an explicit seed — and the
        offline backtest and live broker call the <strong>same</strong> four
        functions:
      </p>
      <ul>
        <li>
          <code>f_S</code> — Selector. Universe restriction (top-k by score,
          regime-aware filter, sector exclusion).
        </li>
        <li>
          <code>f_A</code> — Allocator. The RL policy emits raw weights for
          the selected universe.
        </li>
        <li>
          <code>f_T</code> — Timing adjuster. Applies slippage, latency,
          smoothing.
        </li>
        <li>
          <code>f_R</code> — Risk overlay.{" "}
          <code>RiskLimits</code> + <code>TargetWeightsRebalancer</code> cap
          per-name exposure and turnover.
        </li>
      </ul>
      <p>
        Offline backtest engines opt in by flipping{" "}
        <code>EngineCapabilities.supports_rl_injection=True</code>; live
        paper trading routes through the same{" "}
        <code>WeightCentricPipeline</code> via{" "}
        <code>context['rl_agent']</code>. Same code, same target weights, no
        silent drift. Read the deep-dive at{" "}
        <a href="/learn/finrl-x-portfolio-pipeline">
          /learn/finrl-x-portfolio-pipeline
        </a>
        .
      </p>

      <h2 id="frameworks">Six frameworks, one adapter API</h2>
      <p>
        AQP wraps six RL frameworks behind a uniform <code>BaseRLAgent</code>{" "}
        ABC. You pick the framework you know and the platform handles the
        plumbing:
      </p>
      <ul>
        <li>
          <code>SB3Adapter</code> — PPO / SAC / TD3 / DDPG / DQN +
          sb3-contrib (RecurrentPPO / QRDQN / MaskablePPO / ARS / TQC /
          TRPO).
        </li>
        <li>
          <code>ElegantRLAdapter</code> — FinRL parity backend (optional
          dep).
        </li>
        <li>
          <code>RayRLlibAdapter</code> — distributed multi-agent training.
        </li>
        <li>
          <code>CleanRLAdapter</code> — single-file reference baselines.
        </li>
        <li>
          <code>LLMHybridAgent</code> — FinRobot-style LLM advisor blended
          with an RL backbone (LLM calls routed through{" "}
          <code>router_complete</code>).
        </li>
        <li>
          <code>NeMoRLAdapter</code> — heavy-dep escape hatch (Megatron).
        </li>
      </ul>
      <p>
        New backbones plug in via <code>TimeSeriesEncoder</code>: Transformer
        for medium sequences, Recurrent (LSTM / GRU) for long memory,
        Autoencoder for high-dim observations, PatchTST for long-horizon
        patch tokenisation. All four wrap existing <code>aqp_models</code>{" "}
        modules so the policy network and the offline ML stack share one
        source of truth.
      </p>

      <h2 id="advantage-estimators">Advantage estimators that don't lie</h2>
      <p>
        The advantage estimator is the difference between the actual reward
        and the expected reward. The choice matters more than people think,
        especially in finance where the variance of returns drowns out the
        signal at short horizons:
      </p>
      <ul>
        <li>
          <code>GAEAdvantage</code> — Generalised Advantage Estimation, the
          SB3 default. Bias-variance trade-off via <code>λ</code>.
        </li>
        <li>
          <code>GRPOAdvantage</code> — Group-relative, no critic. Useful
          when the critic is hard to train (sparse rewards, weak baseline).
          DeepSeek R1 / NeMo-RL parity.
        </li>
        <li>
          <code>ReinforcePlusPlusAdvantage</code> — leave-one-out cohort
          baseline + decoupled global normalisation. NeMo-RL port.
        </li>
      </ul>

      <h2 id="evaluation">Evaluation beyond Sharpe</h2>
      <p>
        Sharpe is one number. RL policies need a multi-axis view because
        their failure modes are multi-axis. PRUDEX-Compass is AQP's
        17-measure evaluation framework across six axes:
      </p>
      <ul>
        <li>
          <strong>Profitability:</strong> total_return, sharpe, sortino,
          calmar, cumulative_return.
        </li>
        <li>
          <strong>Risk-control:</strong> max_drawdown, vol, downside_vol,
          ulcer_index, var_99.
        </li>
        <li>
          <strong>Universality:</strong> cross_dataset_sharpe_mean,
          generalisation_gap.
        </li>
        <li>
          <strong>Diversification:</strong> portfolio_weight_entropy,
          herfindahl.
        </li>
        <li>
          <strong>Explainability:</strong> regime_conditioned_sharpe,
          exposure_drift, decision_attribution.
        </li>
        <li>
          <strong>X-tra:</strong> regime-stratified evaluation, stress-test
          windows.
        </li>
      </ul>

      <div className="my-8 grid grid-cols-2 gap-3">
        <MetricSparkline
          data={REWARD}
          label="Reward"
          value="+482"
          tone="tertiary"
          height={72}
          showDelta={false}
        />
        <MetricSparkline
          data={SHARPE}
          label="Sharpe"
          value="2.18"
          tone="primary"
          height={72}
          showDelta={false}
        />
        <MetricSparkline
          data={DD}
          label="Max DD"
          value="-4.2%"
          tone="neg"
          height={72}
          showDelta={false}
        />
        <MetricSparkline
          data={ENTROPY}
          label="Weight entropy"
          value="0.78"
          tone="secondary"
          height={72}
          showDelta={false}
        />
      </div>

      <h2 id="trajectories">Trajectories as data</h2>
      <p>
        AQP persists every env step to Iceberg via the{" "}
        <code>IcebergTrajectoryStore</code>. Four tables —
        <code>rl.trajectories</code> (every step),{" "}
        <code>rl.equity_curves</code> (portfolio value + drawdown),{" "}
        <code>rl.action_logs</code> (action vectors), and{" "}
        <code>rl.reward_decomposition</code> (per-term reward attribution)
        — are queryable from DuckDB or the RL Lab UI.
      </p>
      <p>
        Treating trajectories as first-class data unlocks two important
        capabilities. First, you can re-evaluate any historic policy against
        any new data window with no re-training. Second, you can audit
        <em>why</em> a policy made a decision at a specific step:
        action_logs + reward_decomposition give you the input vector and the
        per-term reward attribution side-by-side.
      </p>

      <CodeBlock
        filename="rl_train_replay.py"
        language="python"
        code={`from aqp_rl import RLRuntime, RLExperimentSpec

# Load a spec; the RLExperimentSpec is hash-locked.
spec = RLExperimentSpec.from_yaml(
    "configs/rl/momentum_ppo_v3.yaml",
)

rt = RLRuntime(spec)

# Train: writes rl_runs ledger row + Iceberg trajectories.
run = rt.train(timesteps=2_000_000, eval_every=50_000)

# Evaluate against out-of-sample data.
metrics = rt.evaluate(window=("2026-01-01", "2026-04-30"))

# Replay the SAME policy against last month.
old_rt = RLRuntime.from_version(run.spec_version_id)
diff = old_rt.replay(window=last_month, store_to=run.run_id)`}
      />

      <h2 id="where-it-fails">Where RL-for-finance fails</h2>
      <p>
        Three failure modes account for most of the bad RL projects in
        production:
      </p>
      <ul>
        <li>
          <strong>Reward hacking.</strong> The policy finds a way to
          maximise the reward function that does not maximise the actual
          objective. Mitigate by composing reward terms with explicit
          penalties on the failure modes you're worried about.
        </li>
        <li>
          <strong>Non-stationarity.</strong> The market regime that
          generated the training data isn't the regime the policy is
          deployed into. Mitigate by stratifying evaluation across regimes
          and including a regime feature in the observation (see{" "}
          <code>RegimeAwareObservation</code>).
        </li>
        <li>
          <strong>Offline-online drift.</strong> The boss-fight (see above).
          Mitigate by using the deployment-consistent pipeline as the only
          path from policy to broker.
        </li>
      </ul>
      <p>
        RL is not magic. It is a powerful tool for sequential
        decision-making that requires the engineer to do the work of
        encoding the right objective and respecting the deployment
        boundary. AQP's job is to make the boring parts (training
        orchestration, trajectory persistence, replay, evaluation, the
        pipeline) automatic — so you can focus on the parts that are
        actually hard.
      </p>
    </LearnArticleLayout>
  );
}

const REWARD = [
  -20, -15, -8, -2, 8, 16, 22, 30, 42, 58, 80, 110, 145, 180, 215, 250, 290,
  330, 370, 420, 460, 482,
];
const SHARPE = [
  0.8, 0.9, 1.0, 0.95, 1.1, 1.2, 1.35, 1.5, 1.65, 1.7, 1.78, 1.85, 1.9, 2.0,
  2.05, 2.1, 2.12, 2.15, 2.16, 2.17, 2.18,
];
const DD = [
  0, -0.5, -1.2, -2.1, -3.4, -4.8, -5.4, -5.1, -4.7, -4.5, -4.3, -4.2, -4.3,
  -4.2, -4.2, -4.2, -4.2,
];
const ENTROPY = [
  0.4, 0.45, 0.5, 0.55, 0.6, 0.62, 0.65, 0.68, 0.7, 0.72, 0.74, 0.75, 0.76,
  0.77, 0.77, 0.78,
];
