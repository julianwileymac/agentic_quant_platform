"use client";

import { useQuery } from "@tanstack/react-query";
import { use, useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { adminGet, adminPost } from "@/lib/api/client";

export default function SecretDetailPage({
  params,
}: {
  params: Promise<{ ref: string }>;
}) {
  const { ref } = use(params);
  const decoded = decodeURIComponent(ref);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const { data, refetch } = useQuery({
    queryKey: ["admin", "secret", decoded],
    queryFn: () =>
      adminGet<Record<string, unknown>>(`/secrets/${encodeURIComponent(decoded)}`),
  });

  async function rotate(reason: string) {
    setBusy(true);
    try {
      await adminPost(`/secrets/${encodeURIComponent(decoded)}/rotate`, {
        reason,
        notify_consumers: true,
      });
      await refetch();
    } finally {
      setBusy(false);
      setOpen(false);
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Secret {decoded}</h1>
        <button
          type="button"
          className="rounded-md border border-amber-300 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-900"
          onClick={() => setOpen(true)}
        >
          Rotate (step-up MFA)
        </button>
      </header>
      <pre className="rounded-md border bg-white p-4 text-xs">
        {JSON.stringify(data ?? {}, null, 2)}
      </pre>
      <ConfirmFrictionDialog
        open={open}
        title={`Rotate ${decoded}?`}
        description="The new version is written through the registered backend; consumer pods are notified by rolling restart. The plaintext value is never returned to this UI."
        confirmPhrase="rotate"
        destructive
        busy={busy}
        onCancel={() => setOpen(false)}
        onConfirm={(reason) => void rotate(reason)}
      />
    </div>
  );
}
