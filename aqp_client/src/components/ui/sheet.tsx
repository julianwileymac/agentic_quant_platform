import { X } from "lucide-react";
import { type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: ReactNode;
  description?: ReactNode;
  /** Width of the slide-over. Defaults to `max-w-md`. */
  widthClass?: string;
  children: ReactNode;
  footer?: ReactNode;
}

/**
 * Right-anchored slide-over Sheet. Hand-rolled rather than sitting on
 * `@radix-ui/react-dialog` so the backdrop animation, focus trap, and
 * close-on-escape behaviour stay consistent with the existing
 * NodeParamsDrawer / AssistantDrawer surfaces in the app.
 */
export function Sheet({
  open,
  onOpenChange,
  title,
  description,
  widthClass = "max-w-md",
  children,
  footer,
}: SheetProps) {
  return (
    <>
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/60 transition-opacity",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={() => onOpenChange(false)}
        aria-hidden
      />
      <aside
        role="dialog"
        aria-hidden={!open}
        className={cn(
          "fixed right-0 top-0 z-50 flex h-screen w-full flex-col border-l border-[var(--border-default)] bg-[var(--bg-surface)] shadow-2xl transition-transform",
          widthClass,
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <div className="flex items-start justify-between gap-3 border-b border-[var(--border-default)] px-4 py-3">
          <div className="min-w-0 flex-1">
            {title ? <div className="text-sm font-semibold">{title}</div> : null}
            {description ? (
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{description}</p>
            ) : null}
          </div>
          <Button variant="ghost" size="icon" onClick={() => onOpenChange(false)} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex flex-1 flex-col gap-3 overflow-auto p-4">{children}</div>
        {footer ? (
          <div className="flex items-center justify-end gap-2 border-t border-[var(--border-default)] px-4 py-3">
            {footer}
          </div>
        ) : null}
      </aside>
    </>
  );
}
