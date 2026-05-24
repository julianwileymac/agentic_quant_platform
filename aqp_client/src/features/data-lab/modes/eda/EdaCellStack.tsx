import {
  Code2,
  Database,
  Play,
  RotateCw,
  Trash2,
} from "lucide-react";
import type { DragEvent as ReactDragEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { CodeEditor } from "@/components/common/CodeEditor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { LAB_DRAG_MIME } from "@/features/data-lab/catalog/DataBrowser";
import { useLabStore } from "@/features/data-lab/state/labStore";
import { useLabChannel } from "@/features/data-lab/ws/useLabChannel";
import type { EdaCellResultEnvelope } from "@/features/data-lab/ws/envelopes";
import { promoteCellToTestingGraph } from "@/lib/api/lab";

type CellKind = "python" | "sql";

interface EdaCell {
  id: string;
  kind: CellKind;
  source: string;
  ord: number;
  /** Marked stale by either user edit or upstream re-execution. */
  stale: boolean;
  /** Last server-side execution result envelope. */
  lastResult?: EdaCellResultEnvelope | null;
  /** Direct upstream cell ids (rendered as dep chips). */
  upstream?: string[];
}

function freshCell(kind: CellKind = "python", ord = 0): EdaCell {
  return {
    id: `c-${crypto.randomUUID().slice(0, 8)}`,
    kind,
    source: kind === "python" ? "" : "-- SELECT * FROM …",
    ord,
    stale: true,
  };
}

/**
 * EDA cell stack — Phase 1 implementation.
 *
 * - CodeMirror 6 Python / SQL cells (frontend rule 7 — CodeMirror is
 *   the canonical browser editor; NO Monaco).
 * - Each cell carries a "stale" pill the user can refresh by clicking
 *   Run, and a "Promote to node" context-menu that pushes the cell
 *   source into the active Testing GraphSpec as a snippet.python node
 *   (Phase 5 hardens this with the Tier-1/Tier-2 snippet runners).
 * - Per-session WS channel (the LabShell owns the multiplex) forwards
 *   ``eda.exec`` envelopes to the server kernel and listens for
 *   ``eda.cell.result`` envelopes to repopulate the stale_ids list.
 */
export function EdaCellStack() {
  const [cells, setCells] = useState<EdaCell[]>(() => [freshCell("python", 0)]);
  const [promoting, setPromoting] = useState<string | null>(null);
  const sessionId = useLabStore((s) => s.sessionId);
  const labId = useLabStore((s) => s.labId);
  const pushEnvelope = useLabStore((s) => s.pushEnvelope);
  const recentEnvelopes = useLabStore((s) => s.recentEnvelopes);
  const seenCellIdsRef = useRef<Set<string>>(new Set());
  const navigate = useNavigate();

  const handleEnvelope = useCallback(
    (env: EdaCellResultEnvelope) => {
      // Mirror into Zustand store so the global RunHistory drawer can
      // surface EDA results alongside Testing run frames.
      pushEnvelope(env);
      setCells((prev) =>
        prev.map((c) => {
          if (c.id === env.cell_id) {
            return { ...c, lastResult: env, stale: false };
          }
          if (env.stale_ids.includes(c.id)) {
            return { ...c, stale: true };
          }
          return c;
        }),
      );
      seenCellIdsRef.current.add(env.cell_id);
    },
    [pushEnvelope],
  );

  const channel = useLabChannel({
    sessionId,
    onEnvelope: (env) => {
      if (env.kind === "eda.cell.result") {
        handleEnvelope(env);
      }
    },
  });

  // Surface any historical envelopes that arrived before this
  // component mounted (the shell's channel pumped them into Zustand).
  useEffect(() => {
    for (const env of recentEnvelopes) {
      if (env.kind === "eda.cell.result" && !seenCellIdsRef.current.has(env.cell_id)) {
        handleEnvelope(env);
      }
    }
  }, [recentEnvelopes, handleEnvelope]);

  const onSourceChange = useCallback((id: string, source: string) => {
    setCells((prev) =>
      prev.map((c) => (c.id === id ? { ...c, source, stale: true } : c)),
    );
  }, []);

  const onRunCell = useCallback(
    (cell: EdaCell) => {
      if (channel.status !== "open") {
        toast.warning("Lab WS not connected yet — try again in a second.");
        return;
      }
      channel.send({
        kind: "eda.exec",
        cell_id: cell.id,
        code: cell.source,
        v: 1,
      });
    },
    [channel],
  );

  const onAddCell = useCallback((kind: CellKind) => {
    setCells((prev) => [...prev, freshCell(kind, prev.length)]);
  }, []);

  const onDeleteCell = useCallback((id: string) => {
    setCells((prev) => prev.filter((c) => c.id !== id));
  }, []);

  const onCellDrop = useCallback(
    (cellId: string, event: ReactDragEvent<HTMLElement>) => {
      // Honour either the rich Lab payload (preserves the catalog
      // entry metadata for future drop targets) or the plain-text
      // fallback that CodeMirror / textarea drops already produce.
      let insertion = "";
      try {
        const rich = event.dataTransfer.getData(LAB_DRAG_MIME);
        if (rich) {
          const parsed = JSON.parse(rich) as { insertion?: string };
          insertion = parsed.insertion ?? "";
        }
      } catch {
        insertion = "";
      }
      if (!insertion) {
        insertion = event.dataTransfer.getData("text/plain") || "";
      }
      if (!insertion) return;
      event.preventDefault();
      setCells((prev) =>
        prev.map((c) =>
          c.id === cellId
            ? {
                ...c,
                source: c.source ? `${c.source.trimEnd()}\n${insertion}` : insertion,
                stale: true,
              }
            : c,
        ),
      );
    },
    [],
  );

  const onCellDragOver = useCallback((event: ReactDragEvent<HTMLElement>) => {
    if (
      event.dataTransfer.types.includes(LAB_DRAG_MIME) ||
      event.dataTransfer.types.includes("text/plain")
    ) {
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
    }
  }, []);

  const onPromoteToNode = useCallback(
    async (cell: EdaCell) => {
      if (!labId) {
        toast.warning("Open a lab first — promote needs a lab id to scope the snippet.");
        return;
      }
      if (cell.kind !== "python") {
        toast.warning(
          "Only Python cells promote via snippet.python today. SQL promotion ships with snippet.sql.",
        );
        return;
      }
      if (!cell.source.trim()) {
        toast.warning("Cell is empty — write something before promoting.");
        return;
      }
      setPromoting(cell.id);
      try {
        const graph = await promoteCellToTestingGraph(sessionId, cell.id, {
          lab_id: labId,
          source: cell.source,
          cell_label: cell.kind === "python" ? "EDA cell" : "EDA SQL cell",
        });
        toast.success(
          `Cell ${cell.id} promoted to graph ${graph.name} — opening Testing mode.`,
        );
        navigate(`/labs/${labId}/workspace/testing?graph=${graph.id}`);
      } catch (err) {
        toast.error(
          `Promote failed: ${err instanceof Error ? err.message : String(err)}`,
        );
      } finally {
        setPromoting(null);
      }
    },
    [labId, navigate, sessionId],
  );

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <Card>
        <CardContent className="flex items-center gap-2 py-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onAddCell("python")}
            className="gap-2"
          >
            <Code2 className="h-4 w-4" /> + Python cell
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onAddCell("sql")}
            className="gap-2"
          >
            <Database className="h-4 w-4" /> + SQL cell
          </Button>
          <div className="flex-1" />
          <span className="text-xs text-muted-foreground">
            session <code className="font-mono">{sessionId}</code> · {cells.length} cells
          </span>
        </CardContent>
      </Card>
      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-1">
        {cells.map((cell, idx) => (
          <Card
            key={cell.id}
            className="border-l-4"
            data-cell-id={cell.id}
            onDragOver={onCellDragOver}
            onDrop={(e) => onCellDrop(cell.id, e)}
          >
            <CardContent className="space-y-2 py-2">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Badge variant="outline" className="font-mono">
                  [{idx + 1}] {cell.id}
                </Badge>
                <Badge variant={cell.kind === "python" ? "secondary" : "outline"}>
                  {cell.kind}
                </Badge>
                {cell.stale ? (
                  <Badge variant="warn" title="Upstream changed since last run.">
                    stale
                  </Badge>
                ) : null}
                {cell.lastResult?.status === "done" ? (
                  <Badge variant="positive">done</Badge>
                ) : null}
                {cell.lastResult?.status === "error" ? (
                  <Badge variant="negative">error</Badge>
                ) : null}
                <div className="flex-1" />
                <Button
                  variant="ghost"
                  size="sm"
                  className="gap-2"
                  onClick={() => onRunCell(cell)}
                  title="Run this cell"
                >
                  <Play className="h-4 w-4" /> Run
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="gap-2"
                  onClick={() => onPromoteToNode(cell)}
                  disabled={promoting === cell.id}
                  title="Convert this cell into a snippet.python GraphSpec node"
                >
                  <RotateCw className="h-4 w-4" /> {promoting === cell.id ? "Promoting…" : "Promote"}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="gap-2"
                  onClick={() => onDeleteCell(cell.id)}
                  title="Delete this cell"
                >
                  <Trash2 className="h-4 w-4" /> Delete
                </Button>
              </div>
              <div className="h-40">
                <CodeEditor
                  value={cell.source}
                  onChange={(v) => onSourceChange(cell.id, v)}
                  language={cell.kind}
                  height="100%"
                />
              </div>
              {cell.lastResult ? (
                <div className="space-y-1 text-xs">
                  {cell.lastResult.stale_ids.length ? (
                    <div className="text-amber-500">
                      stale descendants: {cell.lastResult.stale_ids.join(", ")}
                    </div>
                  ) : null}
                  {cell.lastResult.render?.kind === "repr" && cell.lastResult.render.value ? (
                    <pre className="overflow-x-auto rounded bg-muted/40 p-2 font-mono text-[11px]">
                      {String(cell.lastResult.render.value)}
                    </pre>
                  ) : null}
                </div>
              ) : null}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export default EdaCellStack;
