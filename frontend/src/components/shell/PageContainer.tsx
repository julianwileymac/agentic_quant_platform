import { type ReactNode } from "react";

import { cn } from "@/lib/utils";

interface PageContainerProps {
  title: ReactNode;
  subtitle?: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  /** Wider padding for full-bleed surfaces like the trading desk. */
  bleed?: boolean;
}

/**
 * Standard route shell used by every non-bleed page. The bleed prop
 * removes the inner padding so the live trading desk and agent flow
 * canvases can fill the viewport.
 */
export function PageContainer({ title, subtitle, extra, children, bleed = false }: PageContainerProps) {
  return (
    <div className={cn("flex h-full flex-col", bleed ? "" : "px-6 py-5")}>
      <div className={cn("flex flex-col gap-1 pb-4", bleed && "px-6 pt-5")}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
            {subtitle ? (
              <p className="text-sm text-[var(--text-secondary)]">{subtitle}</p>
            ) : null}
          </div>
          {extra ? <div className="flex items-center gap-2">{extra}</div> : null}
        </div>
      </div>
      <div className={cn("flex-1", bleed ? "" : "min-h-0")}>{children}</div>
    </div>
  );
}
