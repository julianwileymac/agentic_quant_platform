import { AirbyteWorkspace } from "@/components/airbyte/AirbyteWorkspace";

export const metadata = { title: "Airbyte | AQP" };

export default function AirbytePage() {
  return <AirbyteWorkspace view="overview" />;
}
