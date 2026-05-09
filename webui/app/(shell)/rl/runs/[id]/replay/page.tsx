import { RlReplayViewer } from "@/components/rl/RlReplayViewer";

interface Props {
  params: { id: string };
}

export default function Page({ params }: Props) {
  return <RlReplayViewer runId={params.id} />;
}
