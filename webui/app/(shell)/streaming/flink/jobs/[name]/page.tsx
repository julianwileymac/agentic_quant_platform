import { FlinkJobDetail } from "@/components/streaming/FlinkJobDetail";

interface PageProps {
  params: Promise<{ name: string }>;
}

export default async function Page({ params }: PageProps) {
  const { name } = await params;
  return <FlinkJobDetail name={decodeURIComponent(name)} />;
}
