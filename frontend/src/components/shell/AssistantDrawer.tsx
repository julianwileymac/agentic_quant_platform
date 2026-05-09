import { Send, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/store/ui";

/**
 * Assistant slide-over drawer. Wired to Ctrl/Cmd+J from the TopBar.
 * Phase 0 ships a minimal local UI; the real chat / streaming
 * integration lands in Phase 2 when the chat route is ported and the
 * shared `useChatStream` hook can be plugged in.
 */
export function AssistantDrawer() {
  const open = useUiStore((s) => s.assistantOpen);
  const setOpen = useUiStore((s) => s.setAssistantOpen);
  const [draft, setDraft] = useState("");

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
          <span className="text-sm font-semibold">Assistant</span>
          <Button variant="ghost" size="icon" onClick={() => setOpen(false)} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </div>
        <ScrollArea className="flex-1 px-4 py-3 text-sm text-[var(--text-secondary)]">
          <p className="mb-2">
            Ask the platform anything — strategy ideation, RAG queries, dataset shape probes,
            agent run inspection. Replies stream over the
            <code className="mx-1 rounded bg-[var(--bg-app)] px-1 font-mono text-xs">
              /chat/stream/{"{task_id}"}
            </code>
            WebSocket.
          </p>
          <p className="text-xs italic opacity-70">
            (Phase 0 placeholder — full streaming chat lands in Phase 2 alongside the chat
            route port.)
          </p>
        </ScrollArea>
        <form
          className="flex items-center gap-2 border-t border-[var(--border-default)] p-3"
          onSubmit={(e) => {
            e.preventDefault();
            setDraft("");
          }}
        >
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Type a question…"
          />
          <Button type="submit" size="icon" aria-label="Send" disabled={!draft.trim()}>
            <Send className="h-4 w-4" />
          </Button>
        </form>
      </aside>
    </>
  );
}
