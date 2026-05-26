import type { Metadata } from "next";
import {
  Award,
  Code,
  Eye,
  GitBranch,
  Globe,
  Heart,
  Layers,
  Lock,
  ScrollText,
  Sparkles,
  Target,
  Users,
} from "lucide-react";

import { CallToActionBlock } from "@/components/marketing/CallToActionBlock";
import { FeatureCard } from "@/components/marketing/FeatureCard";
import { FeatureGrid } from "@/components/marketing/FeatureGrid";
import { Hero } from "@/components/marketing/Hero";
import { MotionInView } from "@/components/marketing/MotionInView";
import { SectionHeader } from "@/components/marketing/SectionHeader";
import { StatStrip } from "@/components/marketing/StatStrip";

export const metadata: Metadata = {
  title: "About",
  description:
    "AQP is the agentic quant platform built by quants for quants. Cloud-hosted, multi-tenant, never closed-source.",
};

export const dynamic = "force-static";
export const revalidate = 86400;

export default function AboutPage() {
  return (
    <>
      <Hero
        eyebrow="About AQP"
        eyebrowIcon={Heart}
        title="The trading harness you would have built yourself."
        titleHighlight="built yourself"
        subtitle="If you had a year of weekends. We took every primitive a serious quant desk needs — hierarchical RAG, hash-locked agent specs, twelve backtest engines, paper trading, RL training with Iceberg trajectories — and made them composable, auditable, and multi-tenant by default."
        primaryCta={{ label: "Start free", href: "/signup" }}
        secondaryCta={{ label: "See architecture", href: "/docs/architecture" }}
      />

      <StatStrip
        stats={[
          { value: 5, label: "Spec runtimes", tone: "primary" },
          { value: 10, label: "Boundary packages", tone: "secondary" },
          { value: 55, label: "Hard rules in AGENTS.md", tone: "tertiary" },
          { value: 17, label: "PRUDEX measures", tone: "warn" },
        ]}
      />

      {/* The story */}
      <section className="px-6 py-24">
        <div className="mx-auto max-w-3xl">
          <MotionInView from="up">
            <div
              className="mb-3 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider"
              style={{
                borderColor: "var(--border-default)",
                color: "var(--accent-primary)",
                background: "var(--glass-bg)",
              }}
            >
              <Sparkles size={12} />
              Why we built AQP
            </div>
            <h2
              className="mt-3 text-3xl font-bold tracking-tight md:text-4xl"
              style={{ color: "var(--text-primary)", lineHeight: 1.15 }}
            >
              We built it because the alternatives all asked us to compromise.
            </h2>
            <div
              className="prose-article mt-6"
              style={{ color: "var(--text-secondary)" }}
            >
              <p>
                Every commercial trading platform we tried either locked our
                alpha into someone else's cloud, hid the backtest internals
                behind a SaaS API, or charged like an enterprise database for
                a single-tenant tool. Every open-source quant framework asked
                us to glue together our own data plane, agent loop, RL
                pipeline, observability stack, and identity broker.
              </p>
              <p>
                AQP is the platform we wanted to use: agent loops you can
                deploy near live capital, hash-locked specs so behaviour
                changes never silently happen, a medallion data plane your
                agents can browse, twelve backtest engines under one
                capability-driven dispatcher, and multi-tenant identity from
                day one. Local-first by design. Cloud-managed when you want
                it. Never closed-source.
              </p>
            </div>
          </MotionInView>
        </div>
      </section>

      {/* Principles */}
      <section
        className="px-6 py-24"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Our principles"
            title="Four ideas that shape every line of code we ship"
          />
          <FeatureGrid columns={4}>
            <FeatureCard
              icon={GitBranch}
              tone="primary"
              title="Spec runtimes over scripts"
              body="Every run produces an immutable, hash-locked version row. Replay is a first-class operation. Behaviour changes always produce a new version — never an in-place mutation."
            />
            <FeatureCard
              icon={Layers}
              tone="secondary"
              title="Boundaries over monoliths"
              body="Ten first-class subpackages (aqp_control_plane, aqp_platform_core, aqp_client, aqp_admin, aqp_ui, aqp_ide, aqp_cli, aqp_bots, aqp_rl, aqp_models), each with its own AGENTS.md contract."
            />
            <FeatureCard
              icon={Lock}
              tone="tertiary"
              title="Tenancy is plumbing, not bolted on"
              body="Four TenancyStrategy implementations: shared+RLS by default, schema-per-tenant for teams, database-per-enterprise for procurement, hybrid for the rest."
            />
            <FeatureCard
              icon={ScrollText}
              tone="warn"
              title="Auditable by construction"
              body="Every mutating operation writes a structured audit ledger row BEFORE the action executes. workload_runs, agent_runs_v2, terraform_runs, workflow_runs."
            />
          </FeatureGrid>
        </div>
      </section>

      {/* What we believe */}
      <section className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="What we believe"
            title="Opinionated where it matters; flexible everywhere else"
          />
          <FeatureGrid columns={3}>
            <FeatureCard
              icon={Eye}
              tone="primary"
              title="No black-box services"
              body="Every behaviour is reproducible from the spec + data + provider. No closed-source backend that produces outputs you can't audit."
            />
            <FeatureCard
              icon={Globe}
              tone="tertiary"
              title="Local-first is the default"
              body="The AQP engine is source-available. You can self-host the entire stack. The cloud platform adds managed identity and tenancy — same engine."
            />
            <FeatureCard
              icon={Award}
              tone="secondary"
              title="Boring infrastructure is good"
              body="We use the most boring viable option for everything that isn't the agentic loop. Postgres, Iceberg, Redis, Celery, FastAPI, Next.js."
            />
            <FeatureCard
              icon={Code}
              tone="primary"
              title="Code is the escape hatch"
              body="The studio UIs cover 80% of the cases. When you need to drop to code, every spec is just a YAML or Python dataclass — no hidden state."
            />
            <FeatureCard
              icon={Target}
              tone="tertiary"
              title="Real failure modes, not idealised demos"
              body="We document what breaks. Reward hacking, offline-online drift, prompt injection, multi-tenant cross-pollination. The Don't list in AGENTS.md is as important as the Hard rules."
            />
            <FeatureCard
              icon={Users}
              tone="warn"
              title="Built by quants, for quants"
              body="The team is a mix of practising quants and infrastructure engineers. We use AQP for our own research; the dogfood loop is short."
            />
          </FeatureGrid>
        </div>
      </section>

      {/* Boundary map */}
      <section
        id="architecture"
        className="px-6 py-24"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Boundary map"
            title="Ten packages, ten contracts"
            subtitle="The AQP source is intentionally decomposed by responsibility. Each package has its own AGENTS.md describing what it owns and what it doesn't."
          />
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {BOUNDARIES.map((b) => (
              <MotionInView key={b.name} delay={0} from="up">
                <div
                  className="rounded-lg p-5"
                  style={{
                    background: "var(--glass-bg)",
                    border: "1px solid var(--glass-border)",
                    backdropFilter: "blur(var(--glass-blur))",
                  }}
                >
                  <div className="flex items-center gap-2">
                    <code
                      className="text-sm font-bold"
                      style={{ color: "var(--accent-primary)" }}
                    >
                      {b.name}
                    </code>
                    <span
                      className="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
                      style={{
                        background: "var(--bg-elevated)",
                        color: "var(--text-muted)",
                      }}
                    >
                      {b.kind}
                    </span>
                  </div>
                  <div
                    className="mt-2 text-sm leading-relaxed"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    {b.body}
                  </div>
                </div>
              </MotionInView>
            ))}
          </div>
        </div>
      </section>

      {/* Where we are going */}
      <section className="px-6 py-24">
        <div className="mx-auto max-w-3xl">
          <MotionInView from="up">
            <div
              className="mb-3 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider"
              style={{
                borderColor: "var(--border-default)",
                color: "var(--accent-secondary)",
                background: "var(--glass-bg)",
              }}
            >
              <Target size={12} />
              Where we are going
            </div>
            <h2
              className="mt-3 text-3xl font-bold tracking-tight md:text-4xl"
              style={{ color: "var(--text-primary)", lineHeight: 1.15 }}
            >
              A platform that gets out of your way.
            </h2>
            <div
              className="prose-article mt-6"
              style={{ color: "var(--text-secondary)" }}
            >
              <p>
                The agentic-quant space is moving fast. We are betting that
                three trends will define the next five years. First, that
                hash-locked spec versioning will become table stakes for any
                trading system that gets audited (it is becoming so already).
                Second, that the offline-online drift problem in RL will be
                solved structurally (pipelines) and not by clever evaluation
                tricks. Third, that the platforms that win will be the ones
                that ship the boring infrastructure (identity, tenancy,
                audit, observability) as managed defaults — and let
                practitioners focus on the parts that are actually hard.
              </p>
              <p>
                That is the AQP plan. We are building it in public.
              </p>
            </div>
          </MotionInView>
        </div>
      </section>

      <CallToActionBlock
        eyebrow="Get involved"
        title="Try the platform. Read the source. File a PR."
        subtitle="Free tier forever. Source-available engine. Community Discord. We read every issue."
        primaryCta={{ label: "Start free", href: "/signup" }}
        secondaryCta={{
          label: "Clone on GitHub",
          href: "https://github.com/aqp-fund/aqp",
          external: true,
        }}
      />
    </>
  );
}

const BOUNDARIES = [
  {
    name: "aqp",
    kind: "core",
    body: "Quant runtime: agents, RL, backtest, data, persistence, tasks. Where the platform actually does work.",
  },
  {
    name: "aqp_control_plane",
    kind: "control plane",
    body: "Workload lifecycle + /manage/* API + provider adapters (docker, k8s, AWS, Azure, GCP, Cloudflare).",
  },
  {
    name: "aqp_platform_core",
    kind: "shared",
    body: "Value types, ABCs, auth/resource filters, topology, dependency-light workload contracts.",
  },
  {
    name: "aqp_client",
    kind: "frontend",
    body: "Vite + React 19 + Tailwind 4 operator UI for local power users. The fast-iteration cockpit.",
  },
  {
    name: "aqp_ui",
    kind: "frontend",
    body: "Cloud-hosted Next.js PaaS frontend at app.aqp.fund. Multi-tenant. Dual Auth0 + Entra identity.",
  },
  {
    name: "aqp_admin",
    kind: "frontend",
    body: "Internal admin (managed services + company accounts). Audit-first. Mirrors the control-plane boundary.",
  },
  {
    name: "aqp_ide",
    kind: "tools",
    body: "Theia 1.72 + 6 AQP compile-time extensions + MCP-driven research copilot. The dev environment.",
  },
  {
    name: "aqp_cli",
    kind: "tools",
    body: "Standalone operator CLI. RFC 8628 device flow + OS keyring. HTTP-only against the control plane.",
  },
  {
    name: "aqp_bots",
    kind: "domain",
    body: "Bot entities (TradingBot / ResearchBot) and their templates. The smallest deployable unit.",
  },
  {
    name: "aqp_rl",
    kind: "domain",
    body: "RL stack: RLRuntime, RLExperimentSpec, RLComponent metaclass, FinRL-X pipeline, Iceberg trajectories.",
  },
  {
    name: "aqp_models",
    kind: "domain",
    body: "ML model factory, feature engineering, AlphaBacktestExperiment, walk-forward, custom serving (Ollama / vLLM).",
  },
  {
    name: "aqp_index",
    kind: "ssot",
    body: "Single source of truth for project orientation. Curator-only writes. The map of the codebase.",
  },
];
