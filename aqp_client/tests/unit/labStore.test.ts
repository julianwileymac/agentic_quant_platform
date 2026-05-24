import { describe, expect, it, beforeEach } from "vitest";

import { useLabStore } from "@/features/data-lab/state/labStore";

describe("labStore", () => {
  beforeEach(() => {
    useLabStore.getState().resetSession();
  });

  it("starts with a fresh session id and default testing mode", () => {
    const state = useLabStore.getState();
    expect(state.mode).toBe("testing");
    expect(state.sessionId).toMatch(/^lab-/);
    expect(state.recentEnvelopes).toEqual([]);
    expect(state.nodeStatus).toEqual({});
  });

  it("projects run.status envelopes into per-node status map", () => {
    const ts = Date.now() / 1000;
    useLabStore.getState().pushEnvelope({
      v: 1,
      kind: "run.status",
      task_id: "t-1",
      timestamp: ts,
      stage: "node:done",
      message: "ok",
      run_id: "r-1",
      node_id: "n-7",
      state: "done",
    });
    const state = useLabStore.getState();
    expect(state.nodeStatus["n-7"]?.status).toBe("done");
    expect(state.recentEnvelopes).toHaveLength(1);
  });

  it("accumulates metric envelopes per node", () => {
    const baseTs = Date.now() / 1000;
    useLabStore.getState().pushEnvelope({
      v: 1,
      kind: "run.metric",
      task_id: "t-1",
      timestamp: baseTs,
      stage: "run.metric",
      message: "",
      run_id: "r-1",
      node_id: "n-1",
      name: "sharpe",
      value: 1.27,
    });
    useLabStore.getState().pushEnvelope({
      v: 1,
      kind: "run.metric",
      task_id: "t-1",
      timestamp: baseTs + 1,
      stage: "run.metric",
      message: "",
      run_id: "r-1",
      node_id: "n-1",
      name: "max_dd",
      value: -0.12,
    });
    const status = useLabStore.getState().nodeStatus["n-1"];
    expect(status?.metrics).toEqual({ sharpe: 1.27, max_dd: -0.12 });
  });

  it("caps the recent envelope ring at 200 entries", () => {
    const baseTs = Date.now() / 1000;
    for (let i = 0; i < 220; i++) {
      useLabStore.getState().pushEnvelope({
        v: 1,
        kind: "run.status",
        task_id: "t-1",
        timestamp: baseTs + i,
        stage: "running",
        message: `${i}`,
        run_id: "r-1",
        node_id: "n-x",
        state: "running",
      });
    }
    expect(useLabStore.getState().recentEnvelopes.length).toBeLessThanOrEqual(200);
  });

  it("changes mode but keeps session id stable", () => {
    const sessionId = useLabStore.getState().sessionId;
    useLabStore.getState().setMode("eda");
    expect(useLabStore.getState().mode).toBe("eda");
    expect(useLabStore.getState().sessionId).toBe(sessionId);
  });
});
