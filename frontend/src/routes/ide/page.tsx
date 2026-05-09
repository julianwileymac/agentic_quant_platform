import { Play, Save } from "lucide-react";
import { useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

import { CodeEditor } from "@/components/common/CodeEditor";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { apiFetch, ApiError } from "@/lib/api/client";

const STARTER_PYTHON = `# AQP scratch — runs in the FastAPI sandbox kernel.
# All LLM calls must go through router_complete (AGENTS.md rule 2).
from aqp.config import settings
from aqp.llm.providers.router import router_complete

resp = router_complete(
    profile="default",
    messages=[{"role": "user", "content": "What is the active iceberg warehouse?"}],
)
print(resp.content)
print("warehouse:", settings.iceberg_warehouse_uri)
`;

const STARTER_JSON = `{
  "strategy": {
    "class": "FrameworkAlgorithm",
    "module_path": "aqp.strategies.framework",
    "kwargs": {
      "universe_model": {
        "class": "StaticUniverse",
        "module_path": "aqp.strategies.universes",
        "kwargs": { "symbols": ["AAPL.NASDAQ", "MSFT.NASDAQ"] }
      },
      "alpha_model": {
        "class": "MeanReversionAlpha",
        "module_path": "aqp.strategies.mean_reversion",
        "kwargs": { "lookback": 20, "z_threshold": 2.0 }
      }
    }
  }
}
`;

interface RunResponse {
  stdout?: string;
  stderr?: string;
  ok?: boolean;
}

/**
 * /ide — CodeMirror-backed Python + JSON scratch surface per blueprint
 * Directive 4. The editor is intentionally minimal: it sends the
 * source to a sandboxed FastAPI runner endpoint and displays stdout /
 * stderr. The full multi-file IDE with strategy templates and saved
 * snippets is a Phase 6 follow-up.
 */
export function IdeRoute() {
  const [language, setLanguage] = useState<"python" | "json">("python");
  const [pythonSrc, setPythonSrc] = useState(STARTER_PYTHON);
  const [jsonSrc, setJsonSrc] = useState(STARTER_JSON);
  const [output, setOutput] = useState<string>("");
  const [busy, setBusy] = useState(false);

  const value = language === "python" ? pythonSrc : jsonSrc;
  const setValue = (v: string) => (language === "python" ? setPythonSrc(v) : setJsonSrc(v));

  const onRun = async () => {
    setBusy(true);
    try {
      if (language === "json") {
        // Validate JSON locally; no backend call needed.
        try {
          const parsed = JSON.parse(jsonSrc);
          setOutput(JSON.stringify(parsed, null, 2));
          toast.success("JSON parsed successfully");
        } catch (err) {
          setOutput(`Parse error: ${(err as Error).message}`);
          toast.error("Invalid JSON");
        }
        return;
      }
      const res = await apiFetch<RunResponse>("/ide/run", {
        method: "POST",
        body: JSON.stringify({ language, source: pythonSrc }),
      });
      const blocks: string[] = [];
      if (res.stdout) blocks.push(`--- stdout ---\n${res.stdout}`);
      if (res.stderr) blocks.push(`--- stderr ---\n${res.stderr}`);
      setOutput(blocks.join("\n\n") || "(no output)");
      toast.success("Run completed");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : (err as Error).message;
      setOutput(`Run failed: ${message}`);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageContainer
      title="Python IDE"
      subtitle="Browser-based scratch surface (CodeMirror 6). Runs in the FastAPI sandbox; obeys the same hard rules as agent code."
      extra={
        <div className="flex items-center gap-2">
          <Badge variant="warn">Phase 6 preview</Badge>
          <Button variant="outline" size="sm" onClick={() => toast.info("Snippet save lands in Phase 6 follow-up")}>
            <Save className="h-4 w-4" /> Save
          </Button>
          <Button onClick={onRun} disabled={busy}>
            <Play className="h-4 w-4" /> {busy ? "Running…" : "Run"}
          </Button>
        </div>
      }
      bleed
    >
      <div className="h-[calc(100vh-160px)] px-6 pb-6">
        <PanelGroup direction="horizontal" className="h-full gap-2">
          <Panel defaultSize={60} minSize={35}>
            <Card className="flex h-full flex-col">
              <CardHeader>
                <CardTitle>Editor</CardTitle>
                <Tabs value={language} onValueChange={(v) => setLanguage(v as "python" | "json")}>
                  <TabsList>
                    <TabsTrigger value="python">Python</TabsTrigger>
                    <TabsTrigger value="json">JSON</TabsTrigger>
                  </TabsList>
                  <TabsContent value="python" />
                  <TabsContent value="json" />
                </Tabs>
              </CardHeader>
              <CardContent className="min-h-0 flex-1 p-3">
                <CodeEditor value={value} onChange={setValue} language={language} />
              </CardContent>
            </Card>
          </Panel>
          <PanelResizeHandle className="w-1 cursor-col-resize bg-[var(--border-default)]" />
          <Panel defaultSize={40} minSize={25}>
            <Card className="flex h-full flex-col">
              <CardHeader>
                <CardTitle>Output</CardTitle>
              </CardHeader>
              <CardContent className="min-h-0 flex-1 p-0">
                <ScrollArea className="h-full">
                  <pre className="whitespace-pre-wrap break-words p-4 font-mono text-xs text-[var(--text-primary)]">
                    {output || "(no output yet — click Run)"}
                  </pre>
                </ScrollArea>
              </CardContent>
            </Card>
          </Panel>
        </PanelGroup>
      </div>
    </PageContainer>
  );
}
