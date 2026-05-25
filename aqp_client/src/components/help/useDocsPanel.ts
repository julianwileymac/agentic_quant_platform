// useDocsPanel — small state hook so any route can open the drawer.
//
// Usage:
//
//   const { open, docId, openHelp, closeHelp } = useDocsPanel();
//   <Toolbar>
//     <button onClick={() => openHelp("concepts/strategy/backtest-engines")}>Help</button>
//   </Toolbar>
//   <DocsPanel docId={docId} open={open} onClose={closeHelp} />
//
// The drawer mounts at the app root so any route can drive it via
// the URL search params (?help=concepts/...&helpAnchor=section-id).

import * as React from "react";

type State = {
  open: boolean;
  docId: string | null;
  anchor: string | undefined;
};

const SEARCH_PARAM = "help";
const ANCHOR_PARAM = "helpAnchor";

export function useDocsPanel(): {
  open: boolean;
  docId: string | null;
  anchor: string | undefined;
  openHelp: (docId: string, anchor?: string) => void;
  closeHelp: () => void;
} {
  const [state, setState] = React.useState<State>(() => initialFromUrl());

  // Keep state in sync with the URL — power users deeplink to specific docs.
  React.useEffect(() => {
    const onPop = () => setState(initialFromUrl());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const openHelp = React.useCallback((docId: string, anchor?: string) => {
    setState({ open: true, docId, anchor });
    const url = new URL(window.location.href);
    url.searchParams.set(SEARCH_PARAM, docId);
    if (anchor) url.searchParams.set(ANCHOR_PARAM, anchor);
    else url.searchParams.delete(ANCHOR_PARAM);
    window.history.replaceState(null, "", url.toString());
  }, []);

  const closeHelp = React.useCallback(() => {
    setState({ open: false, docId: null, anchor: undefined });
    const url = new URL(window.location.href);
    url.searchParams.delete(SEARCH_PARAM);
    url.searchParams.delete(ANCHOR_PARAM);
    window.history.replaceState(null, "", url.toString());
  }, []);

  return {
    open: state.open && state.docId !== null,
    docId: state.docId,
    anchor: state.anchor,
    openHelp,
    closeHelp,
  };
}

function initialFromUrl(): State {
  if (typeof window === "undefined") return { open: false, docId: null, anchor: undefined };
  const params = new URLSearchParams(window.location.search);
  const docId = params.get(SEARCH_PARAM);
  if (!docId) return { open: false, docId: null, anchor: undefined };
  const anchor = params.get(ANCHOR_PARAM) ?? undefined;
  return { open: true, docId, anchor };
}
