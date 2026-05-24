import { EdaCellStack } from "@/features/data-lab/modes/eda/EdaCellStack";

/**
 * EDA mode — Phase 1 reactive cell stack.
 *
 * The :class:`EdaKernel` lives server-side (one per session_id) and
 * the cell DAG (marimo-style) tracks references / definitions to
 * mark downstream cells stale on edit. The cell stack ships
 * CodeMirror Python + SQL cells, dependency chips, stale indicator,
 * and the "Promote to node" affordance.
 */
export function LabEdaRoute() {
  return <EdaCellStack />;
}

export default LabEdaRoute;
