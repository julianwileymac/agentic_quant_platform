import type { Metadata } from "next";
import {
  Activity,
  Award,
  Binary,
  BookOpen,
  Boxes,
  BrainCircuit,
  CheckCircle,
  CircleDot,
  Compass,
  Database,
  GitBranch,
  LayoutGrid,
  Network,
  ScrollText,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Workflow,
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
import { RLLoopDiagram } from "@/components/marketing/illustrations/RLLoopDiagram";
import { SectionHeader } from "@/components/marketing/SectionHeader";
import { StatStrip } from "@/components/marketing/StatStrip";

export const metadata: Metadata = {
  title: "Reinforcement Learning",
  description:
    "RLRuntime with hash-locked experiments, six framework adapters, four policy backbones, native REINFORCE++ / GRPO / GAE advantage estimators, and the FinRL-X four-stage weight-centric portfolio pipeline.",
};

export const dynamic = "force-static";
export const revalidate = 3600;

const NAV_ITEMS = [
  { id: "overview", label: "Overview" },
  { id: "runtime", label: "RLRuntime" },
  { id: "components", label: "Component metaclass" },
  { id: "pipeline", label: "FinRL-X pipeline" },
  { id: "frameworks", label: "Frameworks" },
  { id: "evaluation", label: "PRUDEX-Compass" },
  { id: "iceberg", label: "Trajectory store" },
  { id: "faq", label: "FAQ" },
];

export default function RLPage() {
  return (
    <>
      <Hero
        eyebrow="Product · Reinforcement Learning"
        eyebrowIcon={Sparkles}
        title="Deployment-consistent RL for portfolio allocation."
        titleHighlight="Deployment-consistent RL"
        subtitle="The FinRL-X four-stage pipeline (Selector → Allocator → Timing → Risk overlay) produces identical target-weight semantics in the offline backtest and the live broker. Six framework adapters. Four policy backbones. Three native advantage estimators. Iceberg-backed trajectories."
        primaryCta={{ label: "Open the RL Lab", href: "/signup" }}
        secondaryCta={{ label: "RL framework docs", href: "/docs/rl" }}
        illustration={
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
        }
      />

      <ProductNav items={NAV_ITEMS} />

      <StatStrip
        stats={[
          { value: 6, label: "Framework adapters", tone: "primary" },
          { value: 4, label: "Policy backbones", tone: "secondary" },
          { value: 17, label: "PRUDEX measures", tone: "tertiary" },
          { value: 4, label: "Iceberg trajectory tables", tone: "primary" },
        ]}
      />

      {/* Overview */}
      <section id="overview" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Overview"
            title="Why AQP's RL stack is different"
            subtitle="Most RL libraries treat the env, the policy, the reward, and the trajectory store as the user's problem. AQP treats them as a typed metaclass-registered component graph."
          />
          <FeatureGrid columns={3}>
            <FeatureCard
              icon={BrainCircuit}
              tone="primary"
              title="Metaclass registry"
              body="Every env, observation, action, reward, termination, policy, agent, data pipeline, ensembler, experiment, and trajectory store auto-registers through RLComponent."
            />
            <FeatureCard
              icon={GitBranch}
              tone="secondary"
              title="Hash-locked experiments"
              body="RLExperimentSpec snapshots an immutable rl_experiment_versions row. Same content → same version. Replay with new data, same hyperparameters."
            />
            <FeatureCard
              icon={Network}
              tone="tertiary"
              title="Deployment-consistent"
              body="FinRL-X four-stage pipeline produces the same target weights in offline backtests and live broker execution. No silent drift."
            />
            <FeatureCard
              icon={Database}
              tone="primary"
              title="Iceberg trajectories"
              body="Four Iceberg tables (trajectories, equity_curves, action_logs, reward_decomposition) — queryable from DuckDB or the RL Lab UI."
            />
            <FeatureCard
              icon={LayoutGrid}
              tone="warn"
              title="Compose, don't fork"
              body="StackedObservationBuilder + CompositeReward let you compose feature blocks and per-term reward weights without subclassing."
            />
            <FeatureCard
              icon={Compass}
              tone="secondary"
              title="PRUDEX-Compass eval"
              body="17-measure evaluation across six axes (Profitability, Risk-control, Universality, Diversification, Explainability, X-tra)."
            />
          </FeatureGrid>
        </div>
      </section>

      {/* RLRuntime */}
      <section
        id="runtime"
        className="px-6"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <FeatureBreakdown
          eyebrow="RLRuntime"
          tone="primary"
          title="One typed runtime for train / evaluate / replay / paper / walk-forward."
          body="All RL operations route through RLRuntime. Celery tasks (aqp_rl.tasks.rl_tasks) and the FastAPI route (aqp_rl.api.routes.rl) wrap it — they never call agent.train directly. Same content → same version. Replay with new data is a deterministic operation."
          bullets={[
            "rl_runs ledger row written BEFORE training begins",
            "Replay across data is a first-class operation — old version stays for audit",
            "MLflow autolog hooks for hyperparameters, metrics, artifacts",
            "Halt-aware: kill-switch fans out to /rl/halt-all",
          ]}
          cta={{ label: "RL framework docs", href: "/docs/rl/framework" }}
          visual={
            <CodeBlock
              filename="train_replay.py"
              language="python"
              code={`from aqp_rl import RLRuntime, RLExperimentSpec

spec = RLExperimentSpec.from_yaml(
    "configs/rl/momentum_ppo_v3.yaml",
)

rt = RLRuntime(spec)

# Train: snapshots immutable rl_experiment_versions row,
# writes rl_runs ledger row, streams progress frames, persists
# to Iceberg trajectory store.
run = rt.train(
    timesteps=2_000_000,
    eval_every=50_000,
)

# Evaluate the snapshotted policy on out-of-sample data.
metrics = rt.evaluate(window=("2026-01-01", "2026-04-30"))

# Replay any historic version against new data.
old_rt = RLRuntime.from_version(run.spec_version_id)
diff = old_rt.replay(window=last_month, store_to=run.run_id)`}
            />
          }
        />
      </section>

      {/* Component metaclass */}
      <section id="components" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Composable component graph"
            title="Eleven component kinds, all metaclass-registered"
            subtitle="Set rl_kind + rl_alias on a subclass. The RLComponent metaclass calls @register automatically. Mix-and-match without forking, browse by alias in the lab."
          />
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {COMPONENT_KINDS.map((kind, i) => (
              <MotionInView key={kind.label} delay={i * 0.04}>
                <div
                  className="rounded-lg p-4"
                  style={{
                    background: "var(--glass-bg)",
                    border: "1px solid var(--glass-border)",
                    backdropFilter: "blur(var(--glass-blur))",
                  }}
                >
                  <div className="flex items-center gap-2">
                    <CircleDot size={14} style={{ color: "var(--accent-primary)" }} />
                    <code
                      className="text-xs font-bold"
                      style={{ color: "var(--accent-primary)" }}
                    >
                      {kind.label}
                    </code>
                  </div>
                  <div
                    className="mt-2 text-sm"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {kind.title}
                  </div>
                  <div
                    className="mt-1 text-xs leading-snug"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {kind.sub}
                  </div>
                </div>
              </MotionInView>
            ))}
          </div>
        </div>
      </section>

      {/* FinRL-X pipeline */}
      <section
        id="pipeline"
        className="px-6"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <FeatureBreakdown
          eyebrow="FinRL-X pipeline"
          tone="secondary"
          title="Selector → Allocator → Timing → Risk overlay. Four pure functions."
          body="The weight-centric protocol that guarantees identical target-weight semantics across offline backtesting and live broker execution. Each stage is a pure function of its inputs — no hidden global state, no time-dependent randomness without an explicit seed."
          bullets={[
            "f_S: Selector — universe restriction (top-k by score, regime-aware filter)",
            "f_A: Allocator — RL policy emits raw weights",
            "f_T: Timing — applies slippage, latency, smoothing",
            "f_R: Risk overlay — RiskLimits + TargetWeightsRebalancer",
          ]}
          cta={{
            label: "FinRL-X pipeline deep-dive",
            href: "/learn/finrl-x-portfolio-pipeline",
          }}
          reverse
          visual={
            <div className="space-y-4">
              <div
                className="rounded-xl p-6"
                style={{
                  background: "var(--glass-bg-strong)",
                  border: "1px solid var(--glass-border-strong)",
                  backdropFilter: "blur(var(--glass-blur))",
                }}
              >
                <div className="grid grid-cols-1 gap-3">
                  {PIPELINE_STAGES.map((stage) => (
                    <div
                      key={stage.alias}
                      className="flex items-start gap-3 rounded-lg p-3"
                      style={{
                        background: "var(--bg-elevated)",
                        border: "1px solid var(--border-default)",
                      }}
                    >
                      <code
                        className="rounded px-2 py-0.5 font-mono text-sm font-bold"
                        style={{
                          background: "rgba(167,139,250,0.15)",
                          color: "#a78bfa",
                        }}
                      >
                        {stage.alias}
                      </code>
                      <div>
                        <div
                          className="text-sm font-semibold"
                          style={{ color: "var(--text-primary)" }}
                        >
                          {stage.title}
                        </div>
                        <div
                          className="mt-0.5 text-xs leading-snug"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {stage.body}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div
                className="rounded-lg p-3 text-xs leading-relaxed"
                style={{
                  background: "rgba(16,185,129,0.06)",
                  border: "1px solid rgba(16,185,129,0.3)",
                  color: "var(--text-primary)",
                }}
              >
                <span style={{ color: "var(--pos-fg)", fontWeight: 700 }}>
                  Deployment-consistent:
                </span>{" "}
                same code path on offline backtests via context['rl_agent'] and
                live brokers via the WeightCentricPipeline.
              </div>
            </div>
          }
        />
      </section>

      {/* Frameworks + backbones + advantages */}
      <section id="frameworks" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Choose your weapon"
            title="Six framework adapters · Four policy backbones · Three native advantage estimators"
          />
          <div className="grid gap-6 lg:grid-cols-3">
            <MotionInView>
              <FrameworkColumn
                heading="Framework adapters"
                items={[
                  { name: "SB3Adapter", sub: "PPO / SAC / TD3 / DDPG / DQN + sb3-contrib (RecurrentPPO / QRDQN / MaskablePPO / ARS / TQC / TRPO)" },
                  { name: "ElegantRLAdapter", sub: "FinRL parity backend (optional dep)" },
                  { name: "RayRLlibAdapter", sub: "Distributed multi-agent training" },
                  { name: "CleanRLAdapter", sub: "Single-file reference baselines" },
                  { name: "LLMHybridAgent", sub: "FinRobot-style LLM advisor + RL backbone" },
                  { name: "NeMoRLAdapter", sub: "Heavy-dep escape hatch (Megatron)" },
                ]}
              />
            </MotionInView>
            <MotionInView delay={0.1}>
              <FrameworkColumn
                heading="Policy backbones"
                items={[
                  { name: "TransformerBackbone", sub: "Default for medium sequences (30-100 bars)" },
                  { name: "RecurrentBackbone", sub: "LSTM / GRU / vanilla RNN cell" },
                  { name: "AutoencoderBackbone", sub: "High-dim observation (1000+ features) compression" },
                  { name: "PatchTSTBackbone", sub: "Patch-tokenised transformer for long-horizon (252+ bars)" },
                ]}
                footer="All four wrap existing aqp_models modules so policy and offline ML share one source of truth."
              />
            </MotionInView>
            <MotionInView delay={0.2}>
              <FrameworkColumn
                heading="Advantage estimators"
                items={[
                  { name: "ReinforcePlusPlusAdvantage", sub: "Leave-one-out cohort baseline + decoupled global normalisation (NeMo-RL port)" },
                  { name: "GRPOAdvantage", sub: "Group-relative, no-critic (DeepSeek R1 / NeMo-RL parity)" },
                  { name: "GAEAdvantage", sub: "Generalised advantage estimation, the SB3 default" },
                ]}
                footer="Register through RLComponent alongside envs / rewards / policies. New estimators are a simple subclass."
              />
            </MotionInView>
          </div>
        </div>
      </section>

      {/* PRUDEX-Compass */}
      <section
        id="evaluation"
        className="px-6"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <FeatureBreakdown
          eyebrow="PRUDEX-Compass"
          tone="warn"
          title="17 measures across six axes. Sharpe is only one of them."
          body="The PRUDEX-Compass evaluation framework looks at the policy across Profitability, Risk-control, Universality, Diversification, Explainability, and X-tra (regime-conditioned). Every backtest evaluation writes a compass row to the RL Lab dashboard."
          bullets={[
            "Profitability: total_return, sharpe, sortino, calmar, cumulative_return",
            "Risk-control: max_drawdown, vol, downside_vol, ulcer_index, var_99",
            "Universality: cross_dataset_sharpe_mean, generalisation_gap",
            "Diversification: portfolio_weight_entropy, herfindahl",
            "Explainability: regime_conditioned_sharpe, exposure_drift, decision_attribution",
          ]}
          cta={{ label: "Open RL Lab", href: "/signup" }}
          visual={
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <MetricSparkline
                  data={REWARD_CURVE}
                  label="Reward"
                  value="+482"
                  tone="tertiary"
                  height={64}
                  showDelta={false}
                />
                <MetricSparkline
                  data={SHARPE_CURVE}
                  label="Sharpe"
                  value="2.18"
                  tone="primary"
                  height={64}
                  showDelta={false}
                />
                <MetricSparkline
                  data={DRAWDOWN_CURVE}
                  label="Max DD"
                  value="-4.2%"
                  tone="neg"
                  height={64}
                  showDelta={false}
                />
                <MetricSparkline
                  data={ENTROPY_CURVE}
                  label="Wt. entropy"
                  value="0.78"
                  tone="secondary"
                  height={64}
                  showDelta={false}
                />
              </div>
              <div
                className="rounded-lg p-3 text-xs leading-relaxed"
                style={{
                  background: "rgba(245,158,11,0.06)",
                  border: "1px solid rgba(245,158,11,0.25)",
                  color: "var(--text-muted)",
                }}
              >
                Illustrative metrics — your runs persist to{" "}
                <code>rl.equity_curves</code> in Iceberg and render here.
              </div>
            </div>
          }
        />
      </section>

      {/* Iceberg trajectory store */}
      <section id="iceberg" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Trajectory store"
            title="Four Iceberg tables. DuckDB-queryable. Replay-grade."
          />
          <FeatureGrid columns={4}>
            <FeatureCard
              icon={Boxes}
              tone="primary"
              title="rl.trajectories"
              body="Every env step (obs, action, reward, next_obs, done) for every run. Buffered Arrow writes via IcebergTrajectoryStore."
            />
            <FeatureCard
              icon={TrendingUp}
              tone="tertiary"
              title="rl.equity_curves"
              body="Portfolio value + drawdown by step. Powers the RL Lab equity-curve viewer and PRUDEX-Compass metrics."
            />
            <FeatureCard
              icon={Activity}
              tone="secondary"
              title="rl.action_logs"
              body="Action vectors by step. Use for action-distribution analysis and policy debugging."
            />
            <FeatureCard
              icon={Binary}
              tone="warn"
              title="rl.reward_decomposition"
              body="Per-term reward attribution when using CompositeReward. Lets you see which term is driving learning."
            />
          </FeatureGrid>
        </div>
      </section>

      {/* RL applications */}
      <section className="px-6 py-20" style={{ background: "rgba(255,255,255,0.02)" }}>
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Where RL ships in AQP"
            title="Three first-class application surfaces"
          />
          <FeatureGrid columns={3}>
            <FeatureCard
              icon={Award}
              tone="primary"
              title="Portfolio allocation"
              body="WeightCentricPipeline injected as context['rl_agent'] into backtest engines that opt-in via EngineCapabilities.supports_rl_injection."
            />
            <FeatureCard
              icon={Workflow}
              tone="secondary"
              title="Market making"
              body="MarketMakingEnv + Avellaneda-Stoikov / Cartea-Jaimungal HJB solvers (JAX-compiled). Compare RL policies against optimal-control benchmarks."
            />
            <FeatureCard
              icon={ShieldCheck}
              tone="tertiary"
              title="Optimal execution"
              body="OptimalExecutionEnv for parent-order slicing. Reward terms cover implementation shortfall, market impact, queue-position economy."
            />
          </FeatureGrid>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="px-6 py-20">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="FAQ"
            title="RL in AQP — common questions"
          />
          <FaqAccordion items={FAQ_ITEMS} />
        </div>
      </section>

      <CallToActionBlock
        eyebrow="Ready to train"
        title="From notebook to deployed policy in one weekend."
        subtitle="The RL Lab gives you a visual builder for envs, rewards, observations, and actions. Snapshot to a hash-locked spec, train via Celery, replay against last month."
        primaryCta={{ label: "Open the RL Lab", href: "/signup" }}
        secondaryCta={{
          label: "Read RL in finance",
          href: "/learn/reinforcement-learning-in-finance",
        }}
      />
    </>
  );
}

function FrameworkColumn({
  heading,
  items,
  footer,
}: {
  heading: string;
  items: { name: string; sub: string }[];
  footer?: string;
}) {
  return (
    <div
      className="h-full rounded-xl p-6"
      style={{
        background: "var(--glass-bg)",
        border: "1px solid var(--glass-border)",
        backdropFilter: "blur(var(--glass-blur))",
      }}
    >
      <div
        className="text-xs font-bold uppercase tracking-wider"
        style={{ color: "var(--accent-primary)" }}
      >
        {heading}
      </div>
      <ul className="mt-4 space-y-3">
        {items.map((item) => (
          <li key={item.name}>
            <div
              className="flex items-start gap-2 text-sm font-semibold"
              style={{ color: "var(--text-primary)" }}
            >
              <CheckCircle
                size={14}
                style={{ color: "var(--accent-tertiary)", marginTop: 2, flexShrink: 0 }}
              />
              <code className="font-mono">{item.name}</code>
            </div>
            <div
              className="ml-6 mt-1 text-xs leading-snug"
              style={{ color: "var(--text-muted)" }}
            >
              {item.sub}
            </div>
          </li>
        ))}
      </ul>
      {footer ? (
        <div
          className="mt-5 border-t pt-4 text-xs leading-snug"
          style={{
            borderColor: "var(--border-default)",
            color: "var(--text-muted)",
          }}
        >
          {footer}
        </div>
      ) : null}
    </div>
  );
}

// ---------- Content data ----------

const COMPONENT_KINDS = [
  { label: "rl_env", title: "Environment", sub: "FinRL stockstats / covariance / turbulence / VIX / fundamentals" },
  { label: "rl_observation", title: "Observation builder", sub: "StackedObservationBuilder composes feature blocks" },
  { label: "rl_action", title: "Action space", sub: "Continuous / softmax / integer-shares / discrete / target-position" },
  { label: "rl_reward", title: "Reward term", sub: "CompositeReward sums weighted terms with per-step decomposition" },
  { label: "rl_termination", title: "Termination", sub: "Max steps / max drawdown / target-reached / liquidation triggered" },
  { label: "rl_policy", title: "Policy", sub: "PPO / SAC / TD3 / DDPG / DQN / sb3-contrib + custom backbones" },
  { label: "rl_agent", title: "Agent", sub: "Adapter into one of six frameworks (SB3, ElegantRL, RLlib, ...)" },
  { label: "rl_data", title: "Data pipeline", sub: "Iceberg / Yahoo / Alpaca / streaming / replay" },
  { label: "rl_ensembler", title: "Ensembler", sub: "WalkForwardEnsembler — FinRL DRLEnsembleAgent port" },
  { label: "rl_experiment", title: "Experiment", sub: "Train / eval / paper / replay / walk-forward orchestration" },
  { label: "rl_trajectory_store", title: "Trajectory store", sub: "Iceberg writer for the 4 trajectory tables" },
  { label: "rl_advantage_estimator", title: "Advantage estimator", sub: "GAE / GRPO / REINFORCE++ (NeMo-RL ports)" },
  { label: "rl_policy_backbone", title: "Policy backbone", sub: "Transformer / Recurrent / Autoencoder / PatchTST" },
];

const PIPELINE_STAGES = [
  { alias: "f_S", title: "Selector", body: "Restrict universe — top-k by score, regime-aware filter, sector exclusion." },
  { alias: "f_A", title: "Allocator", body: "RL policy emits raw weights for the selected universe (PPO / SAC / GRPO)." },
  { alias: "f_T", title: "Timing adjuster", body: "Apply slippage, latency lag, smoothing to translate raw weights to executable orders." },
  { alias: "f_R", title: "Risk overlay", body: "RiskLimits + TargetWeightsRebalancer cap per-name exposure and turnover." },
];

const REWARD_CURVE = [
  -20, -15, -8, -2, 8, 16, 22, 30, 42, 58, 80, 110, 145, 180, 215, 250, 290,
  330, 370, 420, 460, 482,
];
const SHARPE_CURVE = [
  0.8, 0.9, 1.0, 0.95, 1.1, 1.2, 1.35, 1.5, 1.65, 1.7, 1.78, 1.85, 1.9, 2.0,
  2.05, 2.1, 2.12, 2.15, 2.16, 2.17, 2.18,
];
const DRAWDOWN_CURVE = [
  0, -0.5, -1.2, -2.1, -3.4, -4.8, -5.4, -5.1, -4.7, -4.5, -4.3, -4.2, -4.3,
  -4.2, -4.2, -4.2, -4.2, -4.2,
];
const ENTROPY_CURVE = [
  0.4, 0.45, 0.5, 0.55, 0.6, 0.62, 0.65, 0.68, 0.7, 0.72, 0.74, 0.75, 0.76,
  0.77, 0.77, 0.78, 0.78,
];

const FAQ_ITEMS = [
  {
    question: "What does 'deployment-consistent' actually mean?",
    answer:
      "The FinRL-X four-stage pipeline (f_S → f_A → f_T → f_R) is the single code path that translates a policy output into broker orders. Offline backtest engines opt in by flipping EngineCapabilities.supports_rl_injection=True; live paper-trading routes through the same pipeline via context['rl_agent']. Same code, same target weights — no silent offline-online drift.",
  },
  {
    question: "Do I have to use all four stages?",
    answer:
      "No. f_A is mandatory (the policy itself). The other three default to identity functions. A research-only policy can ship without a Selector or Risk overlay; before going live capital, you wire them in and replay.",
  },
  {
    question: "How are trajectories persisted at scale?",
    answer:
      "IcebergTrajectoryStore buffers Arrow batches and flushes through iceberg_catalog.append_arrow (AGENTS rule 18). The four tables (rl.trajectories / rl.equity_curves / rl.action_logs / rl.reward_decomposition) share batching, tenancy stamping, and flush semantics. Queries go through DuckDB or the RL Lab UI.",
  },
  {
    question: "Can I bring my own RL framework?",
    answer:
      "Yes. Subclass BaseRLAgent in aqp_rl/agents/, set rl_alias and rl_source, expose via the agents __init__.py (suppress import errors so the dep stays optional). The metaclass auto-registers it through @register so the RL Lab can list it.",
  },
  {
    question: "How does LLM-Hybrid fit in?",
    answer:
      "LLMHybridAgent is FinRobot-style — a five-stage cascade (low_intelligence / high_intelligence / low_reflection / high_reflection / decision) that mixes an LLM advisor with the RL backbone's prediction. LLM calls route through router_complete per AGENTS rule 2; the agent degrades gracefully to HOLD when any stage fails.",
  },
];
