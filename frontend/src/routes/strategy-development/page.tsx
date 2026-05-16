import { Navigate } from "react-router-dom";

/**
 * `/strategy-development` index — redirects to the composer by default
 * so users land on a usable surface. The full umbrella (with its split
 * pane + KPI strip) is mounted via the `StrategyDevLayout` route in
 * `frontend/src/routes.tsx`.
 */
export function StrategyDevIndexRoute() {
  return <Navigate to="/strategy-development/composer" replace />;
}
