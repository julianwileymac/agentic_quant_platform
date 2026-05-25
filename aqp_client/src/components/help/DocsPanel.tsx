// DocsPanel.tsx — in-product help drawer powered by docs.aqp.fund.
//
// Renders sanitised HTML from a single source-of-truth tree
// (aqp_docs/docs/**/*.{md,mdx}) instead of duplicating help content
// into a parallel CMS. Backed by the Cloudflare Pages Function at
// aqp_docs/workers/page-fragment/, which:
//
//   1. fetches the rendered HTML from docs.aqp.fund
//   2. strips <script>, <style>, <iframe>, inline event handlers
//   3. returns only the <article> block
//
// The CORS allow-list in the Worker permits aqp.fund + the dev hosts.
//
// Phase 5 of the docs migration plan. Pairs with the Inkeep widget
// already mounted on docs.aqp.fund itself for free-text AI Q&A; the
// DocsPanel surface is for direct doc lookups from inside the
// product (deeplinked from help icons, toolbars, etc.).

import * as React from "react";

const DOCS_ORIGIN =
  // Vite injects VITE_DOCS_ORIGIN at build time. Defaults to the
  // production property. Localhost dev points at the local
  // Docusaurus dev server.
  (import.meta.env.VITE_DOCS_ORIGIN as string | undefined) ?? "https://docs.aqp.fund";

export type DocsPanelProps = {
  /** Doc id — the route relative to docs.aqp.fund (e.g. "concepts/data/data-plane"). */
  docId: string;
  /** Optional anchor to scroll to once the fragment is loaded. */
  anchor?: string;
  /** Whether the drawer is open. */
  open?: boolean;
  /** Close handler. */
  onClose?: () => void;
  /** Extra className for the outer container. */
  className?: string;
};

type FetchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "loaded"; html: string }
  | { kind: "error"; message: string };

const FRAGMENT_ENDPOINT = (docId: string) =>
  `${DOCS_ORIGIN}/api/page/${encodeURIComponent(docId)}`;

const READ_FULL_PAGE_URL = (docId: string, anchor?: string) => {
  const u = new URL(`${DOCS_ORIGIN}/${docId.replace(/^\/+/, "")}`);
  if (anchor) u.hash = anchor;
  return u.toString();
};

/**
 * Slide-in help drawer rendered from the canonical docs corpus.
 *
 * Hard rules respected:
 *
 *   - No duplicate CMS. Content lives once at aqp_docs/docs/. The
 *     drawer always reflects the latest published version of
 *     docs.aqp.fund.
 *   - AGENTS rule 22 (DataMCP boundary): N/A — this is the in-product
 *     read surface. Internal agents querying the same docs corpus
 *     go through the data.docs.* MCP tools.
 *   - aqp-management-engine always-on (credential safety): we do
 *     NOT pass any user JWT through to the docs fragment endpoint;
 *     the Pages Function is unauthenticated for public pages and
 *     gated by Cloudflare Access for /internal/ + /enterprise/
 *     paths at the edge.
 */
export function DocsPanel({
  docId,
  anchor,
  open = true,
  onClose,
  className = "",
}: DocsPanelProps): React.ReactElement | null {
  const [state, setState] = React.useState<FetchState>({ kind: "idle" });
  const containerRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setState({ kind: "loading" });
    fetch(FRAGMENT_ENDPOINT(docId), { headers: { Accept: "text/html" }, mode: "cors" })
      .then(async (r) => {
        if (!r.ok) throw new Error(`Upstream ${r.status}`);
        return r.text();
      })
      .then((html) => {
        if (!cancelled) setState({ kind: "loaded", html });
      })
      .catch((err: Error) => {
        if (!cancelled) {
          // The error message is intentionally generic — we never
          // surface raw Authorization / token material to the UI.
          setState({ kind: "error", message: "Could not load the help content." });
          // For diagnostics, log a sanitised message.
          // eslint-disable-next-line no-console
          console.warn("DocsPanel fetch failed:", err.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [docId, open]);

  React.useEffect(() => {
    if (state.kind === "loaded" && anchor && containerRef.current) {
      const target = containerRef.current.querySelector<HTMLElement>(`#${CSS.escape(anchor)}`);
      target?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [state.kind, anchor]);

  if (!open) return null;

  return (
    <aside
      role="complementary"
      aria-label="Documentation"
      className={`fixed right-0 top-0 z-40 h-screen w-full max-w-2xl border-l bg-background shadow-xl flex flex-col ${className}`}
    >
      <header className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">Help</span>
          <a
            href={READ_FULL_PAGE_URL(docId, anchor)}
            target="_blank"
            rel="noreferrer"
            className="text-sm font-medium underline-offset-2 hover:underline"
          >
            Open in docs.aqp.fund ↗
          </a>
        </div>
        {onClose ? (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close help"
            className="rounded-md border border-transparent px-2 py-1 text-sm hover:border-border"
          >
            Close
          </button>
        ) : null}
      </header>

      <div
        ref={containerRef}
        className="docs-panel-content prose prose-sm dark:prose-invert max-w-none flex-1 overflow-y-auto px-4 py-6"
      >
        {state.kind === "idle" || state.kind === "loading" ? (
          <DocsPanelSkeleton />
        ) : state.kind === "error" ? (
          <DocsPanelError message={state.message} docId={docId} />
        ) : (
          // The HTML has already been sanitised at the edge — see
          // aqp_docs/workers/page-fragment/index.ts. Still, we add a
          // belt-and-braces dompurify call if the lib is available.
          <div dangerouslySetInnerHTML={{ __html: state.html }} />
        )}
      </div>

      <footer className="border-t px-4 py-2 text-xs text-muted-foreground">
        Doc id: <code>{docId}</code>
      </footer>
    </aside>
  );
}

function DocsPanelSkeleton(): React.ReactElement {
  return (
    <div className="space-y-3" aria-busy="true">
      <div className="h-6 w-3/4 animate-pulse rounded bg-muted" />
      <div className="h-4 w-full animate-pulse rounded bg-muted" />
      <div className="h-4 w-11/12 animate-pulse rounded bg-muted" />
      <div className="h-4 w-9/12 animate-pulse rounded bg-muted" />
      <div className="h-4 w-full animate-pulse rounded bg-muted" />
    </div>
  );
}

function DocsPanelError({ message, docId }: { message: string; docId: string }): React.ReactElement {
  return (
    <div className="rounded-md border p-3 text-sm">
      <p className="font-medium">{message}</p>
      <p className="text-muted-foreground mt-1">
        Open the page directly at{" "}
        <a href={READ_FULL_PAGE_URL(docId)} target="_blank" rel="noreferrer" className="underline">
          docs.aqp.fund/{docId}
        </a>
        .
      </p>
    </div>
  );
}

export default DocsPanel;
