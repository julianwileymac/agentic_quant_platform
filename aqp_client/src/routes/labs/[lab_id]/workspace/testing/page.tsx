import { useCallback, useEffect, useMemo, useState } from "react";

import { toast } from "@/components/ui/toast";
import {
  type FlowGraph,
  type PaletteSection,
} from "@/components/flow/types";
import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import {
  type LabCatalogResponse,
  type LabRunOut,
  createLabGraph,
  fetchLabCatalog,
  submitLabRun,
} from "@/lib/api/lab";
import { useLabStore } from "@/features/data-lab/state/labStore";
import { useLabChannel } from "@/features/data-lab/ws/useLabChannel";

function paletteFromCatalog(cat: LabCatalogResponse | null): PaletteSection[] {
  if (!cat) return [];
  return cat.categories.map((c) => ({
    title: c.name,
    items: c.items.map((nt) => {
      const base = {
        kind: nt.alias,
        label: nt.label,
        description: nt.description,
        group: c.name,
        defaultParams: {} as Record<string, unknown>,
      };
      return nt.accent ? { ...base, accent: nt.accent } : base;
    }),
  }));
}

function flowGraphToLabSpec(
  flow: FlowGraph,
  catalog: LabCatalogResponse | null,
): {
  mode: "testing";
  nodes: Array<{
    id: string;
    type: string;
    label: string;
    category:
      | "DataSource"
      | "Transformation"
      | "Feature"
      | "Alpha"
      | "Model"
      | "Strategy"
      | "Math"
      | "Labeler"
      | "Output"
      | "Agent";
    position: [number, number];
    params: Record<string, unknown>;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
  }>;
} {
  const byAlias = new Map<
    string,
    {
      category: string;
      label: string;
    }
  >();
  if (catalog) {
    for (const cat of catalog.categories) {
      for (const item of cat.items) {
        byAlias.set(item.alias, { category: cat.name, label: item.label });
      }
    }
  }
  return {
    mode: "testing",
    nodes: flow.nodes.map((n) => {
      const meta = byAlias.get(n.data.kind);
      return {
        id: n.id,
        type: n.data.kind,
        label: n.data.label ?? meta?.label ?? n.data.kind,
        category: (meta?.category ?? "DataSource") as
          | "DataSource"
          | "Transformation"
          | "Feature"
          | "Alpha"
          | "Model"
          | "Strategy"
          | "Math"
          | "Labeler"
          | "Output"
          | "Agent",
        position: [n.position.x, n.position.y],
        params: (n.data.params as Record<string, unknown>) ?? {},
      };
    }),
    edges: flow.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
    })),
  };
}

/**
 * Testing mode (Phase 0 wiring).
 *
 * Reuses the existing :class:`WorkflowEditor` (which is already the
 * domain-agnostic React Flow shell used by Bot Builder / Strategy
 * Composer / RL Lab / ML Builder) and parameterises it with the Data
 * Lab's 35-node taxonomy fetched from `GET /lab/catalog/node-types`.
 *
 * Save dispatches `POST /lab/graphs`; Run dispatches
 * `POST /lab/graphs/{id}/runs?inline=true`. Phase 2 swaps the inline
 * flag to false to dispatch through the Celery `run_lab_graph`
 * task; the route + WS contract stay identical.
 */
export function LabTestingRoute() {
  const draftGraph = useLabStore((s) => s.draftGraph);
  const setDraftGraph = useLabStore((s) => s.setDraftGraph);
  const setCurrentRun = useLabStore((s) => s.setCurrentRun);
  const labId = useLabStore((s) => s.labId);
  const sessionId = useLabStore((s) => s.sessionId);
  const setSelectedNode = useLabStore((s) => s.setSelectedNode);

  const [catalog, setCatalog] = useState<LabCatalogResponse | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void fetchLabCatalog().then((c) => {
      if (!cancelled) setCatalog(c);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const palette = useMemo(() => paletteFromCatalog(catalog), [catalog]);
  const accentByKind = useMemo(() => {
    const out: Record<string, string> = {};
    if (catalog) {
      for (const cat of catalog.categories) {
        for (const item of cat.items) {
          if (item.accent) out[item.alias] = item.accent;
        }
      }
    }
    return out;
  }, [catalog]);

  // Pumps incoming envelopes into the Zustand store via LabShell's
  // mounted channel; this route owns its own "subscribe to run" hook
  // so the testing canvas can attach to runs it creates.
  const channel = useLabChannel({ sessionId });

  const initialGraph: FlowGraph | undefined = useMemo(() => {
    if (!draftGraph || draftGraph.mode !== "testing") return undefined;
    const spec = draftGraph.spec as Record<string, unknown>;
    const nodes = ((spec.nodes as Array<Record<string, unknown>>) ?? []).map(
      (n) => ({
        id: String(n.id),
        type: "aqp",
        position: {
          x: Array.isArray(n.position) ? Number(n.position[0]) : 0,
          y: Array.isArray(n.position) ? Number(n.position[1]) : 0,
        },
        data: {
          kind: String(n.type),
          label: String(n.label ?? n.type),
          params: (n.params as Record<string, unknown>) ?? {},
        },
      }),
    );
    const edges = ((spec.edges as Array<Record<string, unknown>>) ?? []).map(
      (e) => ({
        id: String(e.id ?? `e-${Math.random().toString(36).slice(2, 8)}`),
        source: String(e.source),
        target: String(e.target),
      }),
    );
    return {
      domain: "data" as const,
      version: 1 as const,
      nodes,
      edges,
    };
  }, [draftGraph]);

  const handleSave = useCallback(
    async (flow: FlowGraph) => {
      if (!labId) {
        toast.error("Select or create a lab before saving the graph.");
        return;
      }
      setSaving(true);
      try {
        const spec = flowGraphToLabSpec(flow, catalog);
        const created = await createLabGraph({
          lab_id: labId,
          name: draftGraph?.name ?? `lab-graph-${Date.now()}`,
          spec,
        });
        setDraftGraph(created);
        toast.success(`Saved graph ${created.content_hash.slice(0, 8)}…`);
      } catch (err) {
        toast.error(`Save failed: ${(err as Error).message}`);
      } finally {
        setSaving(false);
      }
    },
    [labId, catalog, draftGraph?.name, setDraftGraph],
  );

  const handleRun = useCallback(
    async (flow: FlowGraph) => {
      if (!labId) {
        toast.error("Select or create a lab before running the graph.");
        return;
      }
      try {
        const spec = flowGraphToLabSpec(flow, catalog);
        const created = await createLabGraph({
          lab_id: labId,
          name: draftGraph?.name ?? `lab-graph-${Date.now()}`,
          spec,
        });
        setDraftGraph(created);
        const run: LabRunOut = await submitLabRun(created.id, {
          inline: true,
          session_id: sessionId,
        });
        setCurrentRun(run);
        if (run.task_id) {
          channel.subscribe(run.task_id);
        }
        toast.success(`Run submitted (${run.status}).`);
      } catch (err) {
        toast.error(`Run failed: ${(err as Error).message}`);
      }
    },
    [labId, catalog, draftGraph?.name, sessionId, setDraftGraph, setCurrentRun, channel],
  );

  const handleNodeSelected = useCallback(
    (node: Parameters<NonNullable<Parameters<typeof WorkflowEditor>[0]["onNodeSelected"]>>[0]) => {
      setSelectedNode(node ? node.id : null);
    },
    [setSelectedNode],
  );

  // Mirror canvas state into the lab store so the LabShell's
  // right-rail TestingInspectorRail component can render the typed
  // NodeParamsInspector against the most-recent spec.
  const handleGraphChange = useCallback(
    (flow: FlowGraph) => {
      const spec = flowGraphToLabSpec(flow, catalog);
      useLabStore.getState().setLiveSpec(spec as never);
    },
    [catalog],
  );

  if (!catalog) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        Loading 35-node palette…
      </div>
    );
  }
  const initialAsGraph: { initialGraph?: FlowGraph } = initialGraph
    ? { initialGraph }
    : {};

  // The LabShell mounted by the parent route auto-renders the
  // typed NodeParamsInspector in the right rail when mode==='testing'
  // and labStore.selectedNodeId is set; we keep the labStore in
  // sync via ``onNodeSelected`` + ``onGraphChange``.
  return (
    <div className="flex h-full min-h-0 flex-col">
      <WorkflowEditor
        domain="data"
        paletteSections={palette}
        accentByKind={accentByKind}
        {...initialAsGraph}
        onSave={handleSave}
        onRun={handleRun}
        onNodeSelected={handleNodeSelected}
        onGraphChange={handleGraphChange}
        saving={saving}
      />
    </div>
  );
}

export default LabTestingRoute;
