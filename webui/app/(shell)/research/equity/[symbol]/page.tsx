import { EquityReportPage } from "@/components/research/EquityReportPage";

interface RouteParams {
  params: Promise<{ symbol: string }>;
}

export default async function EquityResearchSymbolPage({ params }: RouteParams) {
  const { symbol } = await params;
  return <EquityReportPage vtSymbol={decodeURIComponent(symbol)} />;
}

export const metadata = { title: "Equity Research | AQP" };
