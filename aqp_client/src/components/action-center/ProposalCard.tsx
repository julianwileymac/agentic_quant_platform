import { CheckCircle2, ShieldAlert, ShieldCheck, ShieldX } from "lucide-react";
import type { ReactNode } from "react";

import { Numeric } from "@/components/common/Numeric";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { formatPercent, formatTime } from "@/lib/utils";
import type { AgentProposal } from "@/store/proposals";

interface ProposalCardProps {
  proposal: AgentProposal;
  onApprove: () => void;
  onDecline: () => void;
}

const STATUS_TONE: Record<NonNullable<AgentProposal["status"]>, "positive" | "negative" | "warn" | "secondary" | "default"> =
  {
    pending: "warn",
    approved: "positive",
    declined: "negative",
    expired: "secondary",
    executed: "positive",
  };

/**
 * One row in the Action Center stream — renders the agent's proposal,
 * the LTL guardrail outcomes, the cost-cap remaining, and the
 * approve / decline buttons. The buttons open the friction dialog;
 * this card is purely presentational.
 */
export function ProposalCard({ proposal, onApprove, onDecline }: ProposalCardProps) {
  const status = proposal.status ?? "pending";
  const tone = STATUS_TONE[status];
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-1">
          <CardTitle className="flex items-center gap-2">
            <span>{proposal.agent}</span>
            <Badge variant={tone} className="uppercase">
              {status}
            </Badge>
          </CardTitle>
          <span className="text-xs text-[var(--text-secondary)]">
            {proposal.ts ? formatTime(proposal.ts) : ""} · {proposal.id}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={proposal.side === "buy" ? "positive" : "negative"}>
            {proposal.side.toUpperCase()}
          </Badge>
          <Badge variant="secondary">{proposal.vt_symbol}</Badge>
        </div>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-3 text-sm">
        <Field label="Order type" value={proposal.order_type ?? "market"} />
        <Field
          label="Size"
          value={
            proposal.size_pct != null
              ? formatPercent(proposal.size_pct)
              : proposal.size_abs != null
                ? `${proposal.size_abs}`
                : "—"
          }
        />
        <Field
          label="Limit price"
          value={
            <Numeric value={proposal.price ?? null} kind="decimal" digits={2} color="auto" />
          }
        />
        <Field
          label="Confidence"
          value={
            <Numeric
              value={proposal.confidence ?? null}
              kind="percent"
              digits={1}
              color="auto"
              signed
            />
          }
        />
        <Field
          label="Expected PnL"
          value={
            <Numeric
              value={proposal.risk?.expected_pnl ?? null}
              kind="money"
              digits={0}
              color="auto"
              signed
            />
          }
        />
        <Field
          label="VaR 95"
          value={
            <Numeric value={proposal.risk?.var_95 ?? null} kind="money" digits={0} color="force-neg" />
          }
        />
        <Field
          label="Cost cap remaining"
          value={
            <Numeric
              value={proposal.risk?.cost_cap_remaining_usd ?? null}
              kind="money"
              digits={0}
              color={
                (proposal.risk?.cost_cap_remaining_usd ?? 0) < 5 ? "force-neg" : "neutral"
              }
            />
          }
        />
        <Field
          label="Max DD"
          value={
            <Numeric
              value={proposal.risk?.max_drawdown_pct ?? null}
              kind="percent"
              digits={2}
              color="force-neg"
            />
          }
        />
        {proposal.guardrails && proposal.guardrails.length > 0 ? (
          <div className="col-span-2 mt-1">
            <Separator className="my-2" />
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
              Guardrails (LTL)
            </div>
            <ul className="space-y-1">
              {proposal.guardrails.map((g) => (
                <li key={g.id} className="flex items-start gap-2 text-xs">
                  <GuardrailIcon status={g.status} />
                  <div className="flex-1">
                    <div className="font-mono">{g.rule}</div>
                    {g.detail ? (
                      <div className="text-[var(--text-secondary)]">{g.detail}</div>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {proposal.rationale ? (
          <div className="col-span-2 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3 text-xs italic text-[var(--text-secondary)]">
            “{proposal.rationale}”
          </div>
        ) : null}
      </CardContent>
      <CardFooter>
        <Button variant="outline" size="sm" onClick={onDecline} disabled={status !== "pending"}>
          Decline
        </Button>
        <Button
          size="sm"
          variant="positive"
          onClick={onApprove}
          disabled={status !== "pending" || guardrailFailed(proposal)}
          className="gap-1"
        >
          <CheckCircle2 className="h-4 w-4" /> Approve
        </Button>
      </CardFooter>
    </Card>
  );
}

interface FieldProps {
  label: string;
  value: ReactNode;
}

function Field({ label, value }: FieldProps) {
  return (
    <div className="flex items-center justify-between gap-3 text-xs">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-right font-mono">{value}</span>
    </div>
  );
}

function GuardrailIcon({ status }: { status: "pass" | "warn" | "fail" }) {
  if (status === "pass") return <ShieldCheck className="h-4 w-4 text-[var(--pos-fg)]" />;
  if (status === "warn") return <ShieldAlert className="h-4 w-4 text-[var(--warn-fg)]" />;
  return <ShieldX className="h-4 w-4 text-[var(--neg-fg)]" />;
}

function guardrailFailed(proposal: AgentProposal): boolean {
  return Boolean(proposal.guardrails?.some((g) => g.status === "fail"));
}
