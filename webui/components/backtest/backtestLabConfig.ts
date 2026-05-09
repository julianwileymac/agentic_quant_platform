export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function normaliseBacktestConfigShape(
  parsed: unknown,
  selectedEngine: string,
): Record<string, unknown> | null {
  if (!isRecord(parsed)) return null;

  const strategy = parsed.strategy;
  const backtest = parsed.backtest;
  if (!isRecord(strategy) || !isRecord(backtest)) return null;

  return {
    ...parsed,
    strategy,
    backtest: {
      ...backtest,
      engine: selectedEngine,
    },
  };
}
