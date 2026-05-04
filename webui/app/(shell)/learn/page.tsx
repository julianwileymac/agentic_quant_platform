import { Suspense } from "react";

import { TaxonomyExplorer } from "@/components/learning/TaxonomyExplorer";

export const metadata = { title: "Learn / Taxonomy | AQP" };

export default function LearnPage() {
  return (
    <Suspense fallback={null}>
      <TaxonomyExplorer />
    </Suspense>
  );
}
