import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { type FlowSchema, listAnalysisFlows } from "@/lib/analysis/api";

import { DatasetPicker, type DatasetSelection } from "./DatasetPicker";
import { NamespaceTab } from "./NamespaceTab";

const TAB_ORDER: Array<{
  namespace: string;
  label: string;
  crossLink?: { href: string; label: string };
}> = [
  { namespace: "profiling", label: "Profiling" },
  { namespace: "distribution", label: "Distribution" },
  { namespace: "outlier", label: "Outliers" },
  { namespace: "imputation", label: "Imputation" },
  { namespace: "regression", label: "Regression" },
  { namespace: "time_series", label: "Time Series" },
  {
    namespace: "derivatives",
    label: "Derivatives",
    crossLink: { href: "/options/lab", label: "Options Lab" },
  },
  {
    namespace: "portfolio",
    label: "Portfolio",
    crossLink: { href: "/optimizer", label: "Optimizer" },
  },
  {
    namespace: "factors",
    label: "Factors",
    crossLink: { href: "/factors", label: "Factor Workbench" },
  },
  { namespace: "microstructure", label: "Microstructure" },
];

/**
 * Hybrid `/analysis/lab` surface: dataset-centric tabs as the primary
 * path, with a dedicated `/analysis/lab/composer` route for the
 * XYFlow-driven multi-step pipeline builder.
 *
 * Each tab renders the relevant flow forms via JSON-schema and posts
 * to ``POST /analysis/flows/{flow}/preview``. ``GET /analysis/flows``
 * is fetched once at mount.
 */
export function AnalysisLabPage() {
  const [flows, setFlows] = useState<FlowSchema[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dataset, setDataset] = useState<DatasetSelection>({
    identifier: "",
    limit: 5000,
    columns: [],
  });

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listAnalysisFlows()
      .then((res) => {
        if (cancelled) return;
        setFlows(res);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        toast.error("Could not load /analysis/flows");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const grouped = useMemo(() => {
    const out: Record<string, FlowSchema[]> = {};
    for (const f of flows) {
      const ns = f.namespace || "other";
      if (!out[ns]) out[ns] = [];
      out[ns].push(f);
    }
    return out;
  }, [flows]);

  return (
    <PageContainer
      title="Analysis Lab"
      subtitle="Hash-locked AnalysisSpec + AnalysisRuntime — one place to profile, audit, model, and price every dataset."
      extra={
        <div className="flex items-center gap-2">
          <Badge variant="secondary">{flows.length} flows</Badge>
          <Button asChild size="sm" variant="outline">
            <Link to="/analysis/runs">Run history</Link>
          </Button>
          <Button asChild size="sm">
            <Link to="/analysis/lab/composer">Open Composer →</Link>
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <DatasetPicker value={dataset} onChange={setDataset} />
        {loading ? (
          <p className="text-xs text-[var(--text-secondary)]">Loading flow catalog...</p>
        ) : error ? (
          <p className="text-xs text-[var(--neg-fg)]">{error}</p>
        ) : (
          <Tabs defaultValue={TAB_ORDER[0]!.namespace}>
            <TabsList className="flex-wrap">
              {TAB_ORDER.map((tab) => (
                <TabsTrigger key={tab.namespace} value={tab.namespace}>
                  {tab.label}
                  <span className="ml-1 text-[10px] opacity-60">
                    ({(grouped[tab.namespace] ?? []).length})
                  </span>
                </TabsTrigger>
              ))}
            </TabsList>
            {TAB_ORDER.map((tab) => (
              <TabsContent key={tab.namespace} value={tab.namespace}>
                <NamespaceTab
                  flows={grouped[tab.namespace] ?? []}
                  dataset={dataset}
                  crossLink={tab.crossLink}
                />
              </TabsContent>
            ))}
          </Tabs>
        )}
      </div>
    </PageContainer>
  );
}
