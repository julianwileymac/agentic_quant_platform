import { ProducerDetail } from "@/components/streaming/ProducerDetail";

interface PageProps {
  params: Promise<{ name: string }>;
}

export default async function Page({ params }: PageProps) {
  const { name } = await params;
  return <ProducerDetail name={decodeURIComponent(name)} />;
}
