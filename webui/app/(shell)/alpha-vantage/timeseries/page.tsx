import { AlphaVantageCategoryPage } from "@/components/alpha-vantage/AlphaVantageCategoryPage";

export const metadata = { title: "Alpha Vantage Time Series | AQP" };

export default function Page() {
  return <AlphaVantageCategoryPage kind="timeseries" />;
}
