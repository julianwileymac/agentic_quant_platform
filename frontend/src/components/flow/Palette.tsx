import { ChevronDown } from "lucide-react";
import { type DragEvent } from "react";

import { cn } from "@/lib/utils";

import { PALETTE_DRAG_MIME, type PaletteDragPayload, type PaletteSection } from "./types";

interface PaletteProps {
  sections: PaletteSection[];
  className?: string;
}

/**
 * Left-rail draggable palette. Uses native `<details>` for collapsible
 * sections (so we don't introduce a new Radix package for one use
 * case). Each tile is a focusable `<button>` with `draggable=true`
 * that dispatches a `dragstart` carrying the palette payload as
 * `application/aqp-flow-node`. The canvas listens for that MIME and
 * spawns a node at the drop cursor.
 */
export function Palette({ sections, className }: PaletteProps) {
  return (
    <aside
      className={cn(
        "flex h-full w-60 shrink-0 flex-col gap-2 overflow-y-auto border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-3 text-sm",
        className,
      )}
      data-flow-palette="true"
    >
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
        Palette
      </div>
      {sections.map((section) => (
        <details
          key={section.title}
          open
          className="group rounded-md border border-[var(--border-default)] bg-[var(--bg-app)]"
        >
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
            <span>{section.title}</span>
            <ChevronDown className="h-3 w-3 transition-transform group-open:rotate-0 group-[&:not([open])]:-rotate-90" />
          </summary>
          <ul className="flex flex-col gap-1 p-1.5">
            {section.items.map((item) => (
              <li key={`${section.title}-${item.kind}-${item.label}`}>
                <button
                  type="button"
                  draggable
                  onDragStart={(e) => onDragStart(e, item)}
                  className="flex w-full flex-col items-start gap-0.5 rounded-md border border-[var(--border-default)] bg-[var(--bg-surface)] px-2 py-1.5 text-left text-xs transition-colors hover:border-[var(--info-fg)] hover:bg-[var(--bg-elevated)]"
                  data-flow-palette-tile="true"
                  data-kind={item.kind}
                >
                  <div className="flex w-full items-center gap-2">
                    <span
                      aria-hidden
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ background: item.accent ?? "#3b82f6" }}
                    />
                    <span className="font-medium">{item.label}</span>
                  </div>
                  {item.description ? (
                    <span className="line-clamp-2 text-[10px] text-[var(--text-secondary)]">
                      {item.description}
                    </span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        </details>
      ))}
    </aside>
  );
}

function onDragStart(e: DragEvent<HTMLButtonElement>, item: PaletteSection["items"][number]): void {
  const payload: PaletteDragPayload = {
    kind: item.kind,
    label: item.label,
    ...(item.accent !== undefined ? { accent: item.accent } : {}),
    ...(item.defaultParams !== undefined ? { defaultParams: item.defaultParams } : {}),
  };
  e.dataTransfer.setData(PALETTE_DRAG_MIME, JSON.stringify(payload));
  e.dataTransfer.effectAllowed = "move";
}
