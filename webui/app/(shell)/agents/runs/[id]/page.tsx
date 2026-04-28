import { AgentRunDetailPage } from "@/components/agents/AgentRunDetailPage";

export const metadata = { title: "Agent Run | AQP" };

interface Props {
  params: Promise<{ id: string }>;
}

export default async function Page({ params }: Props) {
  const { id } = await params;
  return <AgentRunDetailPage runId={id} />;
}
