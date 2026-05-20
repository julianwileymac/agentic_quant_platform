import { Loader2, Send, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import {
  AssistantsApi,
  type AssistantSpecSummary,
} from "@/lib/api/assistants";
import { useChatStream } from "@/lib/ws";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/store/ui";

interface DrawerTurn {
  role: "user" | "assistant";
  content: string;
  taskId?: string;
}

const DEFAULT_ASSISTANT = "platform_assistant";

/**
 * Assistant slide-over drawer.
 *
 * Wired to Ctrl/Cmd+J from the TopBar. Sends every prompt through the
 * ``AssistantsApi`` (gated server-side by AQP_ASSISTANT_ENGINE_ENABLED)
 * and streams the resulting task progress over the canonical
 * `/assistants/stream/{task_id}` websocket via ``useChatStream`` —
 * no raw WebSocket handling lives in component code.
 */
export function AssistantDrawer() {
  const open = useUiStore((s) => s.assistantOpen);
  const setOpen = useUiStore((s) => s.setAssistantOpen);
  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<DrawerTurn[]>([]);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [assistantName, setAssistantName] = useState(DEFAULT_ASSISTANT);

  const specs = useApiQuery<AssistantSpecSummary[]>({
    queryKey: ["assistants", "drawer"],
    path: "/assistants",
    enabled: open,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  const stream = useChatStream(taskId, "assistants");

  const selected = useMemo(() => {
    const list = specs.data ?? [];
    return list.find((spec) => spec.name === assistantName) ?? list[0];
  }, [assistantName, specs.data]);

  useEffect(() => {
    if (!selected) return;
    if (selected.name !== assistantName) {
      setAssistantName(selected.name);
    }
  }, [selected, assistantName]);

  useEffect(() => {
    if (!taskId) return;
    setTurns((prev) => {
      const last = prev[prev.length - 1];
      if (!last || last.role !== "assistant" || last.taskId !== taskId) return prev;
      const next = [...prev];
      next[next.length - 1] = {
        ...last,
        content: stream.text || stream.error || (stream.done ? "(no content)" : "..."),
      };
      return next;
    });
  }, [stream.text, stream.error, stream.done, taskId]);

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
      setTurns((prev) => [
        ...prev,
        { role: "assistant", content: "...", taskId: res.task_id },
      ]);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Assistant send failed: ${msg}`);
      setTurns((prev) => [
        ...prev,
        { role: "assistant", content: `(error) ${msg}` },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/60 transition-opacity",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={() => setOpen(false)}
        aria-hidden
      />
      <aside
        className={cn(
          "fixed right-0 top-0 z-50 flex h-screen w-full max-w-md flex-col border-l border-[var(--border-default)] bg-[var(--bg-surface)] shadow-2xl transition-transform",
          open ? "translate-x-0" : "translate-x-full",
        )}
        aria-hidden={!open}
      >
        <div className="flex h-[52px] items-center justify-between border-b border-[var(--border-default)] px-4">
          <div className="flex flex-col">
            <span className="text-sm font-semibold">Assistant</span>
            <span className="text-[10px] uppercase tracking-wide text-[var(--text-secondary)]">
              {selected?.mode ?? "agent"} · {selected?.target_ref ?? "—"}
            </span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setOpen(false)}
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="border-b border-[var(--border-default)] px-4 py-2 text-xs">
          <label className="grid gap-1">
            <span className="font-semibold text-[var(--text-secondary)]">
              Active assistant
            </span>
            <select
              value={assistantName}
              onChange={(e) => setAssistantName(e.target.value)}
              className="rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-2 py-1 text-sm"
            >
              {(specs.data ?? []).length === 0 ? (
                <option value={DEFAULT_ASSISTANT}>{DEFAULT_ASSISTANT}</option>
              ) : null}
              {(specs.data ?? []).map((spec) => (
                <option key={spec.name} value={spec.name}>
                  {spec.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <ScrollArea className="flex-1 px-4 py-3">
          {turns.length === 0 ? (
            <p className="text-xs italic text-[var(--text-secondary)]">
              Ask the assistant anything — strategy ideation, RAG queries, dataset
              probes, agent run inspection. Replies stream over
              <code className="mx-1 rounded bg-[var(--bg-app)] px-1 font-mono">
                /assistants/stream/{"{task_id}"}
              </code>
              .
            </p>
          ) : (
            <ul className="grid gap-3">
              {turns.map((turn, idx) => (
                <li
                  key={`${turn.role}-${idx}`}
                  className={cn(
                    "rounded-md border border-[var(--border-default)] p-3 text-xs",
                    turn.role === "user"
                      ? "ml-auto max-w-[85%] bg-[var(--info-bg)]"
                      : "mr-auto max-w-[85%] bg-[var(--bg-app)]",
                  )}
                >
                  <div className="text-[10px] font-semibold uppercase text-[var(--text-secondary)]">
                    {turn.role}
                  </div>
                  <pre className="mt-1 whitespace-pre-wrap font-mono text-[11px]">
                    {turn.content}
                  </pre>
                </li>
              ))}
            </ul>
          )}
        </ScrollArea>

        <form
          className="flex items-center gap-2 border-t border-[var(--border-default)] p-3"
          onSubmit={submit}
        >
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Type a question…"
            disabled={busy}
          />
          <Button
            type="submit"
            size="icon"
            aria-label="Send"
            disabled={busy || !draft.trim()}
          >
            {busy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </form>
      </aside>
    </>
  );
}
