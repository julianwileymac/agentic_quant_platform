import { cn } from "@/lib/utils";

interface AspectPayloadViewerProps {
  value: unknown;
  className?: string;
}

export function AspectPayloadViewer({ value, className }: AspectPayloadViewerProps) {
  return (
    <div
      className={cn(
        "rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3 font-mono text-xs",
        className,
      )}
    >
      <JsonNode label={null} value={value} depth={0} />
    </div>
  );
}

function JsonNode({
  label,
  value,
  depth,
}: {
  label: string | null;
  value: unknown;
  depth: number;
}) {
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <JsonLeaf label={label} value="[]" />;
    }
    return (
      <details open={depth < 1} className="mb-1">
        <summary className="cursor-pointer select-none text-[var(--text-secondary)]">
          {label ? `${label}: ` : ""}
          <span>[{value.length}]</span>
        </summary>
        <div className="ml-3 mt-1 border-l border-[var(--border-default)] pl-3">
          {value.map((entry, index) => (
            <JsonNode key={`${index}-${typeof entry}`} label={String(index)} value={entry} depth={depth + 1} />
          ))}
        </div>
      </details>
    );
  }
  if (isRecord(value)) {
    const keys = Object.keys(value);
    if (keys.length === 0) {
      return <JsonLeaf label={label} value="{}" />;
    }
    return (
      <details open={depth < 1} className="mb-1">
        <summary className="cursor-pointer select-none text-[var(--text-secondary)]">
          {label ? `${label}: ` : ""}
          <span>{"{"}{keys.length}{"}"}</span>
        </summary>
        <div className="ml-3 mt-1 border-l border-[var(--border-default)] pl-3">
          {keys.map((key) => (
            <JsonNode key={key} label={key} value={value[key]} depth={depth + 1} />
          ))}
        </div>
      </details>
    );
  }
  return <JsonLeaf label={label} value={formatPrimitive(value)} />;
}

function JsonLeaf({
  label,
  value,
}: {
  label: string | null;
  value: string;
}) {
  return (
    <div className="mb-1 break-all">
      {label ? (
        <span className="text-[var(--text-secondary)]">{label}: </span>
      ) : null}
      <span className="text-[var(--text-primary)]">{value}</span>
    </div>
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatPrimitive(value: unknown): string {
  if (typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number" || typeof value === "boolean" || value === null) {
    return String(value);
  }
  if (typeof value === "undefined") {
    return "undefined";
  }
  return JSON.stringify(value);
}
