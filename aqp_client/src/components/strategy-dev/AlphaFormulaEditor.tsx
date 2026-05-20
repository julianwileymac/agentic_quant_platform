import { useEffect, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import {
  QuantAgentsApi,
  type FactorCompilePreviewResponse,
} from "@/lib/api/quantAgents";

import { CodeEditor } from "@/components/common/CodeEditor";

interface Props {
  value: string;
  onChange: (value: string) => void;
  /** Debounce ms before auto-compile-preview fires. Default 400. */
  debounceMs?: number;
  /** Hide the live compile feedback strip (useful inside dense layouts). */
  hideStatusStrip?: boolean;
}

/**
 * Phase B editor for symbolic alpha factor formulas. Wraps the
 * canonical CodeEditor (CodeMirror 6) and adds a debounced auto-
 * compile-preview against `/quant-agents/factor/compile-preview`.
 *
 * The actual operator + field whitelist enforcement happens
 * server-side (AGENTS.md rule 39, AST sandbox). The editor only
 * surfaces the result — it never `eval`s the formula client-side.
 */
export function AlphaFormulaEditor({
  value,
  onChange,
  debounceMs = 400,
  hideStatusStrip = false,
}: Props) {
  const [preview, setPreview] = useState<FactorCompilePreviewResponse | null>(null);
  const [pending, setPending] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    const trimmed = value.trim();
    if (!trimmed) {
      setPreview(null);
      return;
    }
    setPending(true);
    timerRef.current = setTimeout(() => {
      QuantAgentsApi.compilePreview({ formula: trimmed })
        .then((res) => {
          setPreview(res);
        })
        .catch((err) => {
          setPreview({
            ok: false,
            formula: trimmed,
            used_operators: [],
            used_fields: [],
            error: err instanceof Error ? err.message : String(err),
          });
        })
        .finally(() => setPending(false));
    }, debounceMs);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [value, debounceMs]);

  const status = useMemo(() => {
    if (pending) return { variant: "secondary" as const, text: "compiling..." };
    if (!preview) return { variant: "outline" as const, text: "empty" };
    if (preview.ok) return { variant: "positive" as const, text: "OK" };
    return { variant: "negative" as const, text: "rejected" };
  }, [pending, preview]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="min-h-[160px] flex-1">
        <CodeEditor
          value={value}
          onChange={onChange}
          language="python"
          height="100%"
        />
      </div>
      {!hideStatusStrip ? (
        <div className="rounded border border-[var(--border-default)] p-2 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={status.variant}>{status.text}</Badge>
            {preview?.ok ? (
              <>
                <span className="text-[var(--text-secondary)]">operators:</span>
                <span className="font-mono">
                  {preview.used_operators.join(", ") || "—"}
                </span>
                <span className="text-[var(--text-secondary)]">fields:</span>
                <span className="font-mono">
                  {preview.used_fields.join(", ") || "—"}
                </span>
              </>
            ) : null}
          </div>
          {preview?.error ? (
            <pre className="mt-1 overflow-auto whitespace-pre-wrap text-[10px] text-[var(--neg-fg)]">
              {preview.error}
            </pre>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
