import Link from "next/link";
import {
  Activity,
  BrainCircuit,
  Database,
  GitBranch,
  Layers,
  ShieldCheck,
  Sparkles,
  TrendingUp,
} from "lucide-react";

export const dynamic = "force-static";
export const revalidate = 3600;

export default function MarketingHomePage() {
  return (
    <>
      <HeroSection />
      <FeatureGrid />
      <SocialProofStrip />
      <CallToAction />
    </>
  );
}

function HeroSection() {
  return (
    <section className="mx-auto flex max-w-7xl flex-col items-center px-6 py-24 text-center">
      <div className="mb-6 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium tracking-wide" style={{ borderColor: "var(--border-default)", color: "var(--text-secondary)" }}>
        <Sparkles size={12} />
        AgenticOps for quantitative finance
      </div>

      <h1 className="max-w-4xl text-balance text-5xl font-bold tracking-tight md:text-6xl" style={{ color: "var(--text-primary)" }}>
        The agentic quant platform you would have built yourself.
      </h1>

      <p className="mt-6 max-w-2xl text-lg leading-relaxed" style={{ color: "var(--text-secondary)" }}>
        Hierarchical RAG over your alpha library. Hash-locked agent specs.
        Twelve backtest engines with a capability-driven dispatcher. Paper
        trading on Alpaca, IBKR, Tradier. All multi-tenant, all auditable,
        all yours.
      </p>

      <div className="mt-10 flex flex-col items-center gap-3 sm:flex-row">
        <Link
          href="/signup"
          className="rounded-md px-6 py-3 text-base font-semibold"
          style={{ background: "var(--accent-primary)", color: "white" }}
        >
          Start free
        </Link>
        <Link
          href="/docs"
          className="rounded-md border px-6 py-3 text-base font-semibold"
          style={{
            borderColor: "var(--border-default)",
            color: "var(--text-primary)",
          }}
        >
          Read the docs
        </Link>
      </div>

      <div className="mt-6 text-xs" style={{ color: "var(--text-muted)" }}>
        SOC 2 in progress · GDPR-ready · BYOK for every brokerage
      </div>
    </section>
  );
}

const FEATURES = [
  {
    icon: BrainCircuit,
    title: "Agentic strategy authoring",
    body:
      "AlphaResearcher proposes factors. StrategyExecutor turns them into hash-locked specs. AgentRuntime enforces guardrails and cost caps. You audit the trail.",
  },
  {
    icon: Layers,
    title: "9 backtest engines, one API",
    body:
      "vectorbt-pro primary, event-driven fallback, OSS vectorbt, backtesting.py, ZVT, AAT, hftbacktest, more. Capability-driven dispatch picks the right engine.",
  },
  {
    icon: Database,
    title: "Medallion data plane",
    body:
      "Bronze / Silver / Gold Iceberg namespaces. Active discovery across Airbyte, Polaris, Hudi. pgvector-backed RAG. Cache write-through and prefetch.",
  },
  {
    icon: GitBranch,
    title: "Hash-locked spec versions",
    body:
      "Every agent, bot, RL experiment, analysis flow, and workflow is an immutable, hash-locked version row. Replay any run from any history.",
  },
  {
    icon: Activity,
    title: "Real-time telemetry",
    body:
      "Canonical /chat/stream/{task_id} and /live/stream/{channel_id} WebSockets. 30 FPS rAF-batched market data. Throttled, bounded, never blocks the UI.",
  },
  {
    icon: ShieldCheck,
    title: "Multi-tenant by default",
    body:
      "Auth0 Organizations for B2C. Entra ID + EntraTenantLink for enterprise B2B. Row-level security, schema-per-tenant, or database-per-enterprise — your choice.",
  },
];

function FeatureGrid() {
  return (
    <section className="border-t" style={{ borderColor: "var(--border-default)", background: "var(--bg-surface)" }}>
      <div className="mx-auto max-w-7xl px-6 py-20">
        <div className="mb-12 text-center">
          <h2 className="text-3xl font-bold tracking-tight" style={{ color: "var(--text-primary)" }}>
            Everything a serious quant desk needs
          </h2>
          <p className="mt-3 text-base" style={{ color: "var(--text-secondary)" }}>
            Built on the open-source AQP engine. Cloud-managed for you, with your data fenced into your tenant.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div
              key={title}
              className="rounded-lg border p-6"
              style={{
                borderColor: "var(--border-default)",
                background: "var(--bg-elevated)",
              }}
            >
              <Icon size={20} style={{ color: "var(--accent-primary)" }} />
              <h3 className="mt-4 text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
                {title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                {body}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function SocialProofStrip() {
  return (
    <section className="mx-auto max-w-7xl px-6 py-16">
      <div className="flex flex-col items-center gap-4">
        <div className="text-xs uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
          Trusted by quants worldwide
        </div>
        <div className="flex items-center gap-3 text-sm" style={{ color: "var(--text-secondary)" }}>
          <TrendingUp size={16} />
          From research notebook to production paper trading in under 10 minutes.
        </div>
      </div>
    </section>
  );
}

function CallToAction() {
  return (
    <section className="mx-auto max-w-4xl px-6 py-24 text-center">
      <h2 className="text-3xl font-bold" style={{ color: "var(--text-primary)" }}>
        Stop rebuilding the same trading harness.
      </h2>
      <p className="mt-4 text-base" style={{ color: "var(--text-secondary)" }}>
        Sign up free. Bring your own brokerage keys. Spin up a strategy in minutes.
      </p>
      <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
        <Link
          href="/signup"
          className="rounded-md px-6 py-3 text-base font-semibold"
          style={{ background: "var(--accent-primary)", color: "white" }}
        >
          Create free account
        </Link>
        <Link
          href="/pricing"
          className="rounded-md border px-6 py-3 text-base font-semibold"
          style={{
            borderColor: "var(--border-default)",
            color: "var(--text-primary)",
          }}
        >
          See pricing
        </Link>
      </div>
    </section>
  );
}
