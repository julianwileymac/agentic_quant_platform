"use client";

import { useRouter } from "next/navigation";
import { message } from "antd";

import { StrategyForm } from "@/components/strategy/StrategyForm";

export default function NewStrategyPage() {
  const router = useRouter();
  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
          New strategy
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          Edit the recipe in the form (or raw YAML) and save. Each save creates
          a new hash-locked version in <code>paper_recipe_spec_versions</code>.
        </p>
      </header>

      <StrategyForm
        initialJson={{
          session: { name: "", dry_run: false, initial_cash: 100_000 },
          broker: {
            class: "AlpacaBrokerage",
            module_path: "aqp.providers.alpaca",
            credentials_ref: "",
            kwargs: {},
          },
          feed: { class: "AlpacaFeed", module_path: "aqp.providers.alpaca", kwargs: {} },
          strategy: { class: "MeanReversion", module_path: "aqp.strategies.mean_rev", kwargs: {} },
          risk: { daily_loss_limit: 500, drawdown_limit: 5 },
        }}
        onSubmit={async ({ yamlText, json }) => {
          const res = await fetch("/api/strategies", {
            method: "POST",
            credentials: "include",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ yaml: yamlText, recipe: json }),
          });
          if (!res.ok) {
            message.error(`Save failed: ${res.status}`);
            return;
          }
          const created = (await res.json()) as { id: string };
          message.success("Strategy saved");
          router.push(`/strategies/${created.id}`);
        }}
      />
    </div>
  );
}
