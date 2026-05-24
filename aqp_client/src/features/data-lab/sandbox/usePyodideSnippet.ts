import { useCallback, useEffect, useRef, useState } from "react";

import { useLabStore } from "@/features/data-lab/state/labStore";

/**
 * React hook wrapping the Pyodide Web Worker.
 *
 * Gated by ``labStore.pyodideEnabled`` (Phase 4 feature flag — the
 * worker is ~10MB gzipped and only useful for pure-Python EDA
 * snippets that don't need server-side data access). The hook
 * lazily spawns the worker on first ``run`` and reuses it across
 * subsequent calls so the cold-start cost is amortised.
 */
export interface PyodideRunResult {
  status: "done" | "error";
  stdout: string;
  stderr: string;
  repr: string | null;
  error: string | null;
  duration_ms: number;
}

export interface UsePyodideSnippet {
  ready: boolean;
  loading: boolean;
  error: string | null;
  run: (source: string, inputs?: Record<string, unknown>) => Promise<PyodideRunResult>;
}

export function usePyodideSnippet(enabled: boolean = true): UsePyodideSnippet {
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const workerRef = useRef<Worker | null>(null);
  const pendingRef = useRef<
    Map<string, (result: PyodideRunResult) => void>
  >(new Map());

  // Keep the worker singleton across hook re-mounts.
  useEffect(() => {
    if (!enabled) return;
    if (workerRef.current) return;
    setLoading(true);
    try {
      const worker = new Worker(
        new URL("./pyodideWorker.ts", import.meta.url),
        { type: "module" },
      );
      workerRef.current = worker;
      worker.onmessage = (event: MessageEvent<unknown>) => {
        const data = event.data as
          | { type: "preload_ready" }
          | { type: "preload_error"; error: string }
          | (PyodideRunResult & { type: "result"; id: string });
        if (data && (data as { type: string }).type === "preload_ready") {
          setReady(true);
          setLoading(false);
          return;
        }
        if (data && (data as { type: string }).type === "preload_error") {
          setError((data as { error: string }).error);
          setLoading(false);
          return;
        }
        if (data && (data as { type: string }).type === "result") {
          const resolver = pendingRef.current.get((data as { id: string }).id);
          if (resolver) {
            pendingRef.current.delete((data as { id: string }).id);
            resolver({
              status: (data as { status: "done" | "error" }).status,
              stdout: (data as { stdout: string }).stdout,
              stderr: (data as { stderr: string }).stderr,
              repr: (data as { repr: string | null }).repr,
              error: (data as { error: string | null }).error,
              duration_ms: (data as { duration_ms?: number }).duration_ms ?? 0,
            });
          }
        }
      };
      worker.postMessage({ type: "preload" });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setLoading(false);
    }
    return () => {
      workerRef.current?.terminate();
      workerRef.current = null;
      pendingRef.current.clear();
    };
  }, [enabled]);

  const run = useCallback(
    (source: string, inputs?: Record<string, unknown>) => {
      const worker = workerRef.current;
      if (!worker || !ready) {
        return Promise.resolve<PyodideRunResult>({
          status: "error",
          stdout: "",
          stderr: "",
          repr: null,
          error: ready
            ? "pyodide worker not initialised"
            : "pyodide preload still in flight",
          duration_ms: 0,
        });
      }
      return new Promise<PyodideRunResult>((resolve) => {
        const id = `pyo-${Math.random().toString(36).slice(2, 10)}`;
        pendingRef.current.set(id, resolve);
        const startedAt = performance.now();
        worker.postMessage({ type: "run", id, source, inputs });
        // Wrap the resolver so we can stamp the duration in this
        // process rather than rely on the worker reporting it.
        const original = pendingRef.current.get(id)!;
        pendingRef.current.set(id, (result) => {
          original({ ...result, duration_ms: performance.now() - startedAt });
        });
      });
    },
    [ready],
  );

  return { ready, loading, error, run };
}

/**
 * Convenience hook reading the AQP_LAB_PYODIDE_ENABLED frontend
 * flag from labStore. When the flag is false the hook returns a
 * disabled wrapper that surfaces an actionable error instead of
 * spawning the worker.
 */
export function useLabPyodide(): UsePyodideSnippet {
  // The flag lives on the labStore so the LabShell can toggle it at
  // runtime (e.g. for a single tenant) without requiring a rebuild.
  // Phase 4 ships the worker behind the same flag the backend uses.
  const enabled = useLabStore(
    (s) => (s as unknown as { pyodideEnabled?: boolean }).pyodideEnabled ?? false,
  );
  return usePyodideSnippet(enabled);
}
