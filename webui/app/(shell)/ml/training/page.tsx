import { Suspense } from "react";

import { MlTrainingPage } from "@/components/ml/MlTrainingPage";

export const metadata = { title: "ML Training | AQP" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <MlTrainingPage />
    </Suspense>
  );
}
