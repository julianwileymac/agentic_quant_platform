import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Changelog",
  description: "Release notes and changes to the Agentic Quant Platform.",
};

export const dynamic = "force-static";
export const revalidate = 3600;

interface Release {
  version: string;
  date: string;
  changes: string[];
}

const RELEASES: Release[] = [
  {
    version: "v0.1.0",
    date: "2026-05-24",
    changes: [
      "Initial cloud-hosted PaaS release",
      "Dual Auth0 (B2C) + Entra (B2B) identity providers",
      "Multi-tenant by default (shared schema RLS / schema-per-tenant / db-per-enterprise)",
      "BYOK broker credentials with envelope encryption (Alpaca, IBKR, Tradier, ...)",
      "Schema-driven strategy editor with YAML round-trip",
      "Real-time WebSocket telemetry for paper runs and market data",
      "Kill-switch fan-out across all six halt endpoints",
    ],
  },
];

export default function ChangelogPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-20">
      <h1 className="text-4xl font-bold" style={{ color: "var(--text-primary)" }}>
        Changelog
      </h1>
      <p className="mt-4 text-base" style={{ color: "var(--text-secondary)" }}>
        Release notes for the AQP cloud platform. Major changes only.
      </p>
      <div className="mt-10 space-y-8">
        {RELEASES.map((release) => (
          <article
            key={release.version}
            className="rounded-md border p-6"
            style={{ borderColor: "var(--border-default)", background: "var(--bg-elevated)" }}
          >
            <div className="flex items-baseline justify-between">
              <h2 className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>
                {release.version}
              </h2>
              <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                {release.date}
              </div>
            </div>
            <ul className="mt-4 ml-6 list-disc space-y-1.5 text-sm" style={{ color: "var(--text-secondary)" }}>
              {release.changes.map((change) => (
                <li key={change}>{change}</li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </div>
  );
}
