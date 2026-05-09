import { json } from "@codemirror/lang-json";
import { python } from "@codemirror/lang-python";
import { sql } from "@codemirror/lang-sql";
import { EditorState } from "@codemirror/state";
import { oneDark } from "@codemirror/theme-one-dark";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

interface CodeEditorProps {
  value: string;
  onChange?: (value: string) => void;
  language?: "python" | "json" | "sql";
  readOnly?: boolean;
  className?: string;
  height?: string | number;
}

/**
 * CodeMirror 6 single-file editor used by the `/ide` route per
 * blueprint Directive 4 ("integrate the CodeMirror library...
 * native Python or JSON editing directly within the dashboard").
 * Dark `oneDark` theme matches the AQP token palette.
 */
export function CodeEditor({
  value,
  onChange,
  language = "python",
  readOnly = false,
  className,
  height = "100%",
}: CodeEditorProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (!containerRef.current) return;
    const langExtension =
      language === "json" ? json() : language === "sql" ? sql() : python();
    const state = EditorState.create({
      doc: value,
      extensions: [
        lineNumbers(),
        history(),
        keymap.of([...defaultKeymap, ...historyKeymap]),
        oneDark,
        langExtension,
        EditorView.editable.of(!readOnly),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            onChangeRef.current?.(update.state.doc.toString());
          }
        }),
        EditorView.theme({
          "&": { height: typeof height === "number" ? `${height}px` : height },
          ".cm-scroller": { fontFamily: "var(--font-mono)" },
        }),
      ],
    });
    const view = new EditorView({ state, parent: containerRef.current });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, [language, readOnly, height]);

  // Sync external `value` changes that didn't originate from the editor
  // itself (e.g. loading a different snippet from the file list).
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (current === value) return;
    view.dispatch({ changes: { from: 0, to: current.length, insert: value } });
  }, [value]);

  return (
    <div
      ref={containerRef}
      className={cn(
        "h-full w-full overflow-hidden rounded-md border border-[var(--border-default)]",
        className,
      )}
    />
  );
}
