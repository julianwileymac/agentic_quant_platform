import { StrategyEditor } from "@/components/strategies/StrategyEditor";

export const metadata = { title: "New strategy | AQP" };

export default function NewStrategyPage() {
  return <StrategyEditor mode="create" />;
}
