import { useEffect, useState } from "react";

import { EntityPicker } from "@/components/common/EntityPicker";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type DatasetColumn, getDatasetColumns } from "@/lib/analysis/api";

export interface DatasetSelection {
  identifier: string;
  limit: number;
  columns: DatasetColumn[];
}

interface Props {
  value: DatasetSelection;
  onChange: (next: DatasetSelection) => void;
}

/**
 * Picks an Iceberg dataset by identifier ("namespace.table"), with a
 * lightweight column-list fetch via GET /analysis/datasets/columns.
 *
 * Intentionally minimal — the v1 lab focuses on the Iceberg path.
 * Inline dataset_cfg / dataset_version_id flows can be added later
 * without touching every tab.
 */
export function DatasetPicker({ value, onChange }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!value.identifier) return;
    let cancelled = false;
    setBusy(true);
    setError(null);
    getDatasetColumns(value.identifier)
      .then((res) => {
        if (cancelled) return;
        onChange({ ...value, columns: res.columns });
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        onChange({ ...value, columns: [] });
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value.identifier]);

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
      <div className="flex flex-col gap-1">
        <Label htmlFor="ds-identifier">Iceberg identifier</Label>
        {/* Phase 6 — whitelist-only dataset picker. Falls back to
            free-text only when the cache returns nothing (e.g. a
            brand-new namespace not yet ingested). */}
        <EntityPicker
          kind="datasets"
          value={value.identifier || null}
          onChange={(next) => onChange({ ...value, identifier: next ?? "" })}
          allowCustom
          placeholder="aqp_silver_yfinance.equities_daily"
          secondaryField="iceberg_identifier"
        />
        <p className="text-xs text-[var(--text-secondary)]">
          {busy
            ? "Loading columns..."
            : error
              ? `Error: ${error}`
              : value.columns.length > 0
                ? `${value.columns.length} columns`
                : "Pick a dataset to load columns"}
        </p>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="ds-limit">Row cap</Label>
        <Input
          id="ds-limit"
          type="number"
          min={1}
          max={200000}
          value={value.limit}
          onChange={(e) =>
            onChange({ ...value, limit: Number(e.target.value || 0) })
          }
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label>Columns</Label>
        <div className="flex flex-wrap gap-1 overflow-y-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-2 text-xs h-[68px]">
          {value.columns.length === 0 ? (
            <span className="text-[var(--text-secondary)]">
              (column metadata appears here)
            </span>
          ) : (
            value.columns.map((c) => (
              <span
                key={c.name}
                className="rounded-sm border border-[var(--border-default)] bg-[var(--bg-elevated)] px-2 py-0.5"
                title={c.dtype}
              >
                {c.name}
              </span>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
