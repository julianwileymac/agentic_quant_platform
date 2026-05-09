import { Copy, Crosshair, Edit3, NotebookPen, Trash2 } from "lucide-react";

import { cn } from "@/lib/utils";

interface CanvasContextMenuProps {
  open: boolean;
  position: { x: number; y: number } | null;
  nodeId: string | null;
  onEdit: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onFocus: () => void;
  onAddNote: () => void;
  onClose: () => void;
}

/**
 * Right-click context menu for canvas nodes. Hand-rolled rather than
 * sitting on `@radix-ui/react-context-menu` so the open state stays
 * controlled by the parent (we open it from a `react-flow` event,
 * not a `<ContextMenuTrigger>`).
 */
export function CanvasContextMenu({
  open,
  position,
  nodeId,
  onEdit,
  onDuplicate,
  onDelete,
  onFocus,
  onAddNote,
  onClose,
}: CanvasContextMenuProps) {
  if (!open || !position || !nodeId) return null;
  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} aria-hidden />
      <div
        role="menu"
        className="fixed z-50 min-w-[170px] overflow-hidden rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] p-1 text-sm shadow-lg"
        style={{ left: position.x, top: position.y }}
      >
        <Item icon={Edit3} label="Edit params" onClick={onEdit} />
        <Item icon={Copy} label="Duplicate" onClick={onDuplicate} />
        <Item icon={Crosshair} label="Focus" onClick={onFocus} />
        <Item icon={NotebookPen} label="Add note" onClick={onAddNote} />
        <Separator />
        <Item icon={Trash2} label="Delete" onClick={onDelete} variant="destructive" />
      </div>
    </>
  );
}

function Item({
  icon: Icon,
  label,
  onClick,
  variant = "default",
}: {
  icon: typeof Edit3;
  label: string;
  onClick: () => void;
  variant?: "default" | "destructive";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      role="menuitem"
      className={cn(
        "flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-xs transition-colors hover:bg-[var(--bg-surface)]",
        variant === "destructive" && "text-[var(--neg-fg)] hover:bg-[var(--neg-bg)]",
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      <span>{label}</span>
    </button>
  );
}

function Separator() {
  return <div className="my-1 h-px bg-[var(--border-default)]" />;
}
