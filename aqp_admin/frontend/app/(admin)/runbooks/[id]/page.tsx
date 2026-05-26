"use client";

import dynamic from "next/dynamic";
import { use } from "react";

const RunbookEditor = dynamic(
  () => import("@/components/runbooks/RunbookEditor").then((m) => m.RunbookEditor),
  { ssr: false, loading: () => <div className="text-sm text-muted-foreground">loading editor…</div> },
);

export default function RunbookDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <RunbookEditor runbookId={id} />;
}
