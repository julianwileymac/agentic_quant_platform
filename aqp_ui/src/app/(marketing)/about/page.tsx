import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "About",
  description:
    "AQP is the agentic quant platform built by quants for quants. Cloud-hosted, multi-tenant, never closed-source.",
};

export const dynamic = "force-static";
export const revalidate = 86400;

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-20">
      <h1 className="text-4xl font-bold" style={{ color: "var(--text-primary)" }}>
        About AQP
      </h1>
      <p className="mt-6 text-base leading-relaxed" style={{ color: "var(--text-secondary)" }}>
        The Agentic Quant Platform is the trading harness you would have built
        for yourself if you had a year of weekends. We took every primitive a
        serious quant desk needs — hierarchical RAG over an alpha library,
        hash-locked agent specs, twelve backtest engines under one capability
        dispatcher, paper trading on Alpaca / IBKR / Tradier, RL training with
        Iceberg-backed trajectories — and made them composable, auditable, and
        multi-tenant by default.
      </p>
      <h2 className="mt-12 text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
        Our boundary
      </h2>
      <p className="mt-4 text-base leading-relaxed" style={{ color: "var(--text-secondary)" }}>
        AQP is cloud-hosted (this site), local-installable (the open-source AQP
        engine), and never closed-source. Your data lives in your tenant. Your
        brokerage credentials live in your vault. Your strategies are immutable
        hash-locked spec versions you can replay at any point.
      </p>
      <h2 className="mt-10 text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
        Our principles
      </h2>
      <ul className="mt-4 space-y-3 text-base leading-relaxed" style={{ color: "var(--text-secondary)" }}>
        <li>
          <strong style={{ color: "var(--text-primary)" }}>Spec runtimes over scripts.</strong> Every
          run produces an immutable, hash-locked version row. Replay is a
          first-class operation.
        </li>
        <li>
          <strong style={{ color: "var(--text-primary)" }}>Boundaries over monoliths.</strong> Eight
          first-class subpackages, each with its own AGENTS.md contract.
        </li>
        <li>
          <strong style={{ color: "var(--text-primary)" }}>Tenancy is plumbing, not bolted on.</strong>{" "}
          Four tenancy strategies, RLS by default, schema-per-tenant or
          db-per-enterprise on demand.
        </li>
        <li>
          <strong style={{ color: "var(--text-primary)" }}>Auditable by construction.</strong>{" "}
          Every mutating operation writes a structured audit ledger row BEFORE
          the action.
        </li>
      </ul>
    </div>
  );
}
