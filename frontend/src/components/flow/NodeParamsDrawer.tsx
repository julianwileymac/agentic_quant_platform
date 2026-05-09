import { Save, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { CodeEditor } from "@/components/common/CodeEditor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

import type { AqpNode } from "./types";

interface NodeParamsDrawerProps {
  node: AqpNode | null;
  onClose: () => void;
  onSave: (next: { label: string; params: Record<string, unknown>; notes?: string }) => void;
}

/**
 * Slide-over drawer that edits the selected node's `data.label`,
 * `data.params` (via the CodeMirror JSON editor) and `data.notes`.
 * Save is gated on valid JSON.
 */
export function NodeParamsDrawer({ node, onClose, onSave }: NodeParamsDrawerProps) {
  const open = node != null;
  const [label, setLabel] = useState("");
  const [paramsText, setParamsText] = useState("{}");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (!node) return;
    setLabel(node.data.label ?? node.data.kind);
    setParamsText(JSON.stringify(node.data.params ?? {}, null, 2));
    setNotes(node.data.notes ?? "");
  }, [node]);

  const parsed = useMemo(() => safeParseJson(paramsText), [paramsText]);
  const valid = parsed.ok;

  const submit = () => {
    if (!valid) return;
    onSave({
      label: label.trim() || node?.data.kind || "",
      params: parsed.value,
      notes: notes.trim(),
    });
    onClose();
  };

  return (
    <>
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/60 transition-opacity",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onClose}
        aria-hidden
      />
      <aside
        role="dialog"
        aria-hidden={!open}
        className={cn(
          "fixed right-0 top-0 z-50 flex h-screen w-full max-w-lg flex-col border-l border-[var(--border-default)] bg-[var(--bg-surface)] shadow-2xl transition-transform",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <div className="flex h-[52px] items-center justify-between border-b border-[var(--border-default)] px-4">
          <div className="flex flex-col">
            <span className="text-sm font-semibold">Edit node</span>
            <span className="font-mono text-[10px] text-[var(--text-secondary)]">
              {node?.data.kind ?? ""} · {node?.id ?? ""}
            </span>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex flex-1 flex-col gap-3 overflow-auto p-4">
          <div className="flex flex-col gap-1">
            <Label htmlFor="node-label">Label</Label>
            <Input
              id="node-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              autoFocus={open}
            />
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-1">
            <Label htmlFor="node-params">Params (JSON)</Label>
            <div className="min-h-[260px] flex-1">
              <CodeEditor value={paramsText} onChange={setParamsText} language="json" />
            </div>
            {!valid ? (
              <span className="text-xs text-[var(--neg-fg)]">{parsed.error}</span>
            ) : null}
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="node-notes">Notes</Label>
            <Input id="node-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-[var(--border-default)] p-3">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!valid} className="gap-2">
            <Save className="h-4 w-4" /> Save
          </Button>
        </div>
      </aside>
    </>
  );
}

function safeParseJson(text: string): { ok: true; value: Record<string, unknown> } | { ok: false; error: string } {
  if (!text.trim()) return { ok: true, value: {} };
  try {
    const parsed = JSON.parse(text) as unknown;
    if (parsed == null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { ok: false, error: "Params must be a JSON object" };
    }
    return { ok: true, value: parsed as Record<string, unknown> };
  } catch (err) {
    return { ok: false, error: `Invalid JSON: ${(err as Error).message}` };
  }
}
