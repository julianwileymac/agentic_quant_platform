"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";

import { adminGet } from "@/lib/api/client";

type DatasetVertex = {
  urn: string;
  namespace: string;
  table: string;
  medallion_layer: string;
};

export default function LineagePage() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "lineage", "datasets"],
    queryFn: () =>
      adminGet<{ datasets: DatasetVertex[] }>(
        "/lineage/datasets?limit=100",
      ),
  });
  const datasets = data?.datasets ?? [];
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Lineage explorer</h1>
        <p className="text-sm text-muted-foreground">
          Bipartite graph (dataset ↔ transform ↔ edge) over the rule-48
          lineage tables. Walk ancestry / impact subgraphs for any
          Iceberg-resident dataset.
        </p>
      </header>
      <div className="overflow-hidden rounded-md border bg-white">
        <table className="min-w-full divide-y text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Namespace</th>
              <th className="px-4 py-2">Table</th>
              <th className="px-4 py-2">Layer</th>
              <th className="px-4 py-2">URN</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {isLoading ? (
              <tr>
                <td colSpan={4} className="px-4 py-3 text-muted-foreground">
                  loading…
                </td>
              </tr>
            ) : (
              datasets.map((dataset) => (
                <tr key={dataset.urn}>
                  <td className="px-4 py-2 font-mono text-xs">{dataset.namespace}</td>
                  <td className="px-4 py-2">{dataset.table}</td>
                  <td className="px-4 py-2">{dataset.medallion_layer}</td>
                  <td className="px-4 py-2 font-mono text-xs">
                    <Link href={`/lineage/${encodeURIComponent(dataset.urn)}`}>
                      {dataset.urn}
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
