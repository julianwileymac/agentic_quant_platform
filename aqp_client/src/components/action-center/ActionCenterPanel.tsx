import { Inbox, RefreshCcw } from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { Numeric } from "@/components/common/Numeric";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { apiFetch, ApiError } from "@/lib/api/client";
import { formatPercent } from "@/lib/utils";
import { useProposalsStore, type AgentProposal } from "@/store/proposals";
import { useTenancyStore } from "@/store/tenancy";

import { ProposalCard } from "./ProposalCard";

interface ActionCenterPanelProps {
  /** Whether to show the page-level chrome (title etc.) — defaults to true. */
  embedded?: boolean;
}

type Pending = AgentProposal & { status: "pending" };

/**
 * Action Center body. Used both at `/action-center` (page) and inside
 * the topbar drawer dialog. Subscribes to the proposals Zustand store
 * (the WS stream is opened once at the App root, see `useProposalsStream`).
 */
export function ActionCenterPanel(_props: ActionCenterPanelProps) {
  const proposals = useProposalsStore((s) => s.pending);
  const remove = useProposalsStore((s) => s.remove);
  const upsert = useProposalsStore((s) => s.upsert);
  const mode = useTenancyStore((s) => s.mode);

  const pending = useMemo<Pending[]>(
    () => proposals.filter((p): p is Pending => (p.status ?? "pending") === "pending"),
    [proposals],
  );
  const recent = useMemo(
    () => proposals.filter((p) => p.status && p.status !== "pending"),
    [proposals],
  );

  const [target, setTarget] = useState<AgentProposal | null>(null);
  const [actionKind, setActionKind] = useState<"approve" | "decline" | null>(null);

  const onAct = (proposal: AgentProposal, kind: "approve" | "decline") => {
    setTarget(proposal);
    setActionKind(kind);
  };

  const submit = async () => {
    if (!target || !actionKind) return;
    const path = `/agents/proposals/${target.id}/${actionKind}`;
    try {
      await apiFetch(path, { method: "POST" });
      upsert({ ...target, status: actionKind === "approve" ? "approved" : "declined" });
      toast.success(
        `${actionKind === "approve" ? "Approved" : "Declined"} ${target.agent}`,
        {
          description: `${target.side.toUpperCase()} ${target.vt_symbol}`,
        },
      );
      setTimeout(() => remove(target.id), 4_000);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Action failed: ${message}`);
      throw err;
    }
  };

  const friction = target && actionKind ? buildFrictionConfig(target, actionKind, mode) : null;

  return (
    <div className="flex h-full flex-col gap-3">
      <Tabs defaultValue="pending" className="flex h-full flex-col">
        <TabsList className="self-start">
          <TabsTrigger value="pending">
            Pending
            <Badge variant="warn" className="ml-2">
              {pending.length}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="recent">
            Recent
            <Badge variant="secondary" className="ml-2">
              {recent.length}
            </Badge>
          </TabsTrigger>
        </TabsList>
        <TabsContent value="pending" className="flex-1 min-h-0">
          <ScrollArea className="h-full pr-2">
            {pending.length === 0 ? (
              <EmptyState />
            ) : (
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {pending.map((p) => (
                  <ProposalCard
                    key={p.id}
                    proposal={p}
                    onApprove={() => onAct(p, "approve")}
                    onDecline={() => onAct(p, "decline")}
                  />
                ))}
              </div>
            )}
          </ScrollArea>
        </TabsContent>
        <TabsContent value="recent" className="flex-1 min-h-0">
          <ScrollArea className="h-full pr-2">
            {recent.length === 0 ? (
              <EmptyState
                icon={RefreshCcw}
                title="No recent activity"
                hint="Approved / declined proposals will appear here for 60 seconds."
              />
            ) : (
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {recent.map((p) => (
                  <ProposalCard
                    key={p.id}
                    proposal={p}
                    onApprove={() => onAct(p, "approve")}
                    onDecline={() => onAct(p, "decline")}
                  />
                ))}
              </div>
            )}
          </ScrollArea>
        </TabsContent>
      </Tabs>

      {friction ? (
        <ConfirmFrictionDialog
          open={target != null && actionKind != null}
          onOpenChange={(open) => {
            if (!open) {
              setTarget(null);
              setActionKind(null);
            }
          }}
          title={friction.title}
          consequence={friction.consequence}
          details={friction.details}
          confirmPhrase={friction.confirmPhrase}
          confirmLabel={friction.confirmLabel}
          confirmVariant={friction.confirmVariant}
          onConfirm={submit}
        />
      ) : null}
    </div>
  );
}

interface EmptyStateProps {
  icon?: typeof Inbox;
  title?: string;
  hint?: string;
}

function EmptyState({
  icon: Icon = Inbox,
  title = "No pending proposals",
  hint = "Agent runs that gate on human approval will appear here in real time.",
}: EmptyStateProps) {
  return (
    <div className="flex h-48 flex-col items-center justify-center gap-2 text-[var(--text-secondary)]">
      <Icon className="h-8 w-8" />
      <span className="text-sm font-medium">{title}</span>
      <span className="text-xs">{hint}</span>
    </div>
  );
}

interface FrictionConfig {
  title: string;
  consequence: string;
  details: Array<{ label: string; value: ReactNode; tone?: "positive" | "negative" | "warn" | "neutral" }>;
  confirmPhrase: string;
  confirmLabel: string;
  confirmVariant: "destructive" | "default" | "warn";
}

function buildFrictionConfig(
  proposal: AgentProposal,
  kind: "approve" | "decline",
  mode: "live" | "paper" | "sandbox",
): FrictionConfig {
  if (kind === "decline") {
    return {
      title: `Decline ${proposal.agent}'s ${proposal.side.toUpperCase()} ${proposal.vt_symbol}`,
      consequence:
        "The agent will receive the rejection signal and will not retry this exact proposal during the current run. The decision is logged on agent_runs_v2.",
      details: [
        { label: "Agent", value: proposal.agent },
        { label: "Symbol", value: proposal.vt_symbol },
        { label: "Side", value: proposal.side.toUpperCase(), tone: proposal.side === "buy" ? "positive" : "negative" },
      ],
      confirmPhrase: "DECLINE",
      confirmLabel: "Decline proposal",
      confirmVariant: "destructive",
    };
  }
  const isLive = mode === "live";
  return {
    title: `Approve ${proposal.agent}'s ${proposal.side.toUpperCase()} ${proposal.vt_symbol}`,
    consequence: isLive
      ? "Approving routes the proposal through the live broker. Real capital is at risk and the action is irreversible once filled."
      : "Approving routes the proposal through the paper broker. No real capital is at risk.",
    details: [
      { label: "Symbol", value: proposal.vt_symbol },
      { label: "Side", value: proposal.side.toUpperCase(), tone: proposal.side === "buy" ? "positive" : "negative" },
      {
        label: "Size",
        value:
          proposal.size_pct != null
            ? formatPercent(proposal.size_pct)
            : proposal.size_abs != null
              ? proposal.size_abs
              : "—",
      },
      {
        label: "Confidence",
        value:
          proposal.confidence != null ? (
            <Numeric value={proposal.confidence} kind="percent" digits={1} color="neutral" />
          ) : (
            "—"
          ),
      },
      {
        label: "Limit price",
        value:
          proposal.price != null ? (
            <Numeric value={proposal.price} kind="decimal" digits={2} color="neutral" />
          ) : (
            "—"
          ),
      },
      {
        label: "Expected PnL",
        value:
          proposal.risk?.expected_pnl != null ? (
            <Numeric value={proposal.risk.expected_pnl} kind="money" digits={0} color="auto" signed />
          ) : (
            "—"
          ),
        tone: "warn",
      },
      {
        label: "VaR 95",
        value:
          proposal.risk?.var_95 != null ? (
            <Numeric value={proposal.risk.var_95} kind="money" digits={0} color="force-neg" />
          ) : (
            "—"
          ),
        tone: "negative",
      },
      {
        label: "Cost cap remaining",
        value:
          proposal.risk?.cost_cap_remaining_usd != null ? (
            <Numeric
              value={proposal.risk.cost_cap_remaining_usd}
              kind="money"
              digits={0}
              color="auto"
            />
          ) : (
            "—"
          ),
      },
      { label: "Mode", value: mode.toUpperCase(), tone: isLive ? "warn" : "neutral" },
    ],
    confirmPhrase: isLive ? "FIRE" : "APPROVE",
    confirmLabel: "Approve and route",
    confirmVariant: isLive ? "destructive" : "default",
  };
}
