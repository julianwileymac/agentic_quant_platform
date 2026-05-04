import { Suspense } from "react";

import { MonitorPage } from "@/components/monitor/MonitorPage";

export const metadata = { title: "Monitor | AQP" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <MonitorPage />
    </Suspense>
  );
}
