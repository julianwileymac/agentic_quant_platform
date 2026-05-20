import { Loader2, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";
import { useChatStream } from "@/lib/ws/useChatStream";

interface ChatTaskResponse {
  task_id: string;
  stream_url?: string;
}

interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  taskId?: string;
}

/**
 * Real chat surface for the new frontend. Posts a prompt to
 * `POST /chat/messages`, captures the resulting `task_id`, then streams
 * `delta` / `content` frames via `useChatStream` into the assistant
 * bubble. Mirrors the legacy webui `ChatPage` flow but uses the new
 * design tokens + shadcn primitives.
 */
export function ChatRoute() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const stream = useChatStream(taskId);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // When the active stream produces text, mirror it into the latest
  // assistant turn so the user watches tokens land in real time.
  useEffect(() => {
    if (!taskId) return;
    setTurns((prev) => {
      if (prev.length === 0) return prev;
      const last = prev[prev.length - 1];
      if (!last || last.role !== "assistant" || last.taskId !== taskId) return prev;
      const text = stream.text || (stream.error ?? "");
      const next = [...prev];
      next[next.length - 1] = { ...last, content: text };
      return next;
    });
  }, [stream.text, stream.error, taskId]);

  // Auto-scroll on new content.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [turns]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const prompt = draft.trim();
    if (!prompt) return;
    setBusy(true);
    // Append the user turn first so the user sees their message
    // immediately. The assistant placeholder is appended only after
    // we have the task_id back, otherwise the streaming effect's
    // `last.taskId === taskId` guard would never match and the
    // accumulated `delta` chunks would never land in the bubble.
    setTurns((prev) => [...prev, { role: "user", content: prompt }]);
    setDraft("");
    try {
      const res = await apiFetch<ChatTaskResponse>("/chat/messages", {
        method: "POST",
        body: JSON.stringify({ prompt }),
      });
      setTurns((prev) => [
        ...prev,
        { role: "assistant", content: "", taskId: res.task_id },
      ]);
      setTaskId(res.task_id);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Chat send failed: ${msg}`);
      setTurns((prev) => [
        ...prev,
        { role: "assistant", content: `(error) ${msg}` },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageContainer
      title="Chat"
      subtitle="Direct LLM chat. Each turn streams via /chat/stream/{task_id} so deltas land token-by-token; errors and `done` frames close the loop automatically."
      extra={
        taskId ? (
          <span className="flex items-center gap-2 text-xs">
            <Badge variant={stream.done ? "positive" : "secondary"}>
              {stream.done ? "done" : stream.status}
            </Badge>
            <span className="font-mono text-[10px] text-[var(--text-secondary)]">
              {taskId.slice(0, 12)}
            </span>
          </span>
        ) : null
      }
    >
      <Card className="h-[calc(100vh-180px)]">
        <CardHeader>
          <CardTitle>Conversation</CardTitle>
        </CardHeader>
        <CardContent className="grid h-full grid-rows-[1fr_auto] gap-3">
          <div ref={scrollRef} className="overflow-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3">
            {turns.length === 0 ? (
              <p className="text-sm italic text-[var(--text-secondary)]">
                Type a prompt below to start a conversation. The reply streams in token-by-token.
              </p>
            ) : (
              <ul className="grid gap-3">
                {turns.map((turn, i) => (
                  <li
                    key={i}
                    className={
                      turn.role === "user"
                        ? "ml-auto max-w-[85%] rounded-md bg-[var(--info-bg)] p-3 text-sm"
                        : "mr-auto max-w-[85%] rounded-md border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 text-sm"
                    }
                  >
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
                      {turn.role}
                    </span>
                    <pre className="mt-1 whitespace-pre-wrap font-mono text-xs">
                      {turn.content || (turn.role === "assistant" ? "…" : "")}
                    </pre>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <form onSubmit={submit} className="flex items-end gap-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit(e);
                }
              }}
              placeholder="Send a message (Enter to send, Shift+Enter for newline)…"
              className="min-h-[60px] flex-1 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-[var(--info-fg)]"
            />
            <Button type="submit" disabled={busy || !draft.trim()} className="gap-2">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              {busy ? "Sending…" : "Send"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
