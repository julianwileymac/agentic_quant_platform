"use client";

import { useQuery } from "@tanstack/react-query";
import { use } from "react";

import { adminGet } from "@/lib/api/client";

export default function BuildDetailPage({
  params,
}: {
  params: Promise<{ jobName: string }>;
}) {
  const { jobName } = use(params);
  const { data } = useQuery({
    queryKey: ["admin", "builds", jobName],
    queryFn: () => adminGet<Record<string, unknown>>(`/builds/${jobName}`),
    refetchInterval: 5_000,
  });
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Build {jobName}</h1>
      <pre className="rounded-md border bg-white p-4 text-xs">
        {JSON.stringify(data ?? {}, null, 2)}
      </pre>
    </div>
  );
}
