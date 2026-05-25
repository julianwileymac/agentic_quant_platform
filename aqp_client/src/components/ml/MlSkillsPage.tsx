import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { MlApi, type MlSkillSummary } from "@/lib/api/ml";

/**
 * Initial MLOps skill library page.
 *
 * Lists every registered `MLSkillSpec` (in-memory + YAML at
 * `aqp_models/configs/skills/`), exposes the spec hash so operators
 * can confirm replay-determinism, and lets them queue a run via the
 * thin POST `/ml/skills/{name}/run` REST surface. Tighter UX (live
 * progress stream, per-step descriptors) follows in a sibling PR; this
 * is the canvas the report's "Skill codification + Rules" describes.
 */
export function MlSkillsPage() {
  const [skills, setSkills] = useState<MlSkillSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    MlApi.skills()
      .then((rows) => {
        if (!cancelled) {
          setSkills(rows);
          setError(null);
        }
      })
      .catch((exc: Error) => {
        if (!cancelled) {
          setError(exc.message ?? "failed to load skills");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleRun = async (name: string) => {
    try {
      const result = await MlApi.runSkill(name, { inputs: {} });
      // eslint-disable-next-line no-alert
      window.alert(`queued ${name}: ${result.task_id}`);
    } catch (exc) {
      // eslint-disable-next-line no-alert
      window.alert(`failed to queue ${name}: ${(exc as Error).message}`);
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold">MLOps Skills</h1>
        <p className="text-muted-foreground text-sm">
          Hash-locked <code>MLSkillSpec</code> bundles composing the
          agent-facing interfaces (Predictor / Forecaster / Classifier
          / Segmenter / Analyzer). Each run snapshots the spec into{" "}
          <code>ml_skill_versions</code> and writes a{" "}
          <code>ml_skill_runs</code> ledger row.
        </p>
      </header>

      {error ? (
        <div className="rounded border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="text-sm text-muted-foreground">Loading skills…</div>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-left text-muted-foreground">
            <tr>
              <th className="px-2 py-1">Name</th>
              <th className="px-2 py-1">Kind</th>
              <th className="px-2 py-1">Steps</th>
              <th className="px-2 py-1">Annotations</th>
              <th className="px-2 py-1">Spec hash</th>
              <th className="px-2 py-1 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {skills.map((s) => (
              <tr key={s.name} className="border-t">
                <td className="px-2 py-1 font-mono">{s.name}</td>
                <td className="px-2 py-1">{s.kind}</td>
                <td className="px-2 py-1 tabular-nums">{s.n_steps}</td>
                <td className="px-2 py-1">{s.annotations.join(", ")}</td>
                <td className="px-2 py-1 font-mono text-xs">
                  {s.spec_hash.slice(0, 12)}…
                </td>
                <td className="px-2 py-1 text-right">
                  <Button size="sm" onClick={() => handleRun(s.name)}>
                    Run
                  </Button>
                </td>
              </tr>
            ))}
            {skills.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-2 py-4 text-center text-muted-foreground">
                  No skills registered yet. Drop a YAML under{" "}
                  <code>aqp_models/configs/skills/</code> to add one.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      )}
    </div>
  );
}
