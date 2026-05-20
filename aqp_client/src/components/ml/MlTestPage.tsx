import { Play } from "lucide-react";
import { useState } from "react";

import { CodeEditor } from "@/components/common/CodeEditor";
import { PageContainer } from "@/components/shell/PageContainer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";

const FLOWS = [
  { value: "linear", label: "Linear (ridge / lasso)", body: '{"flow":"linear","X":[[1,2],[3,4]],"y":[1,2]}' },
  { value: "decomposition", label: "Decomposition", body: '{"flow":"decomposition","series":[1,2,3,4,5,6]}' },
  { value: "forecast", label: "Forecast", body: '{"flow":"forecast","series":[1,2,3,4,5,6]}' },
  { value: "garch", label: "GARCH", body: '{"flow":"garch","returns":[0.01,-0.02,0.03,-0.01]}' },
  { value: "iforest", label: "Isolation forest", body: '{"flow":"iforest","X":[[1,2],[3,4],[5,6]]}' },
];

export function MlTestPage() {
  const [tab, setTab] = useState(FLOWS[0]!.value);
  const [body, setBody] = useState(FLOWS[0]!.body);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<unknown>(null);

  const onTabChange = (next: string) => {
    setTab(next);
    const flow = FLOWS.find((f) => f.value === next);
    if (flow) setBody(flow.body);
  };

  const run = async () => {
    setBusy(true);
    setResult(null);
    try {
      let payload: unknown;
      try {
        payload = JSON.parse(body || "{}");
      } catch (parseErr) {
        toast.error(`Invalid JSON: ${(parseErr as Error).message}`);
        return;
      }
      const res = await apiFetch<unknown>("/ml/flows/run", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setResult(res);
      toast.success("Flow ok");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageContainer
      title="ML Test"
      subtitle="Sync ML test harness — run a workbench flow against the API and inspect the JSON response. Useful for adhoc experimentation without spinning up a full ML training run."
    >
      <Tabs value={tab} onValueChange={onTabChange}>
        <TabsList>
          {FLOWS.map((f) => (
            <TabsTrigger key={f.value} value={f.value}>
              {f.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value={tab} className="mt-3">
          <Card className="mb-3">
            <CardHeader>
              <CardTitle>Request body (JSON)</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3">
              <div className="h-40 overflow-hidden rounded-md">
                <CodeEditor language="json" value={body} onChange={setBody} />
              </div>
              <Button onClick={run} disabled={busy} className="w-fit gap-2">
                <Play className="h-4 w-4" /> {busy ? "Running…" : "Run flow"}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Result</CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="max-h-[50vh] overflow-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3 font-mono text-xs">
                {result ? JSON.stringify(result, null, 2) : "Run a flow to see output."}
              </pre>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </PageContainer>
  );
}
