"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/cn";

interface CodeBlockProps {
  code: string;
  language?: string;
  /** Optional filename badge in the top-left of the chrome. */
  filename?: string;
  /** When true, shows a small copy button in the top-right. */
  copyable?: boolean;
  className?: string;
}

/**
 * Code block with a chrome header (language tab + optional filename + copy)
 * and `<pre><code>` body.
 *
 * Intentionally no JS syntax highlighter — keeps the bundle small. Code is
 * styled via CSS only (monospace + theme tokens).
 */
export function CodeBlock({
  code,
  language = "bash",
  filename,
  copyable = true,
  className,
}: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API unavailable; ignore.
    }
  };

  return (
    <div
      className={cn("overflow-hidden rounded-lg", className)}
      style={{
        background: "#0b1220",
        border: "1px solid var(--border-default)",
        boxShadow: "var(--shadow-card)",
      }}
    >
      <div
        className="flex items-center justify-between border-b px-4 py-2"
        style={{
          borderColor: "var(--border-default)",
          background: "rgba(255,255,255,0.02)",
        }}
      >
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span
              className="block h-2.5 w-2.5 rounded-full"
              style={{ background: "#ff5f57" }}
            />
            <span
              className="block h-2.5 w-2.5 rounded-full"
              style={{ background: "#febc2e" }}
            />
            <span
              className="block h-2.5 w-2.5 rounded-full"
              style={{ background: "#28c840" }}
            />
          </div>
          {filename ? (
            <span
              className="text-xs font-medium"
              style={{ color: "var(--text-secondary)" }}
            >
              {filename}
            </span>
          ) : null}
          <span
            className="rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
            style={{
              color: "var(--text-muted)",
              background: "rgba(255,255,255,0.05)",
            }}
          >
            {language}
          </span>
        </div>
        {copyable ? (
          <button
            type="button"
            onClick={handleCopy}
            className="inline-flex items-center gap-1 rounded p-1.5 text-xs transition-colors hover:bg-white/10"
            style={{ color: "var(--text-secondary)" }}
            aria-label="Copy code"
          >
            {copied ? (
              <>
                <Check size={12} style={{ color: "var(--pos-fg)" }} />
                <span style={{ color: "var(--pos-fg)" }}>Copied</span>
              </>
            ) : (
              <>
                <Copy size={12} />
                <span>Copy</span>
              </>
            )}
          </button>
        ) : null}
      </div>
      <pre
        className="overflow-x-auto px-4 py-4 text-sm leading-relaxed"
        style={{
          fontFamily:
            'ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, monospace',
          color: "#d4d4d8",
          background: "#0b1220",
        }}
      >
        <code>{code}</code>
      </pre>
    </div>
  );
}
