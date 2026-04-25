import { BacktestDetail } from "@/components/backtest/BacktestDetail";

export const metadata = { title: "Backtest run | AQP" };

export default async function BacktestDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <BacktestDetail backtestId={id} />;
}
