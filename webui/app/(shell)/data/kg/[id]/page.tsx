import { EntityDetailRouter } from "@/components/data/kg/EntityDetailRouter";

interface RouteParams {
  params: Promise<{ id: string }>;
}

export default async function EntityDetailPage({ params }: RouteParams) {
  const { id } = await params;
  return <EntityDetailRouter entityId={decodeURIComponent(id)} />;
}

export const metadata = { title: "Entity Detail | AQP" };
