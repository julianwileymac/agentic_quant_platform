import { EntityDetail } from "@/components/data/kg/EntityDetail";

interface RouteParams {
  params: Promise<{ id: string }>;
}

export default async function EntityDetailPage({ params }: RouteParams) {
  const { id } = await params;
  return <EntityDetail entityId={decodeURIComponent(id)} />;
}

export const metadata = { title: "Entity Detail | AQP" };
