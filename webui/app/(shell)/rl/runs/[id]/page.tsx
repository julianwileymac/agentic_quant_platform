import { RlRunDetailPage } from "@/components/rl/RlRunDetailPage";

interface Props {
  params: { id: string };
}

export default function Page({ params }: Props) {
  return <RlRunDetailPage runId={params.id} />;
}
