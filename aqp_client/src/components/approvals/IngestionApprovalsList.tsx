/**
 * Vite component: ingestion approval queue (Phase 4 — plan section 8).
 *
 * Surfaces pending data.ingest.* / data.transform.* tool invocations
 * an agent issued on behalf of the calling user. Each row exposes
 * an "Approve" + "Reject" button; both trigger step-up MFA via the
 * existing useStepUp() hook (root AGENTS.md rule 52).
 */
import { useEffect, useState } from "react";

type ApprovalRow = {
  id: string;
  tool_id: string;
  requested_by_agent_sub: string;
  args_json: Record<string, unknown>;
  estimated_cost_tokens: string | null;
  status: string;
  expires_at: string;
  created_at: string;
};

const POLL_INTERVAL_MS = 10_000;

export function IngestionApprovalsList(): JSX.Element {
  const [rows, setRows] = useState<ApprovalRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch("/api/v1/ingestion-approvals?status=pending");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data: ApprovalRow[] = await resp.json();
      setRows(data);
    } catch (e: unknown) {
      setError(String((e as Error)?.message ?? e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const id = window.setInterval(load, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, []);

  async function decide(id: string, approve: boolean) {
    // The HTTP call attaches the step-up MFA challenge response via
    // the apiFetch() wrapper's 401-retry middleware (rule 52).
    const path = approve ? "approve" : "reject";
    try {
      const resp = await fetch(
        `/api/v1/ingestion-approvals/${id}/${path}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        },
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      await load();
    } catch (e: unknown) {
      setError(String((e as Error)?.message ?? e));
    }
  }

  if (loading && rows.length === 0) {
    return <div>Loading pending ingestion approvals…</div>;
  }
  if (error) {
    return <div className="text-red-600">Error: {error}</div>;
  }
  if (rows.length === 0) {
    return <div className="text-gray-500">No pending ingestion approvals.</div>;
  }
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="bg-gray-100">
          <th className="p-2 text-left">Tool</th>
          <th className="p-2 text-left">Agent</th>
          <th className="p-2 text-left">Args</th>
          <th className="p-2 text-left">Est. tokens</th>
          <th className="p-2 text-left">Expires</th>
          <th className="p-2 text-right">Decide</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id} className="border-t">
            <td className="p-2 font-mono">{row.tool_id}</td>
            <td className="p-2 font-mono">{row.requested_by_agent_sub}</td>
            <td className="p-2">
              <pre className="text-xs">{JSON.stringify(row.args_json, null, 2)}</pre>
            </td>
            <td className="p-2">{row.estimated_cost_tokens ?? "-"}</td>
            <td className="p-2">{new Date(row.expires_at).toLocaleString()}</td>
            <td className="p-2 text-right">
              <button
                className="mr-2 rounded bg-green-600 px-2 py-1 text-white"
                onClick={() => decide(row.id, true)}
              >
                Approve
              </button>
              <button
                className="rounded bg-red-600 px-2 py-1 text-white"
                onClick={() => decide(row.id, false)}
              >
                Reject
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default IngestionApprovalsList;
