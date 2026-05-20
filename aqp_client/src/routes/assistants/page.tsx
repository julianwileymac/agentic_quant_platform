import { Loader2, Send, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { EntityPicker } from "@/components/common/EntityPicker";
import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { ProgressTimeline } from "@/components/common/ProgressTimeline";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { AssistantsApi, type AssistantSpecSummary } from "@/lib/api/assistants";
import { useChatStream } from "@/lib/ws";

interface Turn {
  role: "user" | "assistant";
  content: string;
  taskId?: string;
}

export function AssistantsRoute() {
  const specs = useApiQuery<AssistantSpecSummary[]>({
    queryKey: ["assistants"],
    path: "/assistants",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const [assistantName, setAssistantName] = useState("platform_assistant");
  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const stream = useChatStream(taskId, "assistants");

  const selected = useMemo(
    () => (specs.data ?? []).find((spec) => spec.name === assistantName),
    [assistantName, specs.data],
  );

  useEffect(() => {
    if (!taskId) return;
    setTurns((prev) => {
      const last = prev[prev.length - 1];
      if (!last || last.role !== "assistant" || last.taskId !== taskId) return prev;
      const next = [...prev];
      next[next.length - 1] = { ...last, content: stream.text || stream.error || "" };
      return next;
    });
  }, [stream.text, stream.error, taskId]);

  const metrics: Metric[] = [
    { label: "Mode", value: null, hint: <Badge>{selected?.mode ?? "assistant"}</Badge> },
    { label: "Target", value: null, hint: <span className="font-mono text-xs">{selected?.target_ref ?? "—"}</span> },
    { label: "Stream", value: null, hint: <Badge variant={stream.done ? "positive" : "secondary"}>{taskId ? stream.status : "idle"}</Badge> },
    { label: "Turns", value: turns.length, kind: "integer" },
  ];

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const prompt = draft.trim();
    if (!prompt || !assistantName) return;
    setBusy(true);
    setDraft("");
    setTurns((prev) => [...prev, { role: "user", content: prompt }]);
    try {
      const res = await AssistantsApi.sendMessage(assistantName, prompt);
      setTaskId(res.task_id);
      setTurns((prev) => [...prev, { role: "assistant", content: "", taskId: res.task_id }]);
    } catch (error) {
      const msg = error instanceof ApiError ? error.message : (error as Error).message;
      toast.error(`Assistant send failed: ${msg}`);
      setTurns((prev) => [...prev, { role: "assistant", content: `(error) ${msg}` }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageContainer
      title="Assistants"
      subtitle="Interactive AssistantRuntime sessions over AgentRuntime and WorkflowRuntime."
      extra={
        <div className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
          <ShieldCheck className="h-4 w-4" />
          Tool permissions are explicit on the AssistantSpec.
        </div>
      }
    >
      <MetricsGrid metrics={metrics} columns={4} />
      <div className="mt-4 grid gap-4 xl:grid-cols-[340px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Assistant Policy</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <label className="grid gap-1 text-xs">
              <span className="font-semibold text-[var(--text-secondary)]">
                Agent-backed context
              </span>
              <EntityPicker
                kind="agents"
                value={selected?.mode === "agent" ? selected.target_ref : ""}
                onChange={() => undefined}
                disabled
                placeholder="Agent target"
              />
            </label>
            <label className="grid gap-1 text-xs">
              <span className="font-semibold text-[var(--text-secondary)]">Assistant</span>
              <select
                value={assistantName}
                onChange={(event) => setAssistantName(event.target.value)}
                className="rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-2 py-2 text-sm"
              >
                {(specs.data ?? []).map((spec) => (
                  <option key={spec.name} value={spec.name}>
                    {spec.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3 text-xs">
              <div className="font-semibold">Allowed Tools</div>
              <p className="mt-1 text-[var(--text-secondary)]">
                Tool grants are saved on the backend spec. This UI displays the active target and keeps
                permission changes explicit rather than prompt-injected.
              </p>
            </div>
          </CardContent>
        </Card>

        <Card className="min-h-[620px]">
          <CardHeader>
            <CardTitle>Session</CardTitle>
          </CardHeader>
          <CardContent className="grid h-[560px] grid-rows-[1fr_auto] gap-3">
            <div className="overflow-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3">
              {turns.length === 0 ? (
                <p className="text-sm italic text-[var(--text-secondary)]">Send a prompt to start an assistant run.</p>
              ) : (
                <ul className="grid gap-3">
                  {turns.map((turn, index) => (
                    <li
                      key={`${turn.role}-${index}`}
                      className={
                        turn.role === "user"
                          ? "ml-auto max-w-[85%] rounded-md bg-[var(--info-bg)] p-3 text-sm"
                          : "mr-auto max-w-[85%] rounded-md border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 text-sm"
                      }
                    >
                      <div className="text-[10px] font-semibold uppercase text-[var(--text-secondary)]">{turn.role}</div>
                      <pre className="mt-1 whitespace-pre-wrap font-mono text-xs">
                        {turn.content || (turn.role === "assistant" ? "..." : "")}
                      </pre>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <form onSubmit={submit} className="flex items-end gap-2">
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="Ask the selected assistant..."
                className="min-h-[64px] flex-1 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 py-2 font-mono text-sm"
              />
              <Button type="submit" disabled={busy || !draft.trim()} className="gap-2">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                Send
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Live Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <ProgressTimeline events={stream.events} height="280px" follow />
        </CardContent>
      </Card>
    </PageContainer>
  );
}
