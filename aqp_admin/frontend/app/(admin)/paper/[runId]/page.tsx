"use client";

import { useQuery } from "@tanstack/react-query";
import { use, useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { adminGet, adminPost } from "@/lib/api/client";

export default function PaperRunDetailPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = use(params);
  const [stopOpen, setStopOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const { data, refetch } = useQuery({
    queryKey: ["admin", "paper", runId],
    queryFn: () => adminGet<Record<string, unknown>>(`/paper/runs/${runId}`),
    refetchInterval: 5_000,
  });
  async function stop(reason: string) {
    setBusy(true);
    try {
      await adminPost(`/paper/runs/${runId}/stop`, {
        reason,
        cancel_open_orders: true,
      });
      await refetch();
    } finally {
      setBusy(false);
      setStopOpen(false);
    }
  }
  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Run {runId}</h1>
        <button
          type="button"
          onClick={() => setStopOpen(true)}
          className="rounded-md border border-red-300 bg-red-50 px-3 py-1.5 text-sm font-semibold text-red-700"
        >
          Stop run
        </button>
      </header>
      <pre className="rounded-md border bg-white p-4 text-xs">
        {JSON.stringify(data ?? {}, null, 2)}
      </pre>
      <ConfirmFrictionDialog
        open={stopOpen}
        title={`Stop paper run ${runId}?`}
        description="This cancels open orders and halts the Celery task. The run row gets status=halted in the audit ledger."
        confirmPhrase="stop"
        destructive
        busy={busy}
        onCancel={() => setStopOpen(false)}
        onConfirm={(reason) => void stop(reason)}
      />
    </div>
  );
}
