/**
 * /onboarding/researcher — Tier-R guided flow (Phase 5 plan section 9).
 *
 * Walks a non-developer researcher through: pick template → fill form
 * → review budget → trigger first sync. SLO: end-to-end in <15 min
 * with zero CLI usage.
 */
import { useState } from "react";
import { ConnectorCatalogBrowser } from "../../../components/data/connectors/ConnectorCatalogBrowser";

const STEPS = [
  { key: "pick", label: "1. Pick a template" },
  { key: "configure", label: "2. Configure" },
  { key: "review", label: "3. Review budget" },
  { key: "go", label: "4. Go live" },
];

export default function ResearcherOnboardingPage(): JSX.Element {
  const [active, setActive] = useState<number>(0);
  return (
    <main className="mx-auto max-w-5xl space-y-4 p-6">
      <header>
        <h1 className="text-2xl font-semibold">Researcher onboarding</h1>
        <p className="text-sm text-gray-600">
          End-to-end self-service ingestion in &lt;15 minutes. No CLI required.
        </p>
      </header>
      <nav className="flex items-center gap-2">
        {STEPS.map((step, idx) => (
          <button
            key={step.key}
            onClick={() => setActive(idx)}
            className={`rounded px-3 py-1 text-sm ${
              idx === active ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-700"
            }`}
          >
            {step.label}
          </button>
        ))}
      </nav>
      <section className="rounded border p-4">
        {active === 0 && (
          <div className="space-y-2">
            <p className="text-sm text-gray-600">
              Browse the catalog and pick the vendor you want to ingest from.
            </p>
            <ConnectorCatalogBrowser />
          </div>
        )}
        {active === 1 && (
          <p className="text-sm text-gray-600">
            Fill in the per-template parameters on the Create-Connection
            page. Secrets resolve through your BYOK key — never paste them
            here.
          </p>
        )}
        {active === 2 && (
          <p className="text-sm text-gray-600">
            The pre-flight reservation against your rate-limit budget runs
            on submit; if you don&apos;t have enough tokens, the wizard
            shows the exact remaining-budget message before any vendor call
            happens.
          </p>
        )}
        {active === 3 && (
          <p className="text-sm text-gray-600">
            Once approved, the Airbyte connection appears in
            /data/discovery and the first sync runs on schedule. Use
            /data/lineage to watch the bronze → silver → gold flow.
          </p>
        )}
      </section>
    </main>
  );
}
