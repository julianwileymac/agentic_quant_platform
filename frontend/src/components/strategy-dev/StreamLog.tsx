import { Badge } from "@/components/ui/badge";
import { useChatStream } from "@/lib/ws";

interface StreamLogProps {
  taskId: string | null;
  maxHeight?: number;
}

export function StreamLog({ taskId, maxHeight = 240 }: StreamLogProps) {
  const stream = useChatStream(taskId);

  if (!taskId) {
    return (
      <p className="text-xs text-[var(--text-secondary)]">
        No active stream. Submit a task to subscribe.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <Badge variant="outline" className="font-mono text-[10px]">
          {taskId}
        </Badge>
        <Badge variant={stream.status === "closed" ? "positive" : "default"}>
          {stream.status}
        </Badge>
        {stream.error ? (
          <Badge variant="negative" className="font-mono text-[10px]">
            {stream.error}
          </Badge>
        ) : null}
      </div>
      <pre
        style={{ maxHeight }}
        className="overflow-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-2 font-mono text-[10px] leading-relaxed"
      >
        {stream.events.map((e, i) => `[${i}] ${JSON.stringify(e)}`).join("\n") || "—"}
      </pre>
    </div>
  );
}
