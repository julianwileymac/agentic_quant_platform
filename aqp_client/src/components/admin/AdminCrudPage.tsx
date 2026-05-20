import { Plus, RefreshCcw, Trash2 } from "lucide-react";
import { type ReactNode, useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { PageContainer } from "@/components/shell/PageContainer";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";

interface AdminCrudPageProps<T> {
  title: string;
  subtitle: string;
  /** Stable identity for table rows. */
  rowKey: (row: T) => string;
  /** Columns rendered in the DataTable. */
  columns: ColumnDef<T>[];
  /** Data fetched from the typed API wrapper. */
  rows: T[];
  loading: boolean;
  onRefresh: () => void;
  /** Returns the typed-confirmation phrase for deleting `row`. */
  confirmDeletePhrase: (row: T) => string;
  /** Async delete callback. Throws to surface an error toast. */
  onDelete: (row: T) => Promise<void>;
  /** Friction-dialog title for delete (e.g. `Delete org foo`). */
  deleteTitle: (row: T) => string;
  /** Plain-language consequence for the friction dialog. */
  deleteConsequence: string;
  /** Slot for the Create / Edit Sheet rendered by the consumer. */
  createSheet: (state: {
    open: boolean;
    setOpen: (open: boolean) => void;
    onSaved: () => void;
  }) => ReactNode;
  /** Optional click-through (e.g. workspace -> sub-resources Sheet). */
  onRowClick?: (row: T) => void;
  /** Empty-state slot. */
  emptyState?: ReactNode;
  /** Additional buttons next to Refresh / New. */
  toolbarExtras?: ReactNode;
}

/**
 * Reusable admin CRUD scaffold. Each consumer plugs in:
 *   - typed columns for the DataTable
 *   - rows + loading + onRefresh from a useApiQuery
 *   - a Sheet-rendered create form
 *   - an onDelete handler + friction-phrase derivation
 *
 * Cuts each Phase 5 admin route from ~120 LOC to ~40.
 */
export function AdminCrudPage<T>({
  title,
  subtitle,
  rowKey,
  columns,
  rows,
  loading,
  onRefresh,
  confirmDeletePhrase,
  onDelete,
  deleteTitle,
  deleteConsequence,
  createSheet,
  onRowClick,
  emptyState,
  toolbarExtras,
}: AdminCrudPageProps<T>) {
  const [createOpen, setCreateOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<T | null>(null);

  const submit = async () => {
    if (!pendingDelete) return;
    try {
      await onDelete(pendingDelete);
      toast.success(deleteTitle(pendingDelete));
      onRefresh();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Delete failed: ${msg}`);
    } finally {
      setPendingDelete(null);
    }
  };

  const augmentedColumns: ColumnDef<T>[] = [
    ...columns,
    {
      key: "_actions",
      header: "Actions",
      width: 110,
      render: (row) => (
        <Button
          variant="ghost"
          size="sm"
          onClick={(e) => {
            e.stopPropagation();
            setPendingDelete(row);
          }}
          className="gap-1 text-[var(--neg-fg)]"
        >
          <Trash2 className="h-3.5 w-3.5" /> Delete
        </Button>
      ),
    },
  ];

  return (
    <PageContainer
      title={title}
      subtitle={subtitle}
      extra={
        <div className="flex items-center gap-2">
          {toolbarExtras}
          <Button variant="ghost" size="sm" onClick={onRefresh}>
            <RefreshCcw className="h-4 w-4" /> Refresh
          </Button>
          <Button size="sm" onClick={() => setCreateOpen(true)} className="gap-2">
            <Plus className="h-4 w-4" /> New
          </Button>
        </div>
      }
    >
      <Card className="h-[calc(100vh-180px)]">
        <CardContent className="h-full p-0">
          <DataTable<T>
            rows={rows}
            rowKey={rowKey}
            columns={augmentedColumns}
            {...(onRowClick ? { onRowClick } : {})}
            emptyState={loading ? <span>Loading…</span> : emptyState ?? <span>No rows.</span>}
          />
        </CardContent>
      </Card>

      {createSheet({
        open: createOpen,
        setOpen: setCreateOpen,
        onSaved: () => {
          setCreateOpen(false);
          onRefresh();
        },
      })}

      {pendingDelete ? (
        <ConfirmFrictionDialog
          open
          onOpenChange={(open) => !open && setPendingDelete(null)}
          title={deleteTitle(pendingDelete)}
          consequence={deleteConsequence}
          details={[]}
          confirmPhrase={confirmDeletePhrase(pendingDelete)}
          confirmLabel="Delete"
          confirmVariant="destructive"
          onConfirm={submit}
        />
      ) : null}
    </PageContainer>
  );
}

/** Re-export so consumers can import ColumnDef without two paths. */
export type { ColumnDef };

/**
 * Sheet form footer helper used by every CRUD route. Saves go through
 * the consumer's onSubmit; cancel just closes the sheet.
 */
export function CrudSheetFooter({
  onCancel,
  onSubmit,
  saveLabel = "Save",
  saving = false,
  saveDisabled = false,
}: {
  onCancel: () => void;
  onSubmit: () => void;
  saveLabel?: string;
  saving?: boolean;
  saveDisabled?: boolean;
}) {
  return (
    <>
      <Button variant="outline" onClick={onCancel} disabled={saving}>
        Cancel
      </Button>
      <Button onClick={onSubmit} disabled={saving || saveDisabled}>
        {saving ? "Saving…" : saveLabel}
      </Button>
    </>
  );
}
