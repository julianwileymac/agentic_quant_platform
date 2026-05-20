import { Loader2, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";

interface EquityReportDetail {
  id: string;
  vt_symbol: string;
  as_of: string;
  status: string;
  cost_usd: number;
  sections: Record<string, string | Record<string, unknown>>;
  valuation: Record<string, unknown>;
  catalysts: Array<Record<string, unknown>>;
  sensitivity: Record<string, unknown>;
  usage: Record<string, unknown>;
  error?: string | null;
}

export function EquityReportPage() {
  const params = useParams<{ symbol?: string }>();
  const initialSymbol = params.symbol ? decodeURIComponent(params.symbol) : "AAPL.NASDAQ";

  const [vtSymbol, setVtSymbol] = useState(initialSymbol);
  const [asOf, setAsOf] = useState(new Date().toISOString().slice(0, 10));
  const [peers, setPeers] = useState("MSFT.NASDAQ, GOOGL.NASDAQ");
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<EquityReportDetail | null>(null);
  const [tab, setTab] = useState("thesis");

  // If the route param changes (deep link with /research/equity/:symbol),
  // pre-populate the form so the user gets a same-page UX.
  useEffect(() => {
    if (params.symbol) setVtSymbol(decodeURIComponent(params.symbol));
  }, [params.symbol]);

  const submit = async () => {
    setBusy(true);
    setReport(null);
    try {
      const peersArr = peers.split(",").map((s) => s.trim()).filter(Boolean);
      const res = await apiFetch<EquityReportDetail>("/agents/equity-report", {
        method: "POST",
        body: JSON.stringify({ vt_symbol: vtSymbol, as_of: asOf, peers: peersArr }),
      });
      setReport(res);
      toast.success(`Report ${res.id.slice(0, 8)} ${res.status}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const metrics: Metric[] = [
    { label: "Status", value: null, hint: <Badge variant="secondary">{report?.status ?? "—"}</Badge> },
    { label: "Cost", value: report?.cost_usd ?? null, kind: "money", digits: 4, tone: "neutral" },
    {
      label: "Catalysts",
      value: report?.catalysts?.length ?? null,
      kind: "integer",
      digits: 0,
      tone: "neutral",
    },
    {
      label: "Sections",
      value: report?.sections ? Object.keys(report.sections).length : null,
      kind: "integer",
      digits: 0,
      tone: "neutral",
    },
  ];

  return (
    <PageContainer
      title="Equity Research"
      subtitle="FinRobot-style structured equity report. Submit a vt_symbol + peers; the agent crew assembles a multi-section report (thesis / valuation / catalysts / sensitivity)."
    >
      <Card className="mb-3">
        <CardHeader>
          <CardTitle>Inputs</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
            className="flex flex-wrap items-end gap-3"
          >
            <div className="flex flex-col gap-1">
              <Label htmlFor="vt">vt_symbol</Label>
              <Input
                id="vt"
                value={vtSymbol}
                onChange={(e) => setVtSymbol(e.target.value)}
                className="w-56 font-mono"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="as_of">as_of</Label>
              <Input
                id="as_of"
                value={asOf}
                onChange={(e) => setAsOf(e.target.value)}
                className="w-48 font-mono"
              />
            </div>
            <div className="flex flex-1 flex-col gap-1">
              <Label htmlFor="peers">Peers (comma-separated)</Label>
              <Input
                id="peers"
                value={peers}
                onChange={(e) => setPeers(e.target.value)}
                className="font-mono"
              />
            </div>
            <Button type="submit" disabled={busy} className="gap-2">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {busy ? "Generating…" : "Generate"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <MetricsGrid metrics={metrics} columns={4} />

      <Tabs value={tab} onValueChange={setTab} className="mt-3">
        <TabsList>
          <TabsTrigger value="thesis">Thesis</TabsTrigger>
          <TabsTrigger value="valuation">Valuation</TabsTrigger>
          <TabsTrigger value="catalysts">Catalysts</TabsTrigger>
          <TabsTrigger value="sensitivity">Sensitivity</TabsTrigger>
          <TabsTrigger value="usage">Usage</TabsTrigger>
        </TabsList>
        {(["thesis", "valuation", "catalysts", "sensitivity", "usage"] as const).map((k) => (
          <TabsContent key={k} value={k} className="mt-3">
            <Card>
              <CardContent>
                <pre className="max-h-[60vh] overflow-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3 font-mono text-xs">
                  {report
                    ? JSON.stringify(
                        k === "thesis"
                          ? report.sections
                          : k === "valuation"
                            ? report.valuation
                            : k === "catalysts"
                              ? report.catalysts
                              : k === "sensitivity"
                                ? report.sensitivity
                                : report.usage,
                        null,
                        2,
                      )
                    : "Generate a report to see this section."}
                </pre>
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>
    </PageContainer>
  );
}
