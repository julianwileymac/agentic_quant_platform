export const OPTIMIZER_LIST_PATH = "/backtest/optimize";

export function optimizerDetailPath(runId: string): string {
  return `/backtest/optimize/${encodeURIComponent(runId)}`;
}
