import { AlphaVantageCategoryPage } from "@/components/alpha-vantage/AlphaVantageCategoryPage";

export const metadata = { title: "Alpha Vantage Commodities | AQP" };

export default function Page() {
  return <AlphaVantageCategoryPage kind="commodities" />;
}
