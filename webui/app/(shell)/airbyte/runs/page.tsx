import { AirbyteWorkspace } from "@/components/airbyte/AirbyteWorkspace";

export const metadata = { title: "Airbyte Runs | AQP" };

export default function AirbyteRunsPage() {
  return <AirbyteWorkspace view="runs" />;
}
