import { AlphaVantageCategoryPage } from "@/components/alpha-vantage/AlphaVantageCategoryPage";

export const metadata = { title: "Alpha Vantage Indices | AQP" };

export default function Page() {
  return <AlphaVantageCategoryPage kind="indices" />;
}
