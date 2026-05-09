import { Send } from "lucide-react";
import { useState } from "react";

import { ProgressTimeline } from "@/components/common/ProgressTimeline";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useChatStream } from "@/lib/ws";
import { BotsApi } from "@/lib/api/bots";

interface BotChatPanelProps {
  botId: string;
}

/**
 * Streaming chat for a research bot. Sends a prompt to
 * `POST /bots/{ref}/chat`, receives the task_id, and subscribes to
 * the chat progress WebSocket via `useChatStream`.
 */
export function BotChatPanel({ botId }: BotChatPanelProps) {
  const [prompt, setPrompt] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);
  const stream = useChatStream(taskId, "chat");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = prompt.trim();
    if (!trimmed) return;
    setPrompt("");
    try {
      const res = await BotsApi.chat(botId, { prompt: trimmed });
      setTaskId(res.task_id);
      toast.success("Prompt routed", { description: `task_id=${res.task_id}` });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Chat failed: ${msg}`);
    }
  };

  return (
    <Card className="flex h-[60vh] flex-col">
      <CardHeader>
        <CardTitle>Research bot chat</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-2 p-3">
        <ProgressTimeline events={stream.events} className="flex-1" follow />
        <form onSubmit={submit} className="flex flex-col gap-2">
          <Label htmlFor="bot-chat-prompt">Prompt</Label>
          <div className="flex gap-2">
            <Input
              id="bot-chat-prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={`Ask ${botId}…`}
            />
            <Button type="submit" disabled={!prompt.trim() || stream.status === "open"} className="gap-1">
              <Send className="h-4 w-4" /> Send
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
