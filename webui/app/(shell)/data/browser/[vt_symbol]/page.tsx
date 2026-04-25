import { DataSymbolBrowser } from "@/components/data/DataSymbolBrowser";

export const metadata = { title: "Symbol | AQP" };

export default async function DataSymbolPage({
  params,
}: {
  params: Promise<{ vt_symbol: string }>;
}) {
  const { vt_symbol } = await params;
  return <DataSymbolBrowser vtSymbol={decodeURIComponent(vt_symbol)} />;
}
