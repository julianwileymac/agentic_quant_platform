import {
  Activity,
  BookOpen,
  BrainCircuit,
  Database,
  GitBranch,
  Layers,
  Lock,
  ScrollText,
  ShieldCheck,
  Sparkles,
  Workflow,
  Zap,
} from "lucide-react";

import { AgentFlowDiagram } from "@/components/marketing/illustrations/AgentFlowDiagram";
import { CallToActionBlock } from "@/components/marketing/CallToActionBlock";
import { CodeBlock } from "@/components/marketing/CodeBlock";
import {
  ComparisonTable,
  type ComparisonCell,
} from "@/components/marketing/ComparisonTable";
import { FaqAccordion } from "@/components/marketing/FaqAccordion";
import { FeatureBreakdown } from "@/components/marketing/FeatureBreakdown";
import { FeatureCard } from "@/components/marketing/FeatureCard";
import { FeatureGrid } from "@/components/marketing/FeatureGrid";
import { Hero } from "@/components/marketing/Hero";
import { MedallionLayers } from "@/components/marketing/illustrations/MedallionLayers";
import { MetricSparkline } from "@/components/marketing/MetricSparkline";
import { MotionInView } from "@/components/marketing/MotionInView";
import { RLLoopDiagram } from "@/components/marketing/illustrations/RLLoopDiagram";
import { SectionHeader } from "@/components/marketing/SectionHeader";
import { StatStrip } from "@/components/marketing/StatStrip";

export const dynamic = "force-static";
export const revalidate = 3600;

export default function MarketingHomePage() {
  return (
    <>
      <Hero
        eyebrow="AgenticOps for quantitative finance"
        eyebrowIcon={Sparkles}
        title="The agentic quant platform you would have built yourself."
        titleHighlight="agentic quant platform"
        subtitle="Hierarchical RAG over your alpha library. Hash-locked agent specs. Twelve backtest engines with a capability-driven dispatcher. Paper trading on Alpaca, IBKR, Tradier. All multi-tenant, all auditable, all yours."
        primaryCta={{ label: "Start free", href: "/signup" }}
        secondaryCta={{ label: "Read the docs", href: "/docs" }}
        illustration={<AgentFlowDiagram className="rounded-xl p-2" />}
        meta="SOC 2 in progress · GDPR-ready · BYOK for every brokerage"
      />

      <StatStrip
        stats={[
          { value: 9, suffix: "+", label: "Backtest engines", tone: "primary" },
          { value: 5, label: "Spec runtimes", tone: "secondary" },
          { value: 17, label: "PRUDEX measures", tone: "tertiary" },
          { value: 4, label: "Tenancy strategies", tone: "primary" },
        ]}
      />

      {/* Four pillars */}
      <section className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Four pillars"
            title="Everything a serious quant desk needs"
            subtitle="Built on the open-source AQP engine. Cloud-managed for you, with your data fenced into your tenant."
          />
          <FeatureGrid columns={4}>
            <FeatureCard
              icon={BrainCircuit}
              tone="primary"
              title="AgentOps"
              body="Five hash-locked spec runtimes. Five canonical multi-agent patterns. Built-in guardrails (cost cap, rate limit, forbidden terms). The DataMCP boundary keeps agents on rails."
              href="/product/agentops"
            />
            <FeatureCard
              icon={Sparkles}
              tone="secondary"
              title="Reinforcement Learning"
              body="RLRuntime, six framework adapters, four policy backbones, three native advantage estimators. FinRL-X four-stage pipeline. Iceberg-backed trajectories."
              href="/product/reinforcement-learning"
            />
            <FeatureCard
              icon={Database}
              tone="tertiary"
              title="Data Platform"
              body="Medallion Iceberg lakehouse (Bronze / Silver / Gold). Active discovery across Airbyte, Polaris, Hudi. HierarchicalRAG with pgvector + Redis."
              href="/product/data-platform"
            />
            <FeatureCard
              icon={Activity}
              tone="warn"
              title="Backtesting"
              body="Nine engines under one capability-driven dispatch. Per-bar agent and RL injection. JAX-compiled HJB solvers for market making and optimal execution."
              href="/product/backtesting"
            />
          </FeatureGrid>
        </div>
      </section>

      {/* How it works */}
      <section className="px-6 py-20" style={{ background: "rgba(255,255,255,0.02)" }}>
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="How it works"
            title="Author once. Snapshot. Replay forever."
            subtitle="Every spec is hash-locked. First run snapshots an immutable version row. Behaviour changes always produce a new version — never an in-place mutation."
          />
          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {STEPS.map((step, i) => (
              <MotionInView key={step.title} delay={i * 0.1}>
                <div
                  className="relative h-full rounded-xl p-6"
                  style={{
                    background: "var(--glass-bg)",
                    border: "1px solid var(--glass-border)",
                    backdropFilter: "blur(var(--glass-blur))",
                  }}
                >
                  <div
                    className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-lg text-base font-bold"
                    style={{
                      background: "var(--gradient-hero)",
                      color: "white",
                      boxShadow: "var(--shadow-glow-primary)",
                    }}
                  >
                    {i + 1}
                  </div>
                  <h3
                    className="text-lg font-semibold"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {step.title}
                  </h3>
                  <p
                    className="mt-2 text-sm leading-relaxed"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    {step.body}
                  </p>
                  {step.code ? (
                    <div className="mt-4">
                      <CodeBlock
                        code={step.code}
                        language={step.lang ?? "python"}
                        copyable={false}
                      />
                    </div>
                  ) : null}
                </div>
              </MotionInView>
            ))}
          </div>
        </div>
      </section>

      {/* Agentic breakdown */}
      <FeatureBreakdown
        eyebrow="AgentOps"
        tone="primary"
        title="Agents you can deploy near live capital."
        body="Every AQP agent is a hash-locked AgentSpec executed by AgentRuntime. The runtime enforces cost caps, rate limits, max calls, forbidden terms, and minimum confidence — at runtime, not as documentation. Five orchestration patterns: sequential, parallel, debate, coordinator, ReAct."
        bullets={[
          "Hash-locked AgentSpec → immutable agent_spec_versions row",
          "DataMCP boundary — agents never touch Postgres or Iceberg directly",
          "Cost / rate / max-call guardrails enforced by AgentRuntime",
          "Replay any run against any historical data window",
        ]}
        cta={{ label: "Explore AgentOps", href: "/product/agentops" }}
        visual={
          <div className="overflow-hidden rounded-xl p-2" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", backdropFilter: "blur(var(--glass-blur))" }}>
            <AgentFlowDiagram />
          </div>
        }
      />

      {/* RL breakdown (reverse) */}
      <FeatureBreakdown
        eyebrow="Reinforcement Learning"
        tone="secondary"
        title="Deployment-consistent RL for portfolio allocation."
        body="The FinRL-X four-stage pipeline (Selector → Allocator → Timing → Risk overlay) produces the same target-weight semantics in the offline backtest and the live broker. Native REINFORCE++ / GRPO / GAE advantage estimators. Four policy backbones wrapping the existing ML model zoo."
        bullets={[
          "RLRuntime with hash-locked RLExperimentSpec — every run is replayable",
          "Six framework adapters: SB3, ElegantRL, RLlib, CleanRL, NeMo-RL, LLM-Hybrid",
          "Iceberg-backed trajectory store (4 tables) queryable via DuckDB",
          "PRUDEX-Compass 17-measure evaluation across six axes",
        ]}
        cta={{ label: "Explore RL", href: "/product/reinforcement-learning" }}
        reverse
        visual={
          <div className="space-y-4">
            <div className="overflow-hidden rounded-xl p-2" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", backdropFilter: "blur(var(--glass-blur))" }}>
              <RLLoopDiagram />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <MetricSparkline
                data={ILLUSTRATIVE_REWARD}
                label="Reward"
                value="+482"
                tone="tertiary"
                height={56}
                showDelta={false}
              />
              <MetricSparkline
                data={ILLUSTRATIVE_SHARPE}
                label="Sharpe"
                value="2.18"
                tone="primary"
                height={56}
                showDelta={false}
              />
              <MetricSparkline
                data={ILLUSTRATIVE_DRAWDOWN}
                label="Drawdown"
                value="-4.2%"
                tone="neg"
                height={56}
                showDelta={false}
              />
            </div>
          </div>
        }
      />

      {/* Data plane breakdown */}
      <FeatureBreakdown
        eyebrow="Data Platform"
        tone="tertiary"
        title="A medallion data plane your agents can browse."
        body="Bronze for raw, Silver for normalised, Gold for products — every Iceberg write goes through one wrapper with declared layer and business metadata. The active discovery service unifies Airbyte, Polaris, and Hudi entries. Agents read through DataMCP tools, never raw ORM."
        bullets={[
          "Three medallion layers with namespace-prefix validation",
          "Bipartite lineage graph dual-written from every dataset event",
          "HierarchicalRAG over alpha library, papers, regulatory corpora",
          "pgvector control plane alongside Redis hybrid for vector search",
        ]}
        cta={{ label: "Explore Data Platform", href: "/product/data-platform" }}
        visual={
          <div className="overflow-hidden rounded-xl p-2" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)", backdropFilter: "blur(var(--glass-blur))" }}>
            <MedallionLayers />
          </div>
        }
      />

      {/* Cloud vs Self-Hosted */}
      <section className="px-6 py-24" style={{ background: "rgba(255,255,255,0.02)" }}>
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Two ways to run AQP"
            title="Cloud-managed or local-first. Same engine."
            subtitle="Cloud lives at app.aqp.fund with multi-tenant Auth0 + Entra identity. Self-hosted runs on any Kubernetes cluster (rpi k3s, EKS, AKS, GKE) inside its own aqp-* namespaces. Pick what fits — switch later without rewriting code."
          />
          <ComparisonTable columns={COMPARE_COLUMNS} rows={COMPARE_ROWS} />
          <div className="mt-8 flex flex-col items-center justify-center gap-3 text-sm sm:flex-row">
            <a
              href="/cloud"
              className="rounded-md px-6 py-2.5 font-semibold"
              style={{
                background: "var(--accent-primary)",
                color: "white",
              }}
            >
              See cloud plan
            </a>
            <a
              href="/self-hosted"
              className="rounded-md border px-6 py-2.5 font-semibold"
              style={{
                borderColor: "var(--border-default)",
                color: "var(--text-primary)",
              }}
            >
              See self-hosted
            </a>
          </div>
        </div>
      </section>

      {/* Security strip */}
      <section className="px-6 py-20">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Security & compliance"
            title="Built for production from day one."
            subtitle="Every halt destructive action requires step-up MFA. Every audit row is written BEFORE the action. Every multi-tenant query honours row-level security."
          />
          <FeatureGrid columns={4}>
            <FeatureCard
              icon={ShieldCheck}
              tone="primary"
              title="Step-up MFA (RFC 9470)"
              body="Kill-switch, broker BYOK CRUD, tenant invites, Terraform apply / destroy — all gated by fresh MFA. WWW-Authenticate header bubbled to the SPA for popup retry."
            />
            <FeatureCard
              icon={Lock}
              tone="tertiary"
              title="Tenant data isolation"
              body="Four TenancyStrategy implementations (shared+RLS, schema-per-tenant, database-per-enterprise, hybrid). Move tiers without code changes."
            />
            <FeatureCard
              icon={ScrollText}
              tone="secondary"
              title="Audit-first ledgers"
              body="workload_runs, agent_runs_v2, terraform_runs, workflow_runs — every mutating operation writes a structured row BEFORE the call executes."
            />
            <FeatureCard
              icon={Zap}
              tone="warn"
              title="Single-button halt"
              body="POST /api/kill-switch fans out via Promise.allSettled to six halt endpoints. Topbar KillSwitch reachable from every page."
            />
          </FeatureGrid>
        </div>
      </section>

      {/* Architecture story strip */}
      <section className="px-6 py-20" style={{ background: "rgba(255,255,255,0.02)" }}>
        <div className="mx-auto grid max-w-7xl gap-10 md:grid-cols-[1fr_1fr]">
          <MotionInView from="left">
            <div
              className="rounded-xl p-6"
              style={{
                background: "var(--glass-bg-strong)",
                border: "1px solid var(--glass-border-strong)",
                backdropFilter: "blur(var(--glass-blur))",
              }}
            >
              <div className="flex items-center gap-3">
                <Layers
                  size={20}
                  style={{ color: "var(--accent-primary)" }}
                />
                <h3
                  className="text-lg font-semibold"
                  style={{ color: "var(--text-primary)" }}
                >
                  The boundary map
                </h3>
              </div>
              <p
                className="mt-3 text-sm leading-relaxed"
                style={{ color: "var(--text-secondary)" }}
              >
                AQP is decomposed into focused boundaries: aqp_control_plane,
                aqp_platform_core, aqp_client, aqp_bots, aqp_rl, aqp_models,
                aqp_ui, aqp_admin, aqp_ide, aqp_cli. Each has its own
                AGENTS.md contract; the quant runtime stays in aqp.
              </p>
              <div className="mt-5 grid grid-cols-2 gap-2 text-xs">
                {BOUNDARY_PILLS.map((b) => (
                  <div
                    key={b}
                    className="rounded border px-2 py-1.5 text-center font-mono"
                    style={{
                      borderColor: "var(--border-default)",
                      background: "var(--bg-elevated)",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {b}
                  </div>
                ))}
              </div>
            </div>
          </MotionInView>

          <MotionInView from="right">
            <div
              className="rounded-xl p-6"
              style={{
                background: "var(--glass-bg-strong)",
                border: "1px solid var(--glass-border-strong)",
                backdropFilter: "blur(var(--glass-blur))",
              }}
            >
              <div className="flex items-center gap-3">
                <Workflow
                  size={20}
                  style={{ color: "var(--accent-secondary)" }}
                />
                <h3
                  className="text-lg font-semibold"
                  style={{ color: "var(--text-primary)" }}
                >
                  Author a spec, run it anywhere
                </h3>
              </div>
              <p
                className="mt-3 text-sm leading-relaxed"
                style={{ color: "var(--text-secondary)" }}
              >
                A bot's strategy graph, an RL experiment, an agent prompt, a
                workflow DAG, a Terraform stack — all of them are YAML or
                Python that snapshots to an immutable version row. Tasks
                stream canonical progress frames through one WebSocket.
              </p>
              <div className="mt-4">
                <CodeBlock
                  code={`from aqp.agents import AgentRuntime, AgentSpec\n\nspec = AgentSpec.from_yaml("configs/agents/alpha_researcher.yaml")\nrun = AgentRuntime(spec).invoke({"universe": "spy_top_50"})\n\nprint(run.spec_version_id, run.cost_usd, run.findings_count)`}
                  language="python"
                  filename="alpha_run.py"
                />
              </div>
            </div>
          </MotionInView>
        </div>
      </section>

      {/* Learn callout */}
      <section className="px-6 py-20">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Deep dives"
            title="The quant ops literature, written for engineers."
            subtitle="The Learn hub is a growing library of long-form articles on agentic finance, RL portfolio construction, hash-locked specs, and the medallion data plane."
          />
          <FeatureGrid columns={3}>
            <FeatureCard
              icon={BrainCircuit}
              tone="primary"
              title="AgentOps in finance"
              body="Why agentic loops produce better alpha than monolithic scripts, and how hash-locked specs bridge the audit gap."
              href="/learn/agentops-in-finance"
            />
            <FeatureCard
              icon={Sparkles}
              tone="secondary"
              title="RL in finance"
              body="From the Markowitz objective to deployment-consistent weight pipelines. Why offline-online drift is the boss-fight."
              href="/learn/reinforcement-learning-in-finance"
            />
            <FeatureCard
              icon={GitBranch}
              tone="tertiary"
              title="Hash-locked specs"
              body="The case against self-modifying agents in finance, and what AQP does instead: snapshots, replays, and immutable versions."
              href="/learn/hash-locked-specs"
            />
            <FeatureCard
              icon={Workflow}
              tone="primary"
              title="Multi-agent patterns"
              body="Sequential, parallel, debate, coordinator, ReAct — five canonical topologies and when each one earns its keep."
              href="/learn/multi-agent-patterns"
            />
            <FeatureCard
              icon={Activity}
              tone="warn"
              title="FinRL-X pipeline"
              body="Selector → Allocator → Timing → Risk overlay. The four pure functions that close the offline-to-live RL gap."
              href="/learn/finrl-x-portfolio-pipeline"
            />
            <FeatureCard
              icon={Database}
              tone="tertiary"
              title="Medallion data plane"
              body="Bronze / Silver / Gold isn't just a naming convention. It is a contract about who writes what, with what business metadata."
              href="/learn/medallion-data-platform"
            />
          </FeatureGrid>
          <div className="mt-10 text-center">
            <a
              href="/learn"
              className="inline-flex items-center gap-2 text-sm font-semibold"
              style={{ color: "var(--accent-primary)" }}
            >
              <BookOpen size={14} />
              Browse the full Learn hub →
            </a>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="px-6 py-20" style={{ background: "rgba(255,255,255,0.02)" }}>
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="FAQ"
            title="Common questions"
            subtitle="Engineering details about the cloud platform and the open-source engine."
          />
          <FaqAccordion items={FAQ_ITEMS} />
        </div>
      </section>

      <CallToActionBlock
        eyebrow="Get started"
        title="Stop rebuilding the same trading harness."
        subtitle="Sign up free. Bring your own brokerage keys. Spin up a strategy in minutes."
        primaryCta={{ label: "Create free account", href: "/signup" }}
        secondaryCta={{ label: "See pricing", href: "/pricing" }}
      />
    </>
  );
}

// ---------- Content data ----------

const STEPS = [
  {
    title: "Author a spec",
    body: "Author a hash-locked AgentSpec, BotSpec, RLExperimentSpec, AnalysisSpec, or WorkflowSpec in YAML or Python. Forms in the Lab studio generate them for you.",
    code: 'spec = AgentSpec(\n  name="alpha.researcher",\n  model="claude-4-sonnet",\n  guardrails={"cost_budget_usd": 5.0},\n)',
    lang: "python",
  },
  {
    title: "Snapshot a version",
    body: "First call snapshots an immutable agent_spec_versions row (sha256 of canonical JSON). Behaviour changes always produce a new version row — never in-place mutation.",
    code: 'version_id = persist_spec(spec)\n# sha256 = 9a4f...c1d3\n# old version still queryable',
    lang: "python",
  },
  {
    title: "Run + replay",
    body: "AgentRuntime executes against the pinned version, records an agent_runs_v2 row with cost, latency, and findings. Replay later with new data, same code.",
    code: "run = AgentRuntime(spec).invoke(inputs)\nrun.replay(window=last_7d)\n# deterministic given the version + data",
    lang: "python",
  },
];

const ILLUSTRATIVE_REWARD = [
  -20, -15, -8, -2, 8, 16, 22, 30, 42, 58, 80, 110, 145, 180, 215, 250, 290,
  330, 370, 420, 460, 482,
];
const ILLUSTRATIVE_SHARPE = [
  0.8, 0.9, 1.0, 0.95, 1.1, 1.2, 1.35, 1.5, 1.65, 1.7, 1.78, 1.85, 1.9, 2.0,
  2.05, 2.1, 2.12, 2.15, 2.16, 2.17, 2.18,
];
const ILLUSTRATIVE_DRAWDOWN = [
  0, -0.5, -1.2, -2.1, -3.4, -4.8, -5.4, -5.1, -4.7, -4.5, -4.3, -4.2, -4.3,
  -4.2, -4.2, -4.2, -4.2, -4.2, -4.2,
];

const COMPARE_COLUMNS = [
  { name: "Cloud", tagline: "app.aqp.fund", highlight: true },
  { name: "Self-Hosted", tagline: "Your cluster" },
];

const COMPARE_ROWS: { label: string; group?: string; cells: ComparisonCell[] }[] = [
  { group: "Core engine", label: "AgentRuntime + BotRuntime + RLRuntime + WorkflowRuntime", cells: [true, true] },
  { group: "Core engine", label: "9 backtest engines + capability dispatch", cells: [true, true] },
  { group: "Core engine", label: "Medallion Iceberg + HierarchicalRAG", cells: [true, true] },
  { group: "Core engine", label: "Hash-locked spec versions", cells: [true, true] },

  { group: "Identity & tenancy", label: "Auth0 B2C self-signup", cells: [true, "-"] },
  { group: "Identity & tenancy", label: "Microsoft Entra ID B2B SSO", cells: [true, true] },
  { group: "Identity & tenancy", label: "EntraTenantLink wizard", cells: [true, true] },
  { group: "Identity & tenancy", label: "Tenant strategy", cells: ["Auto-managed", "You pick"] },

  { group: "Deployment", label: "Hosted at app.aqp.fund", cells: [true, false] },
  { group: "Deployment", label: "Docker Compose / K8s / native", cells: [false, true] },
  { group: "Deployment", label: "Cloudflare edge + DDoS", cells: [true, false] },
  { group: "Deployment", label: "Bring your own KMS / Vault", cells: [false, true] },

  { group: "Support", label: "Email + chat support", cells: [true, false] },
  { group: "Support", label: "Status page (status.aqp.fund)", cells: [true, "-"] },
  { group: "Support", label: "Community Discord", cells: [true, true] },
];

const BOUNDARY_PILLS = [
  "aqp_control_plane",
  "aqp_platform_core",
  "aqp_client",
  "aqp_admin",
  "aqp_ui",
  "aqp_ide",
  "aqp_cli",
  "aqp_bots",
  "aqp_rl",
  "aqp_models",
];

const FAQ_ITEMS = [
  {
    question: "Do you train on my data?",
    answer:
      "No. AQP runs LLMs through your chosen provider (or your own local Ollama / vLLM endpoint) via the router_complete gateway. Your prompts, alpha factor formulas, and trade history are never used to train models.",
  },
  {
    question: "Is the AQP engine open source?",
    answer:
      "The AQP engine is source-available under a fair-use license. You can self-host the entire stack via Docker Compose, Kubernetes, or native dev. The cloud-hosted PaaS at app.aqp.fund is the same engine plus managed identity, tenancy, and Cloudflare edge.",
  },
  {
    question: "Can I bring my own brokerage credentials?",
    answer:
      "Yes. Every paid tier supports BYOK for Alpaca, Interactive Brokers, Tradier, TradeStation, Schwab, ETrade, Binance, Coinbase, Kraken, OKX. Keys are envelope-encrypted (Vault Transit in prod, AESGCM locally) and never returned to the browser. Create + delete operations require step-up MFA per RFC 9470.",
  },
  {
    question: "How are agent runs replayable?",
    answer:
      "Every AgentSpec / BotSpec / RLExperimentSpec / AnalysisSpec / WorkflowSpec is hash-locked. First run snapshots a row in *_spec_versions. The matching *_runs ledger row references spec_version_id, so any historic run can be re-executed against new or original data without ambiguity.",
  },
  {
    question: "What identity providers do you support?",
    answer:
      "Auth0 (B2C self-signup, default for Free + Pro), Microsoft Entra ID (B2B enterprise SSO via the EntraTenantLink wizard, included on Enterprise), generic OIDC, Cloudflare Access, and a mock provider for local dev. All flow through the IdentityProvider chain (AQP hard rule 27).",
  },
  {
    question: "Is multi-tenancy actually safe?",
    answer:
      "Yes. The TenancyStrategy abstraction has four implementations: SharedSchemaRLSStrategy (Postgres row-level security, default for Free + Pro), SchemaPerTenantStrategy (Team tier), DatabasePerEnterpriseStrategy (Enterprise), and HybridStrategy. RLS DDL is enforced on every tenant-scoped table by migration 0063; the session GUC honours the active RequestContext.",
  },
];
