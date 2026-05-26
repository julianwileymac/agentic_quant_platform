import type { Metadata } from "next";
import {
  Activity,
  Cloud,
  Globe,
  KeyRound,
  Lock,
  Network,
  Server,
  ShieldCheck,
  Users,
  Zap,
} from "lucide-react";

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
import { MotionInView } from "@/components/marketing/MotionInView";
import { MultiTenantIllustration } from "@/components/marketing/illustrations/MultiTenantIllustration";
import { ProductNav } from "@/components/marketing/ProductNav";
import { SectionHeader } from "@/components/marketing/SectionHeader";
import { StatStrip } from "@/components/marketing/StatStrip";

export const metadata: Metadata = {
  title: "Cloud Platform",
  description:
    "Cloud-hosted, multi-tenant PaaS at app.aqp.fund. Dual Auth0 + Microsoft Entra identity. Four TenancyStrategy isolation modes. BYOK for every brokerage. Step-up MFA on every destructive action.",
};

export const dynamic = "force-static";
export const revalidate = 3600;

const NAV_ITEMS = [
  { id: "overview", label: "Overview" },
  { id: "identity", label: "Identity" },
  { id: "tenancy", label: "Tenancy" },
  { id: "security", label: "Security" },
  { id: "edge", label: "Edge" },
  { id: "compare", label: "Cloud vs Self-Hosted" },
  { id: "faq", label: "FAQ" },
];

export default function CloudPage() {
  return (
    <>
      <Hero
        eyebrow="Cloud Platform"
        eyebrowIcon={Cloud}
        title="The Agentic Quant Platform, fully managed."
        titleHighlight="fully managed"
        subtitle="Hosted at app.aqp.fund behind Cloudflare. Dual identity for B2C (Auth0) and B2B (Microsoft Entra via EntraTenantLink). Multi-tenant by default with four isolation strategies. BYOK for every brokerage. The same engine you can self-host, with the boring parts (identity, tenancy, edge, audit) done for you."
        primaryCta={{ label: "Start free", href: "/signup" }}
        secondaryCta={{ label: "See pricing", href: "/pricing" }}
        illustration={
          <div
            className="overflow-hidden rounded-xl p-2"
            style={{
              background: "var(--glass-bg)",
              border: "1px solid var(--glass-border)",
              backdropFilter: "blur(var(--glass-blur))",
            }}
          >
            <MultiTenantIllustration />
          </div>
        }
      />

      <ProductNav items={NAV_ITEMS} />

      <StatStrip
        stats={[
          { value: 4, label: "Tenancy strategies", tone: "primary" },
          { value: 2, label: "Identity providers", tone: "secondary" },
          { value: 10, label: "BYOK brokers", tone: "tertiary" },
          { value: 6, label: "Halt endpoints", tone: "warn" },
        ]}
      />

      {/* Overview */}
      <section id="overview" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="What's managed for you"
            title="Identity, tenancy, edge, audit — solved."
            subtitle="The AQP cloud platform handles the production boilerplate that takes most quant teams six months to get right. You stay focused on alpha."
          />
          <FeatureGrid columns={3}>
            <FeatureCard
              icon={Users}
              tone="primary"
              title="Dual identity"
              body="Auth0 Organizations for B2C self-signup. Microsoft Entra ID for B2B enterprise SSO via the EntraTenantLink wizard."
            />
            <FeatureCard
              icon={Lock}
              tone="tertiary"
              title="Multi-tenant isolation"
              body="Four TenancyStrategy implementations: shared+RLS, schema-per-tenant, database-per-enterprise, hybrid. Move tiers without code changes."
            />
            <FeatureCard
              icon={KeyRound}
              tone="secondary"
              title="BYOK broker credentials"
              body="Envelope-encrypted in Vault Transit. Step-up MFA on create + delete. Plaintext never returned to the browser."
            />
            <FeatureCard
              icon={Globe}
              tone="warn"
              title="Cloudflare edge"
              body="Three hostnames (aqp.fund, api.aqp.fund, manage.aqp.fund) plus docs.aqp.fund on Pages and status.aqp.fund."
            />
            <FeatureCard
              icon={ShieldCheck}
              tone="primary"
              title="Step-up MFA (RFC 9470)"
              body="Every halt destructive action requires fresh MFA. WWW-Authenticate bubbles to the SPA for popup retry."
            />
            <FeatureCard
              icon={Zap}
              tone="tertiary"
              title="One halt button"
              body="The topbar KillSwitch fans out via Promise.allSettled to six halt endpoints (agents, paper, bots, RL, workflows, portfolio)."
            />
          </FeatureGrid>
        </div>
      </section>

      {/* Identity */}
      <section
        id="identity"
        className="px-6"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <FeatureBreakdown
          eyebrow="Identity"
          tone="primary"
          title="One identity layer for both B2C and B2B."
          body="The same IdentityProvider chain serves Auth0 self-signup (Free + Pro), Microsoft Entra enterprise SSO (Enterprise), generic OIDC, Cloudflare Access, and a mock provider for dev. The PKCE state, JWE session cookie, and Authorization Bearer flow are all built in."
          bullets={[
            "Auth0 Organizations for B2C self-signup with optional MFA",
            "Microsoft Entra ID via EntraTenantLink wizard (admin promotes tid → org)",
            "Generic OIDC for self-managed enterprise IdPs",
            "Cloudflare Access for zero-trust internal users (admin surface)",
          ]}
          cta={{ label: "Identity architecture", href: "/docs/identity" }}
          visual={
            <CodeBlock
              filename="auth_flow.md"
              language="markdown"
              code={`# Two paths to the same dashboard

## B2C — Auth0 (Free + Pro tiers)
1. User → /signup
2. ProviderPicker → Auth0 PKCE redirect
3. Auth0 callback → JWE session cookie set
4. Org auto-provisioned from email domain (free) or
   the user's chosen org (pro)
5. /(app)/* → dashboard

## B2B — Entra (Enterprise tier)
1. User → /login with org param
2. ProviderPicker → MSAL Node PKCE redirect
3. Entra callback → claim contains tenant id (tid)
4. EntraTenantLink lookup:
   - active   → auto-provision the Org row, set JWE cookie
   - pending  → "awaiting AQP super-admin approval" screen
   - missing  → "request access" wizard for the org admin
   - revoked  → block + audit
5. /(app)/* → dashboard with org-scoped tenancy headers`}
            />
          }
        />
      </section>

      {/* Tenancy */}
      <section id="tenancy" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Tenancy"
            title="Pool the stateless. Silo the high-risk."
            subtitle="Four TenancyStrategy implementations let you balance cost and isolation per tier. Migration between strategies is first-class — no code changes required."
          />
          <div className="grid gap-6 lg:grid-cols-2">
            {TENANCY_STRATEGIES.map((s, i) => (
              <MotionInView key={s.name} delay={i * 0.1}>
                <div
                  className="h-full rounded-xl p-6"
                  style={{
                    background: "var(--glass-bg)",
                    border: "1px solid var(--glass-border)",
                    backdropFilter: "blur(var(--glass-blur))",
                  }}
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div
                        className="text-xs font-bold uppercase tracking-wider"
                        style={{ color: "var(--accent-primary)" }}
                      >
                        {s.tier}
                      </div>
                      <h3
                        className="mt-2 text-xl font-bold"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {s.name}
                      </h3>
                    </div>
                    <span
                      className="rounded-full px-3 py-1 text-xs font-bold"
                      style={{
                        background: s.intensity === "high" ? "rgba(167,139,250,0.15)" : s.intensity === "med" ? "rgba(96,165,250,0.15)" : "rgba(52,211,153,0.15)",
                        color: s.intensity === "high" ? "#a78bfa" : s.intensity === "med" ? "#60a5fa" : "#34d399",
                      }}
                    >
                      {s.intensity} isolation
                    </span>
                  </div>
                  <p
                    className="mt-3 text-sm leading-relaxed"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    {s.body}
                  </p>
                  <ul className="mt-4 space-y-2 text-sm">
                    {s.points.map((p) => (
                      <li
                        key={p}
                        className="flex items-start gap-2"
                        style={{ color: "var(--text-primary)" }}
                      >
                        <span
                          className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full"
                          style={{ background: "var(--accent-primary)" }}
                        />
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>
              </MotionInView>
            ))}
          </div>
        </div>
      </section>

      {/* Security */}
      <section
        id="security"
        className="px-6 py-24"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Security"
            title="Built for production from day one"
            subtitle="Every destructive action requires fresh MFA. Every audit row is written BEFORE the action. Every multi-tenant query honours row-level security at the database layer."
          />
          <FeatureGrid columns={4}>
            <FeatureCard
              icon={ShieldCheck}
              tone="primary"
              title="Step-up MFA (RFC 9470)"
              body="Kill-switch, broker BYOK CRUD, tenant invites, Terraform apply / destroy — all gated by fresh MFA via the IdP."
            />
            <FeatureCard
              icon={KeyRound}
              tone="secondary"
              title="Envelope-encrypted BYOK"
              body="Per-org backend choice: local (Vault Transit) or cloud KMS (HashiCorp Vault / AWS SM / Azure KV / GCP SM)."
            />
            <FeatureCard
              icon={Lock}
              tone="tertiary"
              title="Row-Level Security"
              body="Postgres RLS DDL on every tenant-scoped table. Session GUC honours the active RequestContext via PEP 567 contextvar."
            />
            <FeatureCard
              icon={Activity}
              tone="warn"
              title="Audit ledger first"
              body="workload_runs, agent_runs_v2, terraform_runs, workflow_runs — every mutating op writes a row BEFORE the call executes."
            />
            <FeatureCard
              icon={Server}
              tone="primary"
              title="Token-exchange delegation"
              body="Agents call MCP over HTTP via RFC 8693 + Auth0 Custom Token Exchange. The on_behalf_of_user is audit-recorded."
            />
            <FeatureCard
              icon={Network}
              tone="tertiary"
              title="CVE pin discipline"
              body="Next.js pinned >=14.2.25 (CVE-2025-29927). Every BFF handler re-checks getSession() — never relies on middleware alone."
            />
            <FeatureCard
              icon={Globe}
              tone="secondary"
              title="No-token-passthrough MCP"
              body="MCP servers mint their own M2M token; outbound calls never reuse the user's access token. Source linter enforces this."
            />
            <FeatureCard
              icon={Zap}
              tone="warn"
              title="Watchdog auto-halt"
              body="Celery beat task scans for stalled agent_runs / paper_runs / RL runs / workflows and halts them. GET /agents/health surfaces snapshots."
            />
          </FeatureGrid>
        </div>
      </section>

      {/* Edge */}
      <section
        id="edge"
        className="px-6"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <FeatureBreakdown
          eyebrow="Cloudflare edge"
          tone="warn"
          title="Five hostnames. One zone. DDoS and TLS sorted."
          body="The AQP cloud platform lives behind a Cloudflare zone with aggressive cache for /_next/static/* and bypass for /api/*. Every hostname terminates TLS at the edge; the origin sees clean traffic only."
          bullets={[
            "aqp.fund + www.aqp.fund — public marketing site (SSR / ISR)",
            "app.aqp.fund — authenticated multi-tenant dashboard",
            "api.aqp.fund — public AQP API (your tenancy headers honoured)",
            "manage.aqp.fund — control plane (workload lifecycle, IdP wiring)",
            "docs.aqp.fund — Docusaurus on Cloudflare Pages",
            "status.aqp.fund — Instatus page (separate zone for degraded-cluster days)",
          ]}
          cta={{ label: "Architecture overview", href: "/docs/architecture" }}
          reverse
          visual={
            <div
              className="rounded-xl p-6"
              style={{
                background: "var(--glass-bg-strong)",
                border: "1px solid var(--glass-border-strong)",
                backdropFilter: "blur(var(--glass-blur))",
              }}
            >
              <div className="space-y-2 font-mono text-sm">
                {[
                  { host: "aqp.fund", role: "marketing site (SSR)" },
                  { host: "app.aqp.fund", role: "authenticated dashboard" },
                  { host: "api.aqp.fund", role: "public API" },
                  { host: "manage.aqp.fund", role: "control plane" },
                  { host: "docs.aqp.fund", role: "Docusaurus on Pages" },
                  { host: "status.aqp.fund", role: "Instatus (separate zone)" },
                ].map((row) => (
                  <div
                    key={row.host}
                    className="flex items-center justify-between rounded-md px-3 py-2"
                    style={{
                      background: "var(--bg-elevated)",
                      border: "1px solid var(--border-default)",
                    }}
                  >
                    <span
                      className="font-bold"
                      style={{ color: "var(--accent-primary)" }}
                    >
                      {row.host}
                    </span>
                    <span
                      className="text-xs"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {row.role}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          }
        />
      </section>

      {/* Cloud vs Self-Hosted */}
      <section id="compare" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Decision aid"
            title="Cloud or Self-Hosted? Same engine."
            subtitle="Pick what fits your operating model. Migrate later without rewriting code — the boundary between cloud and self-hosted is the deployment layer, never the engine."
          />
          <ComparisonTable columns={COMPARE_COLUMNS} rows={COMPARE_ROWS} />
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
            title="Cloud platform questions"
          />
          <FaqAccordion items={FAQ_ITEMS} />
        </div>
      </section>

      <CallToActionBlock
        eyebrow="Ready when you are"
        title="Free for individuals. Fair for teams. Flexible for enterprises."
        subtitle="Start free. Bring your own brokerage. Pay only when you scale."
        primaryCta={{ label: "Start free", href: "/signup" }}
        secondaryCta={{ label: "See pricing", href: "/pricing" }}
      />
    </>
  );
}

const TENANCY_STRATEGIES = [
  {
    tier: "Free + Pro tiers",
    name: "SharedSchemaRLSStrategy",
    intensity: "low" as const,
    body: "Postgres Row-Level Security on every tenant-scoped table. Cheap, fast, audited. The default for most B2C customers.",
    points: [
      "One shared schema with RLS DDL bundle (migration 0063)",
      "Session GUC honours active RequestContext via PEP 567",
      "Cross-tenant queries fail at the DB layer before hitting the agent",
    ],
  },
  {
    tier: "Team tier",
    name: "SchemaPerTenantStrategy",
    intensity: "med" as const,
    body: "Each team gets its own Postgres schema. Better blast-radius isolation while still pooling stateless services.",
    points: [
      "Per-tenant schema with template-based provisioning",
      "Migrations replay against tenant_template schema first",
      "Single connection pool, dynamic SET search_path per request",
    ],
  },
  {
    tier: "Enterprise tier",
    name: "DatabasePerEnterpriseStrategy",
    intensity: "high" as const,
    body: "Each enterprise gets a dedicated Postgres database. The highest blast-radius isolation; supports BYO Vault / KMS.",
    points: [
      "Dedicated DB per enterprise, optionally in a customer-owned region",
      "BYO Vault / KMS for envelope encryption keys",
      "Compatible with custom DPA / BAA contracts",
    ],
  },
  {
    tier: "Hybrid",
    name: "HybridStrategy",
    intensity: "med" as const,
    body: "Mix-and-match per resource kind. Strategy state shared+RLS; production trading logs schema-per-tenant; audit ledger db-per-enterprise.",
    points: [
      "Per-resource-kind dispatch over the four base strategies",
      "Migration paths between strategies are first-class",
      "Lets you scale isolation along the dimensions that need it",
    ],
  },
];

const COMPARE_COLUMNS = [
  { name: "Cloud", tagline: "app.aqp.fund", highlight: true },
  { name: "Self-Hosted", tagline: "Your cluster" },
];

const COMPARE_ROWS: { label: string; group?: string; cells: ComparisonCell[] }[] = [
  { group: "Operations", label: "Hosted at app.aqp.fund", cells: [true, false] },
  { group: "Operations", label: "Cloudflare edge + DDoS", cells: [true, false] },
  { group: "Operations", label: "99.9% uptime SLA (Team+)", cells: [true, "DIY"] },
  { group: "Operations", label: "Auto-managed migrations + upgrades", cells: [true, false] },

  { group: "Identity", label: "Auth0 self-signup", cells: [true, "-"] },
  { group: "Identity", label: "Microsoft Entra B2B SSO", cells: [true, true] },
  { group: "Identity", label: "Bring your own OIDC provider", cells: ["Enterprise", true] },
  { group: "Identity", label: "Cloudflare Access (admin)", cells: [true, true] },

  { group: "Tenancy", label: "Choose tenancy strategy", cells: ["Auto-assigned", "You pick"] },
  { group: "Tenancy", label: "Bring your own KMS / Vault", cells: ["Enterprise", true] },

  { group: "Engine", label: "AgentRuntime / BotRuntime / RLRuntime / WorkflowRuntime", cells: [true, true] },
  { group: "Engine", label: "9 backtest engines", cells: [true, true] },
  { group: "Engine", label: "AQP IDE", cells: [false, true] },
  { group: "Engine", label: "TerraformRuntime for IaC", cells: ["Managed", true] },
];

const FAQ_ITEMS = [
  {
    question: "What does Free actually include?",
    answer:
      "1 workspace + 3 projects, 1 paper-trading strategy at a time, Alpaca paper BYOK, 10 GB Iceberg + 1 GB cache, community support. Everything else (live trading, custom alpha agents, ML training) is on paid tiers. Free is forever-free and doesn't require a credit card.",
  },
  {
    question: "Can I move from Cloud to Self-Hosted later?",
    answer:
      "Yes. The engine is the same source tree (the open AQP repo). Self-hosting means you run docker compose up -d, Kubernetes, or native dev on your own cluster — and you bring your own identity / KMS / Vault. We provide an export tool that bundles your hash-locked spec versions + Iceberg snapshots; you import on the receiving side.",
  },
  {
    question: "How is Entra B2B onboarding different from generic SSO?",
    answer:
      "AQP does not auto-create an Organization row from a raw Entra tenant id (tid). Instead, the first user from an unknown tid triggers a pending EntraTenantLink. An AQP super-admin reviews the request via the EntraTenantLinkWizard and approves; subsequent users from that tid auto-provision into the org. This prevents silent multi-tenant cross-pollination.",
  },
  {
    question: "What happens during a Cloudflare incident?",
    answer:
      "Two layers of safety. (1) status.aqp.fund lives on a separate Cloudflare zone with its own DNS, so the status page stays up even when the main zone is degraded. (2) The control plane and the operator UI tolerate slow API responses gracefully via the React Query retry/backoff schedule; the topbar KillSwitch is reachable offline if a halt is needed.",
  },
  {
    question: "Do you offer dedicated regions?",
    answer:
      "Yes, on the Enterprise tier. The DatabasePerEnterpriseStrategy supports placing the DB in a customer-chosen region (EU, US-East, US-West, AP-South). Compute can be co-located. Reach out for a custom DPA + region commitment.",
  },
];
