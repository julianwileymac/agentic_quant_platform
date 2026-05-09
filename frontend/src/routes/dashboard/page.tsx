import { Activity, Bot, CheckCircle2, CircleAlert, Power, Radio, ServerCog, TerminalSquare } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useApiQuery } from "@/lib/api/hooks";
import { usePendingCount } from "@/store/proposals";
import { useTenancyStore } from "@/store/tenancy";

interface HealthResponse {
  status: string;
  version?: string;
}

interface RootResponse {
  app?: string;
  version?: string;
  routes?: string[];
}

export function DashboardRoute() {
  const health = useApiQuery<HealthResponse>({ queryKey: ["health"], path: "/health" });
  const root = useApiQuery<RootResponse>({ queryKey: ["root"], path: "/" });
  const proposals = usePendingCount();
  const mode = useTenancyStore((s) => s.mode);

  const apiOnline = health.isSuccess && health.data?.status === "ok";
  const apiDegraded = health.isSuccess && health.data?.status === "degraded";

  return (
    <PageContainer
      title="Dashboard"
      subtitle="Operator overview of the agentic quant platform."
      extra={
        <Button asChild variant="default">
          <Link to="/live">
            <Radio className="h-4 w-4" /> Open Live Desk
          </Link>
        </Button>
      }
    >
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="API"
          icon={ServerCog}
          status={apiOnline ? "positive" : apiDegraded ? "warn" : "negative"}
          headline={apiOnline ? "Online" : apiDegraded ? "Degraded" : health.isPending ? "Checking…" : "Offline"}
          caption={root.data?.version ? `v${root.data.version}` : "FastAPI surface"}
        />
        <StatCard
          title="Mode"
          icon={Power}
          status={mode === "live" ? "positive" : "warn"}
          headline={mode.toUpperCase()}
          caption={
            mode === "live"
              ? "Live capital at risk."
              : mode === "paper"
                ? "Paper broker only."
                : "Sandbox simulation only."
          }
        />
        <StatCard
          title="Pending proposals"
          icon={Bot}
          status={proposals === 0 ? "positive" : "warn"}
          headline={<Numeric value={proposals} kind="integer" digits={0} color="neutral" />}
          caption="Agent-proposed trades awaiting approval"
        />
        <StatCard
          title="API routes registered"
          icon={Activity}
          status="info"
          headline={<Numeric value={root.data?.routes?.length ?? 0} kind="integer" digits={0} color="neutral" />}
          caption="OpenAPI surface"
        />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Recent activity</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-[var(--text-secondary)]">
            <p>
              Live activity (paper sessions, bot deployments, agent runs) populates here once
              the relevant routes are ported in Phase 2. The {" "}
              <Link className="text-[var(--info-fg)] underline" to="/live">
                Live Trading Desk
              </Link>{" "}
              and{" "}
              <Link className="text-[var(--info-fg)] underline" to="/action-center">
                Action Center
              </Link>{" "}
              are fully wired today.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Quick actions</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <QuickLink to="/live" icon={Radio} label="Open Live Desk" />
            <Separator />
            <QuickLink to="/action-center" icon={Bot} label="Approve / decline agent proposals" />
            <Separator />
            <QuickLink to="/ide" icon={TerminalSquare} label="Open Python IDE (Phase 6)" />
            <Separator />
            <QuickLink to="/backtest" icon={Activity} label="Backtests (Phase 2)" />
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}

interface StatCardProps {
  title: string;
  icon: typeof Activity;
  status: "positive" | "negative" | "warn" | "info";
  headline: ReactNode;
  caption: string;
}

function StatCard({ title, icon: Icon, status, headline, caption }: StatCardProps) {
  const statusColor =
    status === "positive"
      ? "text-[var(--pos-fg)]"
      : status === "negative"
        ? "text-[var(--neg-fg)]"
        : status === "warn"
          ? "text-[var(--warn-fg)]"
          : "text-[var(--info-fg)]";
  const StatusIcon = status === "negative" ? CircleAlert : CheckCircle2;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xs font-medium uppercase tracking-wide text-[var(--text-secondary)]">
          {title}
        </CardTitle>
        <Icon className="h-4 w-4 text-[var(--text-secondary)]" />
      </CardHeader>
      <CardContent className="flex items-center gap-3">
        <div className={`flex items-center gap-2 text-2xl font-semibold ${statusColor}`}>
          <StatusIcon className="h-5 w-5" />
          <span>{headline}</span>
        </div>
        <Badge variant="secondary" className="ml-auto whitespace-nowrap text-[10px] uppercase">
          {caption}
        </Badge>
      </CardContent>
    </Card>
  );
}

interface QuickLinkProps {
  to: string;
  icon: typeof Activity;
  label: string;
}

function QuickLink({ to, icon: Icon, label }: QuickLinkProps) {
  return (
    <Link
      to={to}
      className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-[var(--bg-elevated)]"
    >
      <Icon className="h-4 w-4 text-[var(--info-fg)]" />
      <span className="flex-1">{label}</span>
      <span className="font-mono text-[10px] text-[var(--text-muted)]">{to}</span>
    </Link>
  );
}
