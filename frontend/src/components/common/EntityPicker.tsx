import { Check, ChevronDown, Search, X } from "lucide-react";
import {
  type KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { Button } from "@/components/ui/button";
import { CacheApi, type CacheCategory, type CacheItem } from "@/lib/api/cache";
import { useApiQuery } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

export interface EntityPickerProps {
  /** Required. Cache category that backs this dropdown. */
  kind: CacheCategory;
  /** Currently selected value (the entity ``name`` field). */
  value: string | null | undefined;
  onChange: (value: string | null) => void;
  /** Allow free-text values not present in the cache. Off by default. */
  allowCustom?: boolean;
  /** Disable the dropdown entirely. */
  disabled?: boolean;
  /** Optional aria-label / placeholder text. */
  placeholder?: string;
  /** Render an X button that clears the selection. */
  clearable?: boolean;
  /** Pass-through className applied to the outer container. */
  className?: string;
  /**
   * Optional secondary label rendered next to each item in the menu.
   * Defaults to ``item.kind`` for sinks / connectors / kinds, and
   * ``item.iceberg_identifier`` for datasets.
   */
  secondaryField?: string;
}

const DEFAULT_SECONDARY: Partial<Record<CacheCategory, string>> = {
  datasets: "iceberg_identifier",
  airbyte_connectors: "kind",
  sink_names: "kind",
  projects: "workspace_id",
  workspaces: "org_id",
  labs: "workspace_id",
  experiments: "kind",
  tests: "assertion_kind",
  users: "email",
  agents: "kind",
  bots: "kind",
  resources: "resource_type",
  strategy_templates: "framework",
};

const PLACEHOLDER_LABEL: Record<CacheCategory, string> = {
  datasets: "Select dataset...",
  namespaces: "Select namespace...",
  sink_kinds: "Select sink kind...",
  sink_names: "Select sink...",
  airbyte_connectors: "Select Airbyte connector...",
  projects: "Select project...",
  credentials: "Select credential...",
  dataset_kinds: "Select dataset kind...",
  // Phase 5 tenancy + specs
  organizations: "Select organization...",
  teams: "Select team...",
  users: "Select user...",
  workspaces: "Select workspace...",
  labs: "Select lab...",
  experiments: "Select experiment...",
  tests: "Select test...",
  agents: "Select agent spec...",
  bots: "Select bot...",
  rl_experiments: "Select RL experiment...",
  analysis_specs: "Select analysis spec...",
  // Phase 5 + 7 polymorphic content
  resources: "Select resource...",
  strategy_templates: "Select strategy template...",
};

/**
 * Async, searchable, whitelist-only entity dropdown.
 *
 * Backed by the FastAPI ``/cache/{category}`` endpoint, which serves
 * sub-millisecond ``ZRANGEBYLEX`` results from the Phase-0 metadata
 * cache. ``allowCustom`` is OFF by default — that's the whole point:
 * users can only pick entities that already exist on the backend, so
 * spelling errors / capitalisation drift can't reach Postgres.
 */
export function EntityPicker({
  kind,
  value,
  onChange,
  allowCustom = false,
  disabled = false,
  placeholder,
  clearable = true,
  className,
  secondaryField,
}: EntityPickerProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [highlight, setHighlight] = useState(0);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const debouncedSearch = useDebounced(search, 150);

  const query = useApiQuery<{ items: CacheItem[]; total: number; next_cursor: number | null }>({
    queryKey: ["cache", kind, debouncedSearch],
    path: `/cache/${kind}`,
    query: { prefix: debouncedSearch, limit: 50 },
    staleTime: 5_000,
    enabled: open,
  });

  const items = useMemo(() => query.data?.items ?? [], [query.data?.items]);
  const showCustom =
    allowCustom &&
    debouncedSearch.length > 0 &&
    !items.some((item) => normalise(item.name) === normalise(debouncedSearch));

  const totalChoices = items.length + (showCustom ? 1 : 0);

  useEffect(() => {
    if (!open) return;
    setHighlight(0);
  }, [open, debouncedSearch]);

  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (!containerRef.current) return;
      if (containerRef.current.contains(event.target as Node)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const commit = useCallback(
    (next: string | null) => {
      onChange(next);
      setOpen(false);
      setSearch("");
    },
    [onChange],
  );

  const handleKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlight((h) => Math.min(h + 1, Math.max(0, totalChoices - 1)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlight((h) => Math.max(0, h - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (highlight < items.length) {
        commit(items[highlight]?.name ?? null);
      } else if (showCustom) {
        commit(debouncedSearch);
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  const secondaryKey = secondaryField ?? DEFAULT_SECONDARY[kind];

  return (
    <div ref={containerRef} className={cn("relative w-full", className)}>
      <Button
        type="button"
        variant="outline"
        size="default"
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        className={cn(
          "w-full justify-between font-normal text-left",
          !value && "text-[var(--text-muted)]",
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="truncate">{value || placeholder || PLACEHOLDER_LABEL[kind]}</span>
        <span className="ml-2 flex items-center gap-1">
          {clearable && value ? (
            <span
              role="button"
              aria-label="Clear selection"
              onClick={(event) => {
                event.stopPropagation();
                commit(null);
              }}
              className="rounded p-0.5 text-[var(--text-muted)] hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)]"
            >
              <X className="h-3.5 w-3.5" />
            </span>
          ) : null}
          <ChevronDown className="h-4 w-4 text-[var(--text-muted)]" />
        </span>
      </Button>

      {open && !disabled ? (
        <div
          role="listbox"
          className="absolute z-50 mt-1 w-full overflow-hidden rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] shadow-lg"
        >
          <div className="flex items-center gap-2 border-b border-[var(--border-default)] px-2 py-1.5">
            <Search className="h-3.5 w-3.5 text-[var(--text-muted)]" />
            <input
              ref={inputRef}
              autoFocus
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onKeyDown={handleKey}
              placeholder={placeholder || PLACEHOLDER_LABEL[kind]}
              className="h-7 w-full bg-transparent text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
            />
          </div>
          <div className="max-h-64 overflow-y-auto py-1 text-sm">
            {query.isPending ? (
              <div className="px-3 py-2 text-xs text-[var(--text-muted)]">
                Loading...
              </div>
            ) : null}
            {!query.isPending && items.length === 0 && !showCustom ? (
              <div className="px-3 py-2 text-xs text-[var(--text-muted)]">
                No matches.
              </div>
            ) : null}
            {items.map((item, idx) => {
              const secondary = secondaryKey ? String(item[secondaryKey] ?? "") : "";
              const active = idx === highlight;
              const selected = value === item.name;
              return (
                <button
                  type="button"
                  key={`${item.id}-${item.name}`}
                  onMouseEnter={() => setHighlight(idx)}
                  onClick={() => commit(item.name)}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left",
                    active && "bg-[var(--bg-app)]",
                  )}
                  role="option"
                  aria-selected={selected}
                >
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate text-[var(--text-primary)]">
                      {item.name}
                    </span>
                    {secondary ? (
                      <span className="truncate font-mono text-[10px] text-[var(--text-muted)]">
                        {secondary}
                      </span>
                    ) : null}
                  </span>
                  {selected ? (
                    <Check className="h-3.5 w-3.5 text-[var(--info-fg)]" />
                  ) : null}
                </button>
              );
            })}
            {showCustom ? (
              <button
                type="button"
                onMouseEnter={() => setHighlight(items.length)}
                onClick={() => commit(debouncedSearch)}
                className={cn(
                  "flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left",
                  highlight === items.length && "bg-[var(--bg-app)]",
                )}
              >
                <span className="text-[var(--text-primary)]">
                  Use &quot;{debouncedSearch}&quot;
                </span>
                <span className="font-mono text-[10px] text-[var(--text-muted)]">
                  custom
                </span>
              </button>
            ) : null}
          </div>
          <div className="border-t border-[var(--border-default)] px-3 py-1 text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
            {kind.replace(/_/g, " ")} cache · {query.data?.total ?? 0} entries
          </div>
        </div>
      ) : null}
    </div>
  );
}

function normalise(value: string): string {
  return String(value || "").toLowerCase().trim();
}

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const handle = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(handle);
  }, [value, delay]);
  return debounced;
}

// CacheApi imported only to ensure tree-shaking doesn't drop the typed client
// from the build when EntityPicker is the sole consumer.
void CacheApi;
