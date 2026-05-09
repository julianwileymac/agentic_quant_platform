import { Loader2, Save } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { CodeEditor } from "@/components/common/CodeEditor";
import { PageContainer } from "@/components/shell/PageContainer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";

const DEFAULT_YAML = `name: my_momentum_v1
description: Cross-sectional momentum on a fixed universe.
class: MomentumStrategy
module_path: aqp.strategies.momentum
kwargs:
  lookback: 60
  rebalance: weekly
  long_top_pct: 0.2
  short_bottom_pct: 0.2
universe:
  vt_symbols:
    - AAPL.NASDAQ
    - MSFT.NASDAQ
    - GOOGL.NASDAQ
`;

export function StrategyEditorNew() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [yaml, setYaml] = useState(DEFAULT_YAML);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      toast.warning("Name required");
      return;
    }
    setBusy(true);
    try {
      const res = await apiFetch<{ id: string }>("/strategies", {
        method: "POST",
        body: JSON.stringify({ name: name.trim(), yaml }),
      });
      toast.success(`Strategy ${res.id.slice(0, 8)} created`);
      navigate(`/strategies/${encodeURIComponent(res.id)}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageContainer
      title="New Strategy"
      subtitle="Authoring surface for a new IStrategy spec. Save persists a Strategy + initial StrategyVersion; opens the detail editor for further iteration."
    >
      <Card>
        <CardHeader>
          <CardTitle>Strategy spec</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="grid gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="strat-name">Name</Label>
              <Input
                id="strat-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="momentum_v1"
                className="max-w-md font-mono"
                required
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label>YAML</Label>
              <div className="h-[55vh] overflow-hidden rounded-md">
                <CodeEditor language="python" value={yaml} onChange={setYaml} />
              </div>
            </div>
            <Button type="submit" disabled={busy} className="w-fit gap-2">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {busy ? "Saving…" : "Save strategy"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
