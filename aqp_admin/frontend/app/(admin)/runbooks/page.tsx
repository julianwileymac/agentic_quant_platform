"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";

import { adminGet } from "@/lib/api/client";

type Runbook = { id: string; title: string; updated_at?: string };

export default function RunbooksPage() {
  const { data } = useQuery({
    queryKey: ["admin", "runbooks"],
    queryFn: () => adminGet<{ runbooks: Runbook[] }>("/runbooks"),
  });
  const items = data?.runbooks ?? [];
  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Runbooks</h1>
        <Link
          href="/runbooks/new"
          className="rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-accent/50"
        >
          New runbook
        </Link>
      </header>
      <ul className="divide-y rounded-md border bg-white">
        {items.map((runbook) => (
          <li key={runbook.id} className="px-4 py-2">
            <Link href={`/runbooks/${runbook.id}`} className="text-sm font-medium">
              {runbook.title}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
