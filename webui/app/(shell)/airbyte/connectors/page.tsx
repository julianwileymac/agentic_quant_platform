import { AirbyteWorkspace } from "@/components/airbyte/AirbyteWorkspace";

export const metadata = { title: "Airbyte Connectors | AQP" };

export default function AirbyteConnectorsPage() {
  return <AirbyteWorkspace view="connectors" />;
}
