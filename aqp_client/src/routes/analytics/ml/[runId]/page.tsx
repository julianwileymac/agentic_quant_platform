import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { DistributionOverlay } from "@/components/analytics/DistributionOverlay";
import { PageContainer } from "@/components/shell/PageContainer";
import {
  type DistributionOverlayResponse,
  getDistributionOverlay,
} from "@/lib/api/analytics";

/**
 * Drift + distribution overlay view for an ML test run. Reads the
 * staged ``{actual, predicted}`` payload from sessionStorage so the
 * page is reusable across the various ``ml_test_tasks`` consumers
 * (A/B, batch slice, perturbation sweep).
 */
export function MlAnalyticsRoute() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId ?? "";
  const [overlay, setOverlay] = useState<DistributionOverlayResponse | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      const raw = sessionStorage.getItem(`aqp.analytics.ml.${runId}`);
      if (!raw) {
        setError(
          "No ML test payload staged for this run. Re-open the ML test page to populate it.",
        );
        setLoading(false);
        return;
      }
      const payload = JSON.parse(raw) as {
        actual: number[];
        predicted: number[];
        bins?: number;
      };
      getDistributionOverlay({
        actual: payload.actual,
        predicted: payload.predicted,
        ...(payload.bins !== undefined ? { bins: payload.bins } : {}),
      })
        .then(setOverlay)
        .catch((err) =>
          setError(err instanceof Error ? err.message : String(err)),
        )
        .finally(() => setLoading(false));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setLoading(false);
    }
  }, [runId]);

  return (
    <PageContainer
      title={`ML test — ${runId.slice(0, 8) || "run"}`}
      subtitle="Distribution overlays, drift heatmaps, perturbation sweeps"
    >
      {loading ? (
        <p className="text-xs text-[var(--text-secondary)]">Loading…</p>
      ) : error ? (
        <p className="text-xs text-[var(--neg-fg)]">{error}</p>
      ) : (
        <section>
          <h3 className="mb-2 text-sm font-semibold">Distribution overlay</h3>
          <DistributionOverlay data={overlay} />
        </section>
      )}
    </PageContainer>
  );
}

export default MlAnalyticsRoute;
