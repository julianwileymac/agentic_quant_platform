import { StrategyEditor } from "@/components/strategies/StrategyEditor";

export const metadata = { title: "Strategy | AQP" };

export default async function StrategyDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <StrategyEditor mode="edit" strategyId={id} />;
}
