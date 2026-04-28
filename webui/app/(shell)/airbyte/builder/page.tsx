import { AirbyteWorkspace } from "@/components/airbyte/AirbyteWorkspace";

export const metadata = { title: "Airbyte Builder | AQP" };

export default function AirbyteBuilderPage() {
  return <AirbyteWorkspace view="builder" />;
}
