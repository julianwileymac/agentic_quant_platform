import { X } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface SymbolsInputProps {
  value: string[];
  onChange: (next: string[]) => void;
  label?: string;
  placeholder?: string;
}

/**
 * Minimal multi-tag input for symbol selection. Press Enter / comma to
 * commit; click the X to remove. Intentionally framework-light to stay
 * compatible with the existing `<input>` styling tokens.
 */
export function SymbolsInput({
  value,
  onChange,
  label,
  placeholder = "Type a symbol and press Enter",
}: SymbolsInputProps) {
  const [pending, setPending] = useState("");

  const commit = (raw: string) => {
    const trimmed = raw.trim().toUpperCase();
    if (!trimmed) return;
    if (value.includes(trimmed)) return;
    onChange([...value, trimmed]);
  };

  return (
    <div className="space-y-1">
      {label ? <Label>{label}</Label> : null}
      <div className="flex min-h-9 flex-wrap gap-1 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-1">
        {value.map((sym) => (
          <Badge key={sym} variant="secondary" className="gap-1">
            {sym}
            <button
              type="button"
              onClick={() => onChange(value.filter((s) => s !== sym))}
              className="text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              aria-label={`Remove ${sym}`}
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
        <Input
          className="flex-1 border-0 bg-transparent px-1 shadow-none focus-visible:ring-0"
          value={pending}
          placeholder={placeholder}
          onChange={(e) => setPending(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              commit(pending);
              setPending("");
            }
            if (e.key === "Backspace" && !pending && value.length) {
              onChange(value.slice(0, -1));
            }
          }}
          onBlur={() => {
            if (pending) {
              commit(pending);
              setPending("");
            }
          }}
        />
      </div>
    </div>
  );
}
