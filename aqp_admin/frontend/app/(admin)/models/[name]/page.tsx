"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { use, useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { adminGet, adminPost } from "@/lib/api/client";

type Version = { version: number; run_id?: string; aliases?: string[] };

export default function ModelDetailPage({
  params,
}: {
  params: Promise<{ name: string }>;
}) {
  const { name } = use(params);
  const decoded = decodeURIComponent(name);
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<{ alias: string; version: number } | null>(null);

  const { data: model } = useQuery({
    queryKey: ["admin", "models", decoded],
    queryFn: () => adminGet<Record<string, unknown>>(`/models/${decoded}`),
  });
  const { data: versions } = useQuery({
    queryKey: ["admin", "models", decoded, "versions"],
    queryFn: () =>
      adminGet<{ versions: Version[] }>(`/models/${decoded}/versions?limit=50`),
  });

  const setAlias = useMutation({
    mutationFn: async (input: { alias: string; version: number; reason: string }) => {
      // Note: PUT not POST per the FastAPI route
      const res = await fetch(`/admin/models/${decoded}/aliases/${input.alias}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      });
      if (!res.ok) throw new Error(`set alias failed: ${res.status}`);
      return res.json();
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "models", decoded] }),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{decoded}</h1>
      <section>
        <h2 className="mb-2 text-sm font-semibold">Metadata</h2>
        <pre className="rounded-md border bg-white p-4 text-xs">
          {JSON.stringify(model ?? {}, null, 2)}
        </pre>
      </section>
      <section>
        <h2 className="mb-2 text-sm font-semibold">Versions</h2>
        <ul className="divide-y rounded-md border bg-white">
          {(versions?.versions ?? []).map((version) => (
            <li
              key={version.version}
              className="flex items-center justify-between px-4 py-2 text-sm"
            >
              <div>
                v{version.version} · run <code>{version.run_id ?? "?"}</code> ·{" "}
                <span className="text-xs text-muted-foreground">
                  aliases: {(version.aliases ?? []).join(", ") || "(none)"}
                </span>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="rounded-md border px-2 py-1 text-xs"
                  onClick={() => setPending({ alias: "champion", version: version.version })}
                >
                  Promote to champion
                </button>
                <button
                  type="button"
                  className="rounded-md border px-2 py-1 text-xs"
                  onClick={() => setPending({ alias: "challenger", version: version.version })}
                >
                  Set as challenger
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>
      <ConfirmFrictionDialog
        open={pending !== null}
        title={
          pending ? `Set ${decoded} :${pending.alias} → v${pending.version}?` : ""
        }
        description="Champion / challenger flips re-route inference traffic in production. Step-up MFA is enforced server-side."
        confirmPhrase="promote"
        busy={setAlias.isPending}
        onCancel={() => setPending(null)}
        onConfirm={(reason) => {
          if (!pending) return;
          setAlias.mutate({ ...pending, reason });
          setPending(null);
        }}
      />
    </div>
  );
}
