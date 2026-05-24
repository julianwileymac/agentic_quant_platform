import { EvaluationPanel } from "@/features/data-lab/modes/evaluation/EvaluationPanel";

/**
 * Evaluation mode — sweep config + trial grid + CPCV guard.
 *
 * The backend ``aqp.lab.compiler.evaluation`` lowers the sweep into a
 * Celery group of N trials; the CPCV helper in
 * ``aqp.lab.evaluation.cpcv`` enforces the hard 100-path guard; the
 * DSR helper in ``aqp.lab.evaluation.deflated_sharpe`` renders DSR
 * alongside raw Sharpe so the UI never displays raw Sharpe alone.
 */
export function LabEvaluationRoute() {
  return <EvaluationPanel />;
}

export default LabEvaluationRoute;
