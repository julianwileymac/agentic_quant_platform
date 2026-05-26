"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";

import { adminGet } from "@/lib/api/client";

type Build = { job_name: string; status: string };

export default function BuildsPage() {
  const { data } = useQuery({
    queryKey: ["admin", "builds"],
    queryFn: () => adminGet<{ builds: Build[] }>("/builds"),
    refetchInterval: 15_000,
  });
  const builds = data?.builds ?? [];
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Kaniko builds</h1>
      <ul className="divide-y rounded-md border bg-white">
        {builds.map((build) => (
          <li key={build.job_name} className="flex items-center justify-between px-4 py-2">
            <Link href={`/builds/${build.job_name}`} className="font-mono text-sm">
              {build.job_name}
            </Link>
            <span className="text-xs text-muted-foreground">{build.status}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
