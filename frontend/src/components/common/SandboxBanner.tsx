import { FlaskConical, ShieldAlert, Wifi } from "lucide-react";
import { useEffect } from "react";

import { Badge } from "@/components/ui/badge";
import { useTenancyStore, type ExecutionMode } from "@/store/tenancy";

const MODE_META: Record<
  ExecutionMode,
  { label: string; tone: "positive" | "warn" | "negative"; icon: typeof Wifi; banner: string | null }
> = {
  live: {
    label: "Live execution",
    tone: "positive",
    icon: Wifi,
    banner: null,
  },
  paper: {
    label: "Paper trading",
    tone: "warn",
    icon: ShieldAlert,
    banner:
      "Paper trading mode — orders are routed through the paper broker. No real capital is at risk.",
  },
  sandbox: {
    label: "Sandbox",
    tone: "warn",
    icon: FlaskConical,
    banner:
      "Sandbox mode — orders, fills, and PnL are entirely simulated. Backend writes are scoped to the active sandbox tenant.",
  },
};

/**
 * Global mode indicator. Reads the active execution mode from the
 * tenancy store and:
 *
 *   - applies `data-mode` on `<html>` so the CSS in tokens.css can
 *     render the amber outline + topbar accent without prop-drilling
 *   - prefixes the document title with `[SANDBOX]` / `[PAPER]` so
 *     operators are subconsciously aware in their tab strip
 *   - renders a persistent strip at the top of the viewport so the
 *     mode is always visible above the fold (Bloomberg-terminal
 *     "every pixel earns its place" requirement)
 *
 * Live mode renders nothing to keep the production trading desk
 * uncluttered.
 */
export function SandboxBanner() {
  const mode = useTenancyStore((s) => s.mode);
  const meta = MODE_META[mode];

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.mode = mode;
    const baseTitle = "Agentic Quant Platform";
    if (mode === "live") {
      document.title = baseTitle;
    } else {
      document.title = `[${mode.toUpperCase()}] ${baseTitle}`;
    }
    return () => {
      root.dataset.mode = "live";
      document.title = baseTitle;
    };
  }, [mode]);

  if (!meta.banner) return null;

  const Icon = meta.icon;
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-center gap-3 border-b border-[var(--sandbox-border)] bg-[var(--sandbox-bg)] px-4 py-2 text-xs text-[var(--sandbox-fg)]"
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="font-medium">{meta.banner}</span>
      <Badge variant="sandbox" className="uppercase tracking-wider">
        {mode}
      </Badge>
    </div>
  );
}
