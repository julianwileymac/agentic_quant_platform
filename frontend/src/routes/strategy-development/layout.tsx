import { StrategyDevLayout } from "@/components/strategy-dev/StrategyDevLayout";

/**
 * Route component wrapping the consolidated `/strategy-development/*`
 * umbrella. The actual UI is in `StrategyDevLayout` so the layout can
 * be exported as a standalone component for unit tests / storybook.
 */
export function StrategyDevLayoutRoute() {
  return <StrategyDevLayout />;
}
