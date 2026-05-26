import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Check, Sparkles, X } from "lucide-react";

import { CallToActionBlock } from "@/components/marketing/CallToActionBlock";
import {
  ComparisonTable,
  type ComparisonCell,
} from "@/components/marketing/ComparisonTable";
import { FaqAccordion } from "@/components/marketing/FaqAccordion";
import { Hero } from "@/components/marketing/Hero";
import { MotionInView } from "@/components/marketing/MotionInView";
import { SectionHeader } from "@/components/marketing/SectionHeader";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "Simple, transparent pricing for the Agentic Quant Platform. Free for individual quants, paid tiers for teams and enterprises.",
};

export const dynamic = "force-static";
export const revalidate = 3600;

interface Tier {
  name: string;
  price: string;
  cadence: string;
  description: string;
  cta: { label: string; href: string };
  highlight?: boolean;
  features: { included: boolean; label: string }[];
}

const TIERS: Tier[] = [
  {
    name: "Free",
    price: "$0",
    cadence: "forever",
    description: "Everything an individual quant needs to ship one strategy.",
    cta: { label: "Start free", href: "/signup" },
    features: [
      { included: true, label: "1 workspace, 3 projects" },
      { included: true, label: "1 paper-trading strategy at a time" },
      { included: true, label: "Bring your own brokerage (Alpaca paper)" },
      { included: true, label: "10 GB Iceberg, 1 GB cache" },
      { included: true, label: "Community support" },
      { included: false, label: "Live trading" },
      { included: false, label: "Custom alpha agents" },
    ],
  },
  {
    name: "Pro",
    price: "$99",
    cadence: "per user / month",
    description:
      "For serious quants running ML-driven alphas and live paper trading.",
    cta: { label: "Start free trial", href: "/signup?tier=pro" },
    highlight: true,
    features: [
      { included: true, label: "Unlimited strategies and backtests" },
      { included: true, label: "Live paper trading on Alpaca, IBKR, Tradier" },
      { included: true, label: "ML training with vLLM + Ollama" },
      { included: true, label: "AlphaResearcher + StrategyExecutor agents" },
      { included: true, label: "200 GB Iceberg, 25 GB cache" },
      { included: true, label: "Email + chat support" },
      { included: false, label: "Live trading capital" },
    ],
  },
  {
    name: "Team",
    price: "$499",
    cadence: "per seat / month",
    description: "For desks of 3+ quants collaborating on shared alpha.",
    cta: { label: "Start free trial", href: "/signup?tier=team" },
    features: [
      { included: true, label: "Everything in Pro" },
      { included: true, label: "Live trading with risk limits" },
      { included: true, label: "Shared workspaces + ownership graph" },
      { included: true, label: "SOC 2 audit logs" },
      { included: true, label: "Schema-per-tenant data isolation" },
      { included: true, label: "Priority support, 4h SLA" },
    ],
  },
  {
    name: "Enterprise",
    price: "Custom",
    cadence: "talk to sales",
    description:
      "Dedicated database, SAML / SCIM, on-prem option, enterprise procurement.",
    cta: { label: "Contact sales", href: "/legal/contact" },
    features: [
      { included: true, label: "Everything in Team" },
      { included: true, label: "Microsoft Entra ID enterprise SSO" },
      { included: true, label: "Database-per-enterprise tenancy" },
      { included: true, label: "Bring your own Vault / KMS" },
      { included: true, label: "Custom DPA + BAA" },
      { included: true, label: "24/7 support, 1h SLA" },
      { included: true, label: "Dedicated solutions engineer" },
    ],
  },
];

const COMPARE_COLUMNS = [
  { name: "Free", tagline: "$0 forever" },
  { name: "Pro", tagline: "$99 / user / mo", highlight: true },
  { name: "Team", tagline: "$499 / seat / mo" },
  { name: "Enterprise", tagline: "Custom" },
];

const COMPARE_ROWS: { label: string; group?: string; cells: ComparisonCell[] }[] =
  [
    { group: "Strategies & backtesting", label: "Strategies (active)", cells: ["1", "Unlimited", "Unlimited", "Unlimited"] },
    { group: "Strategies & backtesting", label: "Backtest engines (9 total)", cells: ["3", true, true, true] },
    { group: "Strategies & backtesting", label: "Walk-forward + param sweeps", cells: [false, true, true, true] },
    { group: "Strategies & backtesting", label: "RL Lab access", cells: ["Read-only", true, true, true] },
    { group: "Strategies & backtesting", label: "Optimal control (HJB) policies", cells: [false, true, true, true] },

    { group: "Trading", label: "Paper trading", cells: ["Alpaca paper", true, true, true] },
    { group: "Trading", label: "Live trading", cells: [false, false, true, true] },
    { group: "Trading", label: "BYOK broker credentials", cells: ["1", "All 10", "All 10", "All 10"] },
    { group: "Trading", label: "Step-up MFA on destructive actions", cells: [true, true, true, true] },

    { group: "Storage", label: "Iceberg storage", cells: ["10 GB", "200 GB", "2 TB", "Custom"] },
    { group: "Storage", label: "Cache (Redis)", cells: ["1 GB", "25 GB", "200 GB", "Custom"] },
    { group: "Storage", label: "RAG corpora (papers / regulatory / code)", cells: [true, true, true, true] },

    { group: "Identity & tenancy", label: "Auth0 self-signup", cells: [true, true, true, "-"] },
    { group: "Identity & tenancy", label: "Microsoft Entra B2B SSO", cells: [false, false, false, true] },
    { group: "Identity & tenancy", label: "Tenancy isolation", cells: ["Shared+RLS", "Shared+RLS", "Schema-per-tenant", "DB-per-enterprise"] },
    { group: "Identity & tenancy", label: "Bring your own KMS / Vault", cells: [false, false, false, true] },

    { group: "Support", label: "Community Discord", cells: [true, true, true, true] },
    { group: "Support", label: "Email + chat support", cells: [false, true, true, true] },
    { group: "Support", label: "SLA", cells: ["-", "Best effort", "4h", "1h"] },
    { group: "Support", label: "Dedicated solutions engineer", cells: [false, false, false, true] },
  ];

const FAQ_ITEMS = [
  {
    question: "Do I need a credit card to start?",
    answer:
      "No. The Free tier is forever-free and doesn't require a credit card. Pro and Team paid tiers offer a 14-day free trial.",
  },
  {
    question: "Can I bring my own brokerage keys?",
    answer:
      "Yes. All paid tiers support BYOK for Alpaca, Interactive Brokers, Tradier, TradeStation, Schwab, ETrade, Binance, Coinbase, Kraken, OKX. Keys are envelope-encrypted (Vault Transit in prod) and never returned to your browser. Create and delete operations require step-up MFA per RFC 9470.",
  },
  {
    question: "How is data isolated between tenants?",
    answer:
      "Free and Pro share a Postgres schema with row-level security. Team uses schema-per-tenant. Enterprise uses database-per-enterprise. All three strategies are first-class in the platform — no migration required to move between tiers.",
  },
  {
    question: "Can my company sign in with Entra ID?",
    answer:
      "Yes, on the Enterprise tier. We never auto-provision your tenant from a raw Entra tenant ID — an AQP super-admin approves your tenant link explicitly via the EntraTenantLink wizard. This prevents silent multi-tenant cross-pollination.",
  },
  {
    question: "What's the difference between Cloud and Self-Hosted?",
    answer:
      "Cloud is the same engine plus managed identity, tenancy, Cloudflare edge, audit retention, and support SLAs. Self-hosted is the source-available engine you run on your own hardware. You can migrate from Cloud to Self-Hosted (or vice versa) without rewriting code — the engine is the same source tree.",
  },
  {
    question: "Do you offer a non-profit / academic discount?",
    answer:
      "Yes — verified academic researchers and non-profits get 50% off Pro and Team tiers. Reach out via /legal/contact with documentation of your affiliation.",
  },
];

export default function PricingPage() {
  return (
    <>
      <Hero
        eyebrow="Pricing"
        eyebrowIcon={Sparkles}
        title="Simple, transparent pricing for quants."
        titleHighlight="transparent pricing"
        subtitle="Free for individuals, fair for teams, flexible for enterprises. No hidden per-API-call charges. No surprise bills. Bring your own LLM provider if you want to."
        primaryCta={{ label: "Start free", href: "/signup" }}
        secondaryCta={{ label: "Talk to sales", href: "/legal/contact" }}
      />

      {/* Tier cards */}
      <section className="px-6 py-12">
        <div className="mx-auto max-w-7xl">
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
            {TIERS.map((tier, i) => (
              <MotionInView key={tier.name} delay={i * 0.08} from="up">
                <TierCard tier={tier} />
              </MotionInView>
            ))}
          </div>
        </div>
      </section>

      {/* Comparison matrix */}
      <section
        className="px-6 py-24"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Compare tiers"
            title="Pick the row that matters most to you"
            subtitle="Every feature, every tier, side by side."
          />
          <ComparisonTable columns={COMPARE_COLUMNS} rows={COMPARE_ROWS} />
        </div>
      </section>

      {/* FAQ */}
      <section className="px-6 py-20">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="FAQ"
            title="Frequently asked"
          />
          <FaqAccordion items={FAQ_ITEMS} />
        </div>
      </section>

      <CallToActionBlock
        eyebrow="Get started"
        title="Try AQP free forever. Upgrade only when you scale."
        subtitle="14-day free trial on Pro and Team. No credit card to start. Cancel any time."
        primaryCta={{ label: "Create free account", href: "/signup" }}
        secondaryCta={{ label: "Contact sales", href: "/legal/contact" }}
      />
    </>
  );
}

function TierCard({ tier }: { tier: Tier }) {
  return (
    <div
      className="relative flex h-full flex-col overflow-hidden rounded-xl p-6 transition-transform hover:-translate-y-1"
      style={{
        background: tier.highlight ? "var(--glass-bg-strong)" : "var(--glass-bg)",
        border: `1px solid ${
          tier.highlight ? "var(--accent-primary)" : "var(--glass-border)"
        }`,
        backdropFilter: "blur(var(--glass-blur))",
        boxShadow: tier.highlight
          ? "var(--shadow-glow-primary)"
          : "var(--shadow-card)",
      }}
    >
      {tier.highlight ? (
        <div
          className="absolute right-4 top-4 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
          style={{
            background: "var(--accent-primary)",
            color: "white",
          }}
        >
          Most popular
        </div>
      ) : null}
      <div>
        <div
          className="text-xs font-bold uppercase tracking-wider"
          style={{ color: "var(--text-muted)" }}
        >
          {tier.name}
        </div>
        <div className="mt-3 flex items-baseline gap-2">
          <span
            className="text-4xl font-bold"
            style={{ color: "var(--text-primary)" }}
          >
            {tier.price}
          </span>
          <span
            className="text-xs"
            style={{ color: "var(--text-secondary)" }}
          >
            {tier.cadence}
          </span>
        </div>
        <p
          className="mt-3 text-sm leading-relaxed"
          style={{ color: "var(--text-secondary)" }}
        >
          {tier.description}
        </p>
      </div>

      <ul className="my-6 flex flex-1 flex-col gap-2 text-sm">
        {tier.features.map((feature) => (
          <li
            key={feature.label}
            className="flex items-start gap-2"
            style={{
              color: feature.included ? "var(--text-primary)" : "var(--text-muted)",
            }}
          >
            {feature.included ? (
              <Check
                size={14}
                style={{
                  color: "var(--pos-fg)",
                  flexShrink: 0,
                  marginTop: 4,
                }}
              />
            ) : (
              <X
                size={14}
                style={{
                  color: "var(--text-muted)",
                  flexShrink: 0,
                  marginTop: 4,
                }}
              />
            )}
            <span>{feature.label}</span>
          </li>
        ))}
      </ul>

      <Link
        href={tier.cta.href}
        className="group inline-flex items-center justify-center gap-2 rounded-md px-4 py-2.5 text-center text-sm font-semibold transition-transform hover:scale-[1.02]"
        style={{
          background: tier.highlight ? "var(--accent-primary)" : "transparent",
          border: tier.highlight ? "none" : "1px solid var(--border-default)",
          color: tier.highlight ? "white" : "var(--text-primary)",
          boxShadow: tier.highlight ? "var(--shadow-glow-primary)" : undefined,
        }}
      >
        {tier.cta.label}
        <ArrowRight
          size={14}
          className="transition-transform group-hover:translate-x-0.5"
        />
      </Link>
    </div>
  );
}
