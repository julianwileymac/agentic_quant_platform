import type { Metadata } from "next";
import Link from "next/link";
import { Check, X } from "lucide-react";

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

export default function PricingPage() {
  return (
    <div className="mx-auto max-w-7xl px-6 py-20">
      <div className="mb-16 text-center">
        <h1 className="text-4xl font-bold tracking-tight" style={{ color: "var(--text-primary)" }}>
          Pricing built for quants
        </h1>
        <p className="mt-3 text-base" style={{ color: "var(--text-secondary)" }}>
          Free for individuals, fair for teams, flexible for enterprises.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
        {TIERS.map((tier) => (
          <TierCard key={tier.name} tier={tier} />
        ))}
      </div>

      <FaqSection />
    </div>
  );
}

function TierCard({ tier }: { tier: Tier }) {
  return (
    <div
      className="flex flex-col rounded-lg border p-6"
      style={{
        borderColor: tier.highlight ? "var(--accent-primary)" : "var(--border-default)",
        background: "var(--bg-elevated)",
      }}
    >
      <div className="mb-4">
        <div className="text-sm font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
          {tier.name}
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          <span className="text-3xl font-bold" style={{ color: "var(--text-primary)" }}>
            {tier.price}
          </span>
          <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
            {tier.cadence}
          </span>
        </div>
        <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
          {tier.description}
        </p>
      </div>

      <ul className="my-6 flex flex-1 flex-col gap-2 text-sm">
        {tier.features.map((feature) => (
          <li
            key={feature.label}
            className="flex items-start gap-2"
            style={{ color: feature.included ? "var(--text-primary)" : "var(--text-muted)" }}
          >
            {feature.included ? (
              <Check size={16} style={{ color: "var(--pos-fg)", flexShrink: 0, marginTop: 2 }} />
            ) : (
              <X size={16} style={{ color: "var(--text-muted)", flexShrink: 0, marginTop: 2 }} />
            )}
            <span>{feature.label}</span>
          </li>
        ))}
      </ul>

      <Link
        href={tier.cta.href}
        className="rounded-md px-4 py-2 text-center text-sm font-semibold"
        style={{
          background: tier.highlight ? "var(--accent-primary)" : "transparent",
          border: tier.highlight ? "none" : "1px solid var(--border-default)",
          color: tier.highlight ? "white" : "var(--text-primary)",
        }}
      >
        {tier.cta.label}
      </Link>
    </div>
  );
}

const FAQ = [
  {
    q: "Do I need a credit card to start?",
    a: "No. The Free tier is forever-free and doesn't require a credit card.",
  },
  {
    q: "Can I bring my own brokerage keys?",
    a: "Yes. All paid tiers support BYOK (Alpaca, Interactive Brokers, Tradier, TradeStation, Schwab, ETrade, Binance, Coinbase, Kraken, OKX). Keys are envelope-encrypted in our vault and never returned to your browser.",
  },
  {
    q: "How is data isolated between tenants?",
    a: "Free and Pro share schema with row-level security (Postgres RLS). Team uses schema-per-tenant. Enterprise uses database-per-enterprise. All three strategies are first-class in the platform — no migration required to move between tiers.",
  },
  {
    q: "Can my company sign in with Entra ID?",
    a: "Yes. The Enterprise tier supports Microsoft Entra ID enterprise SSO. We never auto-provision your tenant from a raw tenant ID — an AQP super-admin approves your tenant link explicitly via the EntraTenantLink flow.",
  },
];

function FaqSection() {
  return (
    <div className="mx-auto mt-24 max-w-3xl">
      <h2 className="text-center text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
        Frequently asked
      </h2>
      <div className="mt-8 space-y-4">
        {FAQ.map(({ q, a }) => (
          <div
            key={q}
            className="rounded-md border p-4"
            style={{ borderColor: "var(--border-default)", background: "var(--bg-elevated)" }}
          >
            <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              {q}
            </div>
            <div className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
              {a}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
