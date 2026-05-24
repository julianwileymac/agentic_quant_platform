/**
 * Pyodide Tier-1 sandbox — runs pure-Python EDA snippets in the
 * browser via a Web Worker. Phase 4 ships this behind the
 * ``settings.aqp_lab_pyodide_enabled`` feature flag; when disabled
 * EDA cells continue to dispatch via the server-side
 * :class:`AnalysisRuntime` kernel.
 *
 * The worker accepts message envelopes of shape:
 *
 *   { type: 'run', id: string, source: string, inputs?: object }
 *
 * and replies with:
 *
 *   { type: 'result', id, status: 'done'|'error', stdout, stderr, repr, error }
 *
 * Mirrors :class:`aqp.lab.eda.kernel.EdaKernel.execute_cell` so the
 * frontend can swap the WS round-trip for an in-browser execution
 * when the snippet is pure-Python (numpy, pandas, scikit-learn, ...).
 *
 * NOTE: this file is loaded as a Web Worker via Vite's
 * ``new Worker(new URL('./pyodideWorker.ts', import.meta.url),
 * { type: 'module' })`` pattern. The pyodide package is ~10MB
 * gzipped — keep this worker out of the main bundle.
 */

declare const self: DedicatedWorkerGlobalScope;

let pyodideReady: Promise<any> | null = null;

async function getPyodide(): Promise<any> {
  if (!pyodideReady) {
    pyodideReady = (async () => {
      const { loadPyodide } = await import("pyodide");
      const pyodide = await loadPyodide({
        indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.2/full/",
      });
      // Preload the most-common analytical deps. Keep this list
      // small — every entry adds to the cold-start time.
      await pyodide.loadPackage(["numpy", "pandas"]);
      return pyodide;
    })();
  }
  return pyodideReady;
}

interface RunMessage {
  type: "run";
  id: string;
  source: string;
  inputs?: Record<string, unknown>;
}

interface PreloadMessage {
  type: "preload";
}

type IncomingMessage = RunMessage | PreloadMessage;

self.addEventListener("message", async (event: MessageEvent<IncomingMessage>) => {
  const message = event.data;
  if (message.type === "preload") {
    try {
      await getPyodide();
      self.postMessage({ type: "preload_ready" });
    } catch (err) {
      self.postMessage({
        type: "preload_error",
        error: err instanceof Error ? err.message : String(err),
      });
    }
    return;
  }
  if (message.type !== "run") return;

  try {
    const pyodide = await getPyodide();
    if (message.inputs) {
      for (const [key, value] of Object.entries(message.inputs)) {
        pyodide.globals.set(key, value);
      }
    }
    // Capture stdout/stderr — Pyodide ships a hook for this; we
    // pipe both to ring buffers so the worker reply contains them.
    const stdout: string[] = [];
    const stderr: string[] = [];
    pyodide.setStdout({ batched: (line: string) => stdout.push(line) });
    pyodide.setStderr({ batched: (line: string) => stderr.push(line) });
    let repr: string | null = null;
    let status: "done" | "error" = "done";
    let error: string | null = null;
    try {
      const value = await pyodide.runPythonAsync(message.source);
      if (value !== undefined && value !== null) {
        try {
          repr = String(value);
        } catch {
          repr = "<unrepresentable>";
        }
      }
    } catch (err) {
      status = "error";
      error = err instanceof Error ? err.message : String(err);
    }
    self.postMessage({
      type: "result",
      id: message.id,
      status,
      stdout: stdout.join("\n"),
      stderr: stderr.join("\n"),
      repr,
      error,
    });
  } catch (err) {
    self.postMessage({
      type: "result",
      id: message.id,
      status: "error",
      stdout: "",
      stderr: "",
      repr: null,
      error: err instanceof Error ? err.message : String(err),
    });
  }
});

export {};
