import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { DrawdownTable } from "@/components/analytics/DrawdownTable";
import { RollingPanel } from "@/components/analytics/RollingPanel";
import { TearSheetGrid } from "@/components/analytics/TearSheetGrid";
import { UnderwaterPanel } from "@/components/analytics/UnderwaterPanel";
import { PageContainer } from "@/components/shell/PageContainer";
import {
  type PortfolioMetricsResponse,
  type PortfolioRollingResponse,
  getPortfolioMetrics,
  getPortfolioRolling,
} from "@/lib/api/analytics";

/**
 * Server-driven portfolio tearsheet view. Loads returns for the run
 * identified by ``runId`` (the actual returns array would normally
 * come from a backtest / paper / RL run endpoint; we accept it from
 * sessionStorage or a follow-up backend round-trip).
 *
 * For now the page expects callers to pre-stage the returns array
 * under ``sessionStorage[`aqp.analytics.returns.${runId}`]``. A
 * production wiring would replace that with a typed
 * ``getReturnsSeries(runId)`` call to whichever subsystem owns the
 * run.
 */
export function PortfolioAnalyticsRoute() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId ?? "";
  const [metrics, setMetrics] = useState<PortfolioMetricsResponse | null>(null);
  const [rolling, setRolling] = useState<PortfolioRollingResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      const raw = sessionStorage.getItem(`aqp.analytics.returns.${runId}`);
      if (!raw) {
        setError(
          "No returns staged for this run. Re-open the run's overview to populate sessionStorage.",
        );
        setLoading(false);
        return;
      }
      const payload = JSON.parse(raw) as {
        returns: number[];
        index_dates?: string[];
      };
      const baseArgs: { returns: number[]; index_dates?: string[] } = {
        returns: payload.returns,
        ...(payload.index_dates !== undefined ? { index_dates: payload.index_dates } : {}),
      };
      Promise.all([
        getPortfolioMetrics(baseArgs),
        getPortfolioRolling(baseArgs),
      ])
        .then(([m, r]) => {
          setMetrics(m);
          setRolling(r);
        })
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
      title={`Portfolio tearsheet — ${runId.slice(0, 8) || "run"}`}
      subtitle="QuantStats metrics + rolling Sharpe / vol / underwater"
    >
      {loading ? (
        <p className="text-xs text-[var(--text-secondary)]">Loading…</p>
      ) : error ? (
        <p className="text-xs text-[var(--neg-fg)]">{error}</p>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          <section>
            <h3 className="mb-2 text-sm font-semibold">Key metrics</h3>
            <TearSheetGrid data={metrics} />
          </section>

          <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-semibold">Rolling Sharpe</h3>
              <RollingPanel data={rolling} panel="sharpe" />
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold">Rolling volatility</h3>
              <RollingPanel data={rolling} panel="vol" />
            </div>
          </section>

          <section>
            <h3 className="mb-2 text-sm font-semibold">Underwater</h3>
            <UnderwaterPanel data={rolling} />
          </section>

          <section>
            <h3 className="mb-2 text-sm font-semibold">Worst drawdowns</h3>
            <DrawdownTable data={rolling} topN={10} />
          </section>
        </div>
      )}
    </PageContainer>
  );
}

export default PortfolioAnalyticsRoute;
