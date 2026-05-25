/**
 * Runbooks index — TipTap editor + saved list.
 *
 * Skeleton: ``@tiptap/react`` + ``@tiptap/starter-kit`` only. Once
 * the admin persistence layer ships a real DB this hooks the
 * `/admin/runbooks` endpoints to those backing tables; today the
 * BFF keeps them in-memory.
 *
 * The TipTap deps are imported dynamically so the runbooks tab
 * doesn't add the editor bundle to the dashboard / accounts path.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useState } from "react";

import { adminApi } from "@/lib/api";

const RunbookEditor = lazy(() => import("./editor"));

export function RunbooksIndex() {
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ["runbooks"],
    queryFn: adminApi.listRunbooks,
  });
  const [title, setTitle] = useState("Untitled runbook");
  const [doc, setDoc] = useState<unknown>(_emptyDoc());
  const save = useMutation({
    mutationFn: () => adminApi.upsertRunbook({ title, doc, tags: [] }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runbooks"] }),
  });

  return (
    <section className="space-y-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Runbooks</h1>
          <p className="text-sm text-muted-foreground">
            Lightweight TipTap editor for ops runbooks. Persistence is
            scoped to the admin BFF; no Yjs / Hocuspocus collab in this
            PR.
          </p>
        </div>
        <button
          type="button"
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
          onClick={() => save.mutate()}
          disabled={save.isPending}
        >
          {save.isPending ? "Saving..." : "Save runbook"}
        </button>
      </header>
      <div className="grid grid-cols-3 gap-4">
        <aside className="rounded-lg border bg-card p-4">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Recent runbooks
          </h2>
          {list.isLoading ? <p className="text-sm">Loading...</p> : null}
          <ul className="space-y-2 text-sm">
            {list.data?.runbooks.map((rb) => (
              <li key={rb.id} className="rounded border p-2">
                <div className="font-medium">{rb.title}</div>
                <div className="text-xs text-muted-foreground">
                  {new Date(rb.updated_at).toLocaleString()}
                </div>
              </li>
            ))}
          </ul>
        </aside>
        <div className="col-span-2 space-y-3 rounded-lg border bg-card p-4">
          <input
            className="w-full rounded-md border px-3 py-2 text-sm font-semibold"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <Suspense fallback={<p className="text-sm">Loading editor...</p>}>
            <RunbookEditor initialDoc={doc} onChange={setDoc} />
          </Suspense>
        </div>
      </div>
    </section>
  );
}

function _emptyDoc() {
  return {
    type: "doc",
    content: [
      {
        type: "paragraph",
        content: [
          {
            type: "text",
            text: "Start writing your runbook here...",
          },
        ],
      },
    ],
  };
}
