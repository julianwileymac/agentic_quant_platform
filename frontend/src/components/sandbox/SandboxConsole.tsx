import {
  Beaker,
  CircleX,
  Code,
  Database,
  Pause,
  Play,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";

import { CodeEditor } from "@/components/common/CodeEditor";
import { EntityPicker } from "@/components/common/EntityPicker";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { SandboxApi, type SandboxSessionSummary } from "@/lib/api/sandbox";

const DEFAULT_COMPONENT = `# Edit me — this is a sandbox component definition.
# Examples:
#   - kind: airbyte_connection
#   - kind: dataset_kind: iceberg / parquet / api / partitioned / sql / redis_kv / external

type: airbyte_connection
name: "demo"
streams:
  - name: "default"
`;

/**
 * Three-pane interactive Dagster sandbox console.
 *
 * Mounts at `/data/sandbox`. Amber outline + "[SANDBOX]" tab title
 * mirror the paper-mode guardrail in `frontend.mdc`. Airbyte
 * connections are picked through the EntityPicker so the operator
 * can never type a stale connection id.
 */
export function SandboxConsole() {
  const [session, setSession] = useState<SandboxSessionSummary | null>(null);
  const [componentName, setComponentName] = useState("demo.yaml");
  const [componentBody, setComponentBody] = useState(DEFAULT_COMPONENT);
  const [airbyteRowId, setAirbyteRowId] = useState<string | null>(null);
  const [streamLog, setStreamLog] = useState<string>("");

  useEffect(() => {
    document.title = session
      ? `[SANDBOX] ${session.id.slice(0, 8)} – AQP`
      : "Dagster Sandbox – AQP";
    return () => {
      document.title = "AQP";
    };
  }, [session]);

  const create = async () => {
    try {
      const s = await SandboxApi.create();
      setSession(s);
      toast.success(`Sandbox session ${s.id.slice(0, 8)} created`);
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const teardown = async () => {
    if (!session) return;
    try {
      await SandboxApi.teardown(session.id);
      toast.success(`Sandbox ${session.id.slice(0, 8)} torn down`);
      setSession(null);
      setStreamLog("");
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const writeComponent = async () => {
    if (!session) return toast.error("Create a session first");
    try {
      const s = await SandboxApi.writeComponent(session.id, componentName, componentBody);
      setSession(s);
      toast.success(`Wrote ${componentName} to sandbox`);
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const writeAirbyte = async () => {
    if (!session) return toast.error("Create a session first");
    if (!airbyteRowId) return toast.error("Pick an Airbyte connection first");
    try {
      const s = await SandboxApi.loadAirbyte(session.id, airbyteRowId);
      setSession(s);
      toast.success("Airbyte connection loaded into sandbox");
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const loadDefs = async () => {
    if (!session) return;
    try {
      const s = await SandboxApi.load(session.id);
      setSession(s);
      toast.success(`Loaded ${s.asset_keys.length} asset(s)`);
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const execute = async () => {
    if (!session) return;
    try {
      const result = await SandboxApi.execute(session.id);
      setStreamLog((prev) =>
        prev + `[execute] task ${result.task_id} – stream ${result.stream_url}\n`,
      );
      // Poll once after a beat to refresh the log_summary.
      setTimeout(async () => {
        try {
          const refreshed = await SandboxApi.get(session.id);
          setSession(refreshed);
        } catch {
          // ignore
        }
      }, 1500);
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  return (
    <PageContainer
      title="Dagster Sandbox"
      subtitle="Ephemeral interactive environment for testing components + Airbyte connections without polluting production."
      extra={
        <Badge variant="warn">[SANDBOX]</Badge>
      }
    >
      <div
        className="grid gap-3 rounded-md border-2 border-[var(--warn-fg)] p-3 lg:grid-cols-3"
      >
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Beaker className="h-4 w-4" /> Session
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 text-xs">
            {session ? (
              <>
                <p className="font-mono text-[10px] text-[var(--text-muted)]">
                  {session.id}
                </p>
                <p>Status: <Badge variant="secondary">{session.status}</Badge></p>
                <p>
                  Components: <strong>{session.components.length}</strong>
                  &nbsp;Asset keys: <strong>{session.asset_keys.length}</strong>
                </p>
                <p className="text-[10px] text-[var(--text-muted)]">
                  Expires {session.expires_at ?? "—"}
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={loadDefs} className="gap-1">
                    <Code className="h-3 w-3" /> Load
                  </Button>
                  <Button size="sm" onClick={execute} className="gap-1">
                    <Play className="h-3 w-3" /> Execute
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={teardown}
                    className="gap-1"
                  >
                    <Trash2 className="h-3 w-3" /> Teardown
                  </Button>
                </div>
              </>
            ) : (
              <Button size="sm" variant="default" onClick={create} className="gap-1">
                <Plus className="h-3 w-3" /> Create session
              </Button>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Code className="h-4 w-4" /> Component
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 text-xs">
            <Label>Name</Label>
            <Input
              value={componentName}
              onChange={(event) => setComponentName(event.target.value)}
            />
            <Label>Body (YAML)</Label>
            <div className="h-56 overflow-hidden rounded-md">
              <CodeEditor
                language="yaml"
                value={componentBody}
                onChange={(text: string) => setComponentBody(text)}
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" onClick={writeComponent} className="gap-1">
                <Save className="h-3 w-3" /> Write component
              </Button>
            </div>
            <div className="mt-2 grid gap-1">
              <Label>Or load Airbyte connection</Label>
              <EntityPicker
                kind="airbyte_connectors"
                value={airbyteRowId}
                onChange={(next) => setAirbyteRowId(next)}
                placeholder="Pick connection..."
              />
              <Button size="sm" variant="outline" onClick={writeAirbyte} className="gap-1">
                <Database className="h-3 w-3" /> Load into sandbox
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Pause className="h-4 w-4" /> Asset graph + log
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 text-xs">
            {session?.asset_keys?.length ? (
              <ul className="ml-4 list-disc">
                {session.asset_keys.map((key) => (
                  <li key={key.join("/")}>
                    <code>{key.join("/")}</code>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[var(--text-muted)]">
                No assets loaded yet — write a component and click Load.
              </p>
            )}
            {streamLog ? (
              <pre className="mt-2 max-h-32 overflow-y-auto rounded bg-[var(--bg-app)] p-2 text-[10px]">
                {streamLog}
              </pre>
            ) : null}
            {session?.log_summary?.length ? (
              <pre className="mt-2 max-h-44 overflow-y-auto rounded bg-[var(--bg-app)] p-2 text-[10px]">
                {session.log_summary
                  .map((line) => JSON.stringify(line))
                  .join("\n")}
              </pre>
            ) : null}
            {!session ? (
              <div className="flex flex-col items-center justify-center gap-1 py-6 text-[var(--text-muted)]">
                <CircleX className="h-6 w-6" />
                <p>No active session.</p>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
