import { Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAlphaPresence } from "@/lib/ws/useAlphaPresence";

interface Props {
  displayName: string;
}

/**
 * OOS extension: small UI affordance that lights up when other users
 * are also looking at the Alpha Factor Studio. Lives next to the
 * Studio title so concurrent edits at least surface a notice.
 *
 * Driven by ``useAlphaPresence`` (single WS subscription per mount).
 * Disconnected / empty rooms render nothing.
 */
export function PresenceBadge({ displayName }: Props) {
  const { status, others } = useAlphaPresence(displayName);
  if (status !== "open" || others.length === 0) return null;
  const names = others.map((p) => p.display_name || p.participant_id);
  const preview = names.slice(0, 3).join(", ") + (names.length > 3 ? `, +${names.length - 3} more` : "");
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge variant="secondary" className="gap-1">
            <Users className="h-3 w-3" />
            {others.length === 1 ? "1 other editing" : `${others.length} others editing`}
          </Badge>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-xs text-xs">
          <p className="font-medium">Concurrent viewers</p>
          <p>{preview}</p>
          <p className="mt-1 text-[10px] text-[var(--text-secondary)]">
            Presence-only. Save conflicts use last-write-wins; coordinate
            verbally if you're co-authoring a formula.
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
