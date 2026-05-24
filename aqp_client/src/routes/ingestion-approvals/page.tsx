/**
 * /ingestion-approvals — Vite route for the Phase 4 approval queue.
 */
import { IngestionApprovalsList } from "../../components/approvals/IngestionApprovalsList";

export default function IngestionApprovalsPage(): JSX.Element {
  return (
    <main className="mx-auto max-w-6xl space-y-4 p-6">
      <header>
        <h1 className="text-2xl font-semibold">Pending agent ingestion approvals</h1>
        <p className="text-sm text-gray-600">
          Approve or reject mutating data.ingest.* / data.transform.* tool
          calls an autonomous agent issued on your behalf. Step-up MFA is
          required for every decision.
        </p>
      </header>
      <IngestionApprovalsList />
    </main>
  );
}
