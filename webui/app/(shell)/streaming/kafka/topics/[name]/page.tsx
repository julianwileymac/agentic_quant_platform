import { KafkaTopicDetail } from "@/components/streaming/KafkaTopicDetail";

interface PageProps {
  params: Promise<{ name: string }>;
}

export default async function Page({ params }: PageProps) {
  const { name } = await params;
  return <KafkaTopicDetail topic={decodeURIComponent(name)} />;
}
