import { CatalogTableDetail } from "@/components/data/CatalogTableDetail";

export const metadata = { title: "Catalog · Table | AQP" };

interface CatalogDetailPageProps {
  params: Promise<{ namespace: string; name: string }>;
}

export default async function CatalogDetailPage({ params }: CatalogDetailPageProps) {
  const { namespace, name } = await params;
  return (
    <CatalogTableDetail
      namespace={decodeURIComponent(namespace)}
      name={decodeURIComponent(name)}
    />
  );
}
