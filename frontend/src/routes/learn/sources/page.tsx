import { Navigate } from "react-router-dom";

/**
 * Legacy parity: `/learn/sources` is just `/learn?tab=sources` so deep
 * links in old emails / docs continue to resolve to the right tab.
 */
export function LearnSourcesRoute() {
  return <Navigate to="/learn?tab=sources" replace />;
}
