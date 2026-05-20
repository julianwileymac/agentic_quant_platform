import { Bot } from "lucide-react";

import { ActionCenterPanel } from "@/components/action-center/ActionCenterPanel";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useProposalsStore } from "@/store/proposals";

export function ActionCenterRoute() {
  const total = useProposalsStore((s) => s.pending.length);
  return (
    <PageContainer
      title="Action Center"
      subtitle="Approve or decline agent-proposed trades. Every action is logged on agent_runs_v2 via AgentRuntime."
      extra={
        <Badge variant="warn" className="gap-2 px-3 py-1 text-xs">
          <Bot className="h-3 w-3" /> {total} active
        </Badge>
      }
    >
      <Card className="h-[calc(100vh-160px)]">
        <CardContent className="h-full p-3">
          <ActionCenterPanel />
        </CardContent>
      </Card>
    </PageContainer>
  );
}
