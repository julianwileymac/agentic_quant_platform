import { SimulationPanel } from "@/features/data-lab/modes/simulation/SimulationPanel";

/**
 * Simulation mode — env config + transport bar + live tick stream.
 *
 * The backend compiler in :mod:`aqp.lab.compiler.simulation` selects
 * one of the four sub-mode runners (hftbt / stochastic / rl /
 * optctl) and the LiveBridge in :mod:`aqp.lab.ws.fanout` forwards
 * Redpanda topics into the same WS channel as ``stream.market`` /
 * ``stream.exec`` / ``stream.position`` / ``stream.pnl`` envelopes.
 */
export function LabSimulationRoute() {
  return <SimulationPanel />;
}

export default LabSimulationRoute;
