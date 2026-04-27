import type { Metadata } from "next";

import { ConsolidatePage } from "@/components/data/ConsolidatePage";

export const metadata: Metadata = {
  title: "Consolidate Tables · AQP",
  description: "Merge Iceberg part-files into the original logical tables.",
};

export default function ConsolidateRoute() {
  return <ConsolidatePage />;
}
