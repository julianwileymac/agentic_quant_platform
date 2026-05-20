import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

interface UrnBadgeProps {
  urn: string;
  className?: string;
}

export function UrnBadge({ urn, className }: UrnBadgeProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(urn);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
      toast.success("URN copied");
    } catch {
      toast.error("Clipboard copy failed");
    }
  }

  return (
    <Badge
      variant="secondary"
      className={cn("flex w-full items-center justify-between gap-2 rounded-md px-2 py-1", className)}
    >
      <span className="truncate font-mono text-[10px]">{urn}</span>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={handleCopy}
        className="h-6 w-6 shrink-0"
        aria-label="Copy URN"
      >
        {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      </Button>
    </Badge>
  );
}
