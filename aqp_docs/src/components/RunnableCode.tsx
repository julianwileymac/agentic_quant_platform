// RunnableCode.tsx — inline "Run" buttons for Python (Pyodide) +
// TypeScript / JavaScript / Node (StackBlitz WebContainers).
//
// MDX usage:
//
//   ```python runnable
//   import requests
//   print(requests.get("http://localhost:8000/readyz").status_code)
//   ```
//
//   ```ts runnable=stackblitz
//   const r = await fetch("https://api.aqp.fund/health");
//   console.log(await r.json());
//   ```
//
// Phase 5 of the migration plan. Pyodide runs entirely in-browser
// (no server round trips); StackBlitz WebContainers spawn a full
// Node sandbox on demand.
//
// Hard rules respected:
//   - aqp-management-engine always-on (credential safety): Pyodide
//     and WebContainers are sandboxed — secrets in code blocks
//     stay in-sandbox; we do NOT proxy network calls through any
//     credentialed proxy.
//   - "Runnable" is opt-in via the MDX `runnable` attribute; the
//     docs-CI Vale rules reject TODO-marked snippets.

import React from "react";

type Runner = "pyodide" | "stackblitz";

type RunnableCodeProps = {
  code: string;
  language?: string;
  runner?: Runner;
  /** Optional StackBlitz project template id. */
  stackblitzTemplate?: string;
  /** Optional Pyodide packages to pip-install before running. */
  pyodidePackages?: string[];
};

declare global {
  interface Window {
    loadPyodide?: (opts?: { indexURL?: string }) => Promise<{
      runPythonAsync: (code: string) => Promise<unknown>;
      loadPackage: (pkgs: string[]) => Promise<void>;
      globals: { get: (name: string) => unknown };
      setStdout: (opts: { batched: (s: string) => void }) => void;
      setStderr: (opts: { batched: (s: string) => void }) => void;
    }>;
  }
}

const PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js";
const STACKBLITZ_SDK = "https://unpkg.com/@stackblitz/sdk/bundles/sdk.umd.js";

async function loadScript(url: string): Promise<void> {
  if (document.querySelector(`script[src="${url}"]`)) return;
  await new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = url;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error(`Failed to load ${url}`));
    document.head.appendChild(s);
  });
}

export function RunnableCode({
  code,
  language = "python",
  runner,
  stackblitzTemplate = "typescript",
  pyodidePackages = [],
}: RunnableCodeProps): React.ReactElement {
  const [output, setOutput] = React.useState<string>("");
  const [busy, setBusy] = React.useState(false);
  const effectiveRunner: Runner =
    runner ?? (["py", "python"].includes(language.toLowerCase()) ? "pyodide" : "stackblitz");

  async function runPyodide(): Promise<void> {
    setBusy(true);
    setOutput("");
    try {
      await loadScript(PYODIDE_CDN);
      const pyodide = await window.loadPyodide?.({
        indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/",
      });
      if (!pyodide) throw new Error("Pyodide failed to initialise");
      let buf = "";
      pyodide.setStdout({ batched: (s) => (buf += s) });
      pyodide.setStderr({ batched: (s) => (buf += s) });
      if (pyodidePackages.length > 0) {
        await pyodide.loadPackage(pyodidePackages);
      }
      await pyodide.runPythonAsync(code);
      setOutput(buf.trim() || "(no output)");
    } catch (err) {
      setOutput(`Error: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function runStackBlitz(): Promise<void> {
    setBusy(true);
    setOutput("");
    try {
      await loadScript(STACKBLITZ_SDK);
      const sdk = (window as unknown as { StackBlitzSDK?: { openProject: (proj: unknown, opts?: unknown) => void } }).StackBlitzSDK;
      if (!sdk?.openProject) throw new Error("StackBlitz SDK failed to load");
      sdk.openProject(
        {
          title: "AQP Docs Sandbox",
          description: "Runnable code block from docs.aqp.fund",
          template: stackblitzTemplate,
          files: { "index.ts": code, "package.json": `{ "type": "module", "scripts": { "start": "tsx index.ts" }, "dependencies": { "tsx": "^4.19.2" } }` },
        },
        { newWindow: true, openFile: "index.ts" },
      );
      setOutput("Opened in StackBlitz ↗");
    } catch (err) {
      setOutput(`Error: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="aqp-runnable-code">
      <button
        type="button"
        className="aqp-run-button"
        onClick={effectiveRunner === "pyodide" ? runPyodide : runStackBlitz}
        disabled={busy}
        aria-busy={busy}
      >
        {busy ? "Running…" : `Run (${effectiveRunner === "pyodide" ? "Pyodide" : "StackBlitz"})`}
      </button>
      {output ? (
        <pre className="mt-2 max-h-64 overflow-auto rounded border p-2 text-sm">{output}</pre>
      ) : null}
    </div>
  );
}

export default RunnableCode;
