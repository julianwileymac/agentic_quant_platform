import type { Metadata } from "next";

import { IcebergEditor } from "@/components/data/IcebergEditor";

export const metadata: Metadata = {
  title: "Iceberg Editor · AQP",
  description: "Edit metadata, group, and physically consolidate Iceberg tables.",
};

export default function IcebergEditorRoute() {
  return <IcebergEditor />;
}
