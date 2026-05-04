import { Suspense } from "react";

import { BacktestNewShell } from "@/components/backtest/BacktestNewShell";

export const metadata = { title: "New backtest | AQP" };

export default function NewBacktestPage() {
  return (
    <Suspense fallback={null}>
      <BacktestNewShell />
    </Suspense>
  );
}
