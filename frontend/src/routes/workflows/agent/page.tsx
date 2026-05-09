import { Bot, Workflow } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  AGENT_CREW_NODE_ACCENTS,
  AGENT_CREW_PALETTE,
} from "@/components/agents/agentCrewPalette";
import { serializeCrewSpec } from "@/components/agents/agentCrewSerializer";
import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import type { FlowGraph } from "@/components/flow/types";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";

const DRAFT_KEY = "aqp-agent-crew-draft";

export function AgentCrewEditorRoute() {
  const [name, setName] = useState("agent-crew");
  const [draft, setDraft] = useState<FlowGraph | undefined>(undefined);

  // Restore the saved draft once on mount.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(DRAFT_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as { name?: string; graph?: FlowGraph };
      if (parsed.name) setName(parsed.name);
      if (parsed.graph?.version === 1) setDraft(parsed.graph);
    } catch {
      // ignore corrupt drafts
    }
  }, []);

  const initialGraph = useMemo(() => draft, [draft]);

  return (
    <PageContainer
      title="Agent Crew Editor"
      subtitle="Compose a CrewAI-style spec from LLM, Memory, Tools, Agents, Tasks, Outputs. Phase 4 saves to localStorage + clipboard; a backend persistence endpoint can land separately."
      extra={
        <Badge variant="warn" className="gap-2">
          <Workflow className="h-3 w-3" /> draft persistence: localStorage
        </Badge>
      }
      bleed
    >
      <div className="flex h-[calc(100vh-160px)] flex-col gap-3 px-6 pb-6">
        <div className="flex max-w-md items-center gap-2">
          <Bot className="h-4 w-4 text-[var(--info-fg)]" />
          <Label htmlFor="crew-name" className="shrink-0">
            Crew name
          </Label>
          <Input id="crew-name" value={name} onChange={(e) => setName(e.target.value)} />
        </div>

        <div className="min-h-0 flex-1">
          <WorkflowEditor
            domain="agent"
            paletteSections={AGENT_CREW_PALETTE}
            accentByKind={AGENT_CREW_NODE_ACCENTS}
            {...(initialGraph ? { initialGraph } : {})}
            onSave={async (graph) => {
              const spec = serializeCrewSpec(graph, name.trim() || "agent-crew");
              const payload = { name, graph };
              try {
                window.localStorage.setItem(DRAFT_KEY, JSON.stringify(payload));
                await navigator.clipboard.writeText(JSON.stringify(spec, null, 2));
                toast.success("Crew spec copied to clipboard + draft saved");
              } catch {
                toast.success("Draft saved to localStorage", {
                  description: "Clipboard copy failed; export via the toolbar instead.",
                });
              }
            }}
          />
        </div>
      </div>
    </PageContainer>
  );
}
