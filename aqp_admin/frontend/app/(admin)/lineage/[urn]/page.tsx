"use client";

import { useQuery } from "@tanstack/react-query";
import { use } from "react";

import { adminGet } from "@/lib/api/client";

export default function LineageDatasetPage({
  params,
}: {
  params: Promise<{ urn: string }>;
}) {
  const { urn } = use(params);
  const decoded = decodeURIComponent(urn);
  const { data: ancestry } = useQuery({
    queryKey: ["admin", "lineage", decoded, "ancestry"],
    queryFn: () =>
      adminGet<Record<string, unknown>>(
        `/lineage/datasets/${encodeURIComponent(decoded)}/ancestry?depth=3`,
      ),
  });
  const { data: impact } = useQuery({
    queryKey: ["admin", "lineage", decoded, "impact"],
    queryFn: () =>
      adminGet<Record<string, unknown>>(
        `/lineage/datasets/${encodeURIComponent(decoded)}/impact?depth=3`,
      ),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold break-all">{decoded}</h1>
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <h2 className="mb-2 text-sm font-semibold">Ancestry (upstream, depth=3)</h2>
          <pre className="rounded-md border bg-white p-4 text-xs">
            {JSON.stringify(ancestry ?? {}, null, 2)}
          </pre>
        </div>
        <div>
          <h2 className="mb-2 text-sm font-semibold">Impact (downstream, depth=3)</h2>
          <pre className="rounded-md border bg-white p-4 text-xs">
            {JSON.stringify(impact ?? {}, null, 2)}
          </pre>
        </div>
      </section>
    </div>
  );
}
