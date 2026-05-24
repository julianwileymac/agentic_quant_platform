import { useCallback, useEffect, useMemo, useState } from "react";

import { toast } from "@/components/ui/toast";
import { useLabStore } from "@/features/data-lab/state/labStore";
import {
  type LabCatalogResponse,
  type LabGraphSpec,
  type LabNodeSpec,
  type LabNodeType,
  fetchLabCatalog,
  patchLabGraph,
} from "@/lib/api/lab";

import { NodeParamsInspector } from "./NodeParamsInspector";

/**
 * Right-rail content for ``mode === 'testing'``.
 *
 * Reads ``labStore.liveSpec`` (the most-recent Testing canvas edit
 * mirrored from ``WorkflowEditor.onGraphChange``) and renders the
 * RJSF-typed inspector for the currently-selected node. Persists
 * edits through ``PATCH /lab/graphs/{id}``.
 *
 * The catalog (node-types + JSON schemas) is fetched once and
 * cached for the lifetime of the rail — palette + inspector share
 * the same response so a NodeType lookup is a constant-time map.
 */
export function TestingInspectorRail() {
  const draftGraph = useLabStore((s) => s.draftGraph);
  const setDraftGraph = useLabStore((s) => s.setDraftGraph);
  const liveSpec = useLabStore((s) => s.liveSpec);
  const selectedNodeId = useLabStore((s) => s.selectedNodeId);
  const setLiveSpec = useLabStore((s) => s.setLiveSpec);
  const nodeStatus = useLabStore((s) => s.nodeStatus);

  const [catalog, setCatalog] = useState<LabCatalogResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchLabCatalog().then((c) => {
      if (!cancelled) setCatalog(c);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const persistedSpec: LabGraphSpec | null = useMemo(() => {
    if (!draftGraph || draftGraph.mode !== "testing") return null;
    return draftGraph.spec as unknown as LabGraphSpec;
  }, [draftGraph]);

  const activeSpec: LabGraphSpec | null = liveSpec ?? persistedSpec;

  const selectedNode: LabNodeSpec | null = useMemo(() => {
    if (!activeSpec || !selectedNodeId) return null;
    return (activeSpec.nodes ?? []).find((n) => n.id === selectedNodeId) ?? null;
  }, [activeSpec, selectedNodeId]);

  const nodeTypeByAlias = useMemo<Record<string, LabNodeType>>(() => {
    const out: Record<string, LabNodeType> = {};
    if (catalog) {
      for (const cat of catalog.categories) {
        for (const nt of cat.items) {
          out[nt.alias] = nt;
        }
      }
    }
    return out;
  }, [catalog]);

  const handleSubmit = useCallback(
    async (next: LabNodeSpec) => {
      if (!activeSpec) return;
      const nextSpec: LabGraphSpec = {
        ...activeSpec,
        nodes: (activeSpec.nodes ?? []).map((n) =>
          n.id === next.id ? next : n,
        ),
      };
      setLiveSpec(nextSpec);
      if (draftGraph?.id) {
        try {
          const patched = await patchLabGraph(draftGraph.id, { spec: nextSpec });
          setDraftGraph(patched);
        } catch (err) {
          toast.error(`Patch failed: ${(err as Error).message}`);
        }
      }
    },
    [activeSpec, draftGraph?.id, setDraftGraph, setLiveSpec],
  );

  if (!selectedNode) {
    return (
      <div className="p-3 text-xs text-muted-foreground">
        Click a node on the canvas to edit its params.
      </div>
    );
  }

  return (
    <NodeParamsInspector
      node={selectedNode}
      nodeType={
        selectedNode.type ? (nodeTypeByAlias[selectedNode.type] ?? null) : null
      }
      status={nodeStatus[selectedNode.id ?? ""]?.status}
      onSubmit={handleSubmit}
    />
  );
}

export default TestingInspectorRail;
