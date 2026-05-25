import type { Metadata } from "next";
import {
  Activity,
  BookOpen,
  BrainCircuit,
  CheckCircle,
  GitBranch,
  Hexagon,
  Layers,
  Lock,
  MessagesSquare,
  Network,
  ScrollText,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "lucide-react";

import { AgentFlowDiagram } from "@/components/marketing/illustrations/AgentFlowDiagram";
import { CallToActionBlock } from "@/components/marketing/CallToActionBlock";
import { CodeBlock } from "@/components/marketing/CodeBlock";
import { FaqAccordion } from "@/components/marketing/FaqAccordion";
import { FeatureBreakdown } from "@/components/marketing/FeatureBreakdown";
import { FeatureCard } from "@/components/marketing/FeatureCard";
import { FeatureGrid } from "@/components/marketing/FeatureGrid";
import { Hero } from "@/components/marketing/Hero";
import { MotionInView } from "@/components/marketing/MotionInView";
import { ProductNav } from "@/components/marketing/ProductNav";
import { SectionHeader } from "@/components/marketing/SectionHeader";
import { StatStrip } from "@/components/marketing/StatStrip";
import { WorkflowOrchestrationDiagram } from "@/components/marketing/illustrations/WorkflowOrchestrationDiagram";

export const metadata: Metadata = {
  title: "AgentOps",
  description:
    "Hash-locked agent specs, five canonical multi-agent patterns, Workflow Studio orchestration, and built-in guardrails. The agentic stack for quantitative finance.",
};

export const dynamic = "force-static";
export const revalidate = 3600;

const NAV_ITEMS = [
  { id: "overview", label: "Overview" },
  { id: "specs", label: "Hash-locked specs" },
  { id: "patterns", label: "Multi-agent patterns" },
  { id: "workflows", label: "Workflow Studio" },
  { id: "guardrails", label: "Guardrails" },
  { id: "datamcp", label: "DataMCP boundary" },
  { id: "faq", label: "FAQ" },
];

export default function AgentOpsPage() {
  return (
    <>
      <Hero
        eyebrow="Product · AgentOps"
        eyebrowIcon={BrainCircuit}
        title="Agents you can deploy near live capital."
        titleHighlight="near live capital"
        subtitle="Every AQP agent is a hash-locked spec executed by a typed runtime. Guardrails are enforced at runtime, not as documentation. Five canonical multi-agent patterns. One DataMCP boundary keeping agents on rails."
        primaryCta={{ label: "Start free", href: "/signup" }}
        secondaryCta={{ label: "Read the docs", href: "/docs" }}
        illustration={
          <div
            className="overflow-hidden rounded-xl p-2"
            style={{
              background: "var(--glass-bg)",
              border: "1px solid var(--glass-border)",
              backdropFilter: "blur(var(--glass-blur))",
            }}
          >
            <AgentFlowDiagram />
          </div>
        }
      />

      <ProductNav items={NAV_ITEMS} />

      <StatStrip
        stats={[
          { value: 5, label: "Spec runtimes", tone: "primary" },
          { value: 5, label: "Multi-agent patterns", tone: "secondary" },
          { value: 7, label: "Orchestration adapters", tone: "tertiary" },
          { value: 6, label: "Guardrail kinds", tone: "primary" },
        ]}
      />

      {/* Overview */}
      <section id="overview" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Overview"
            title="Five hash-locked runtimes power every agentic workflow"
            subtitle="AgentSpec, BotSpec, RLExperimentSpec, AnalysisSpec, WorkflowSpec — all five share the same hash-lock + immutable + ledger-backed semantics."
          />
          <FeatureGrid columns={3}>
            <FeatureCard
              icon={Sparkles}
              tone="primary"
              title="AgentSpec + AgentRuntime"
              body="Hash-locked agent definition with model, tools, guardrails, and prompt. AgentRuntime is the only sanctioned executor — it enforces cost caps and writes the ledger row."
            />
            <FeatureCard
              icon={Hexagon}
              tone="secondary"
              title="BotSpec + BotRuntime"
              body="Smallest deployable unit. Aggregates universe + strategy + engine + ML + agents + RAG. Drives backtest / paper / chat / k8s deploy."
            />
            <FeatureCard
              icon={Network}
              tone="tertiary"
              title="WorkflowSpec + WorkflowRuntime"
              body="Composes agents and bots into replayable pipelines via seven OrchestrationAdapters: graph, crew, debate, fusion, execution, schedule, studio."
            />
            <FeatureCard
              icon={Activity}
              tone="primary"
              title="RLExperimentSpec + RLRuntime"
              body="Reinforcement-learning experiments with hash-locked components, Iceberg trajectories, and replay against historical data windows."
            />
            <FeatureCard
              icon={ScrollText}
              tone="warn"
              title="AnalysisSpec + AnalysisRuntime"
              body="55-flow catalog covering distribution, outliers, regression, time series, derivatives, portfolio, factors, microstructure, profiling."
            />
            <FeatureCard
              icon={Workflow}
              tone="secondary"
              title="Workflow Studio"
              body="Visual builder for stitching the above together. Halt checks between every adapter transition. ~250ms global stop via the topbar KillSwitch."
            />
          </FeatureGrid>
        </div>
      </section>

      {/* Hash-locked specs */}
      <section
        id="specs"
        className="px-6"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <FeatureBreakdown
          eyebrow="Hash-locked specs"
          tone="primary"
          title="Behaviour changes always produce a new version row."
          body="AQP deliberately rejects the 'rewrite the skill on failure' pattern. Why? Auditability — every behaviour change must be a new hash-locked version row. Replay — runs reference spec_version_id; mutating the spec breaks the replay invariant. Compliance — financial systems need an append-only audit trail."
          bullets={[
            "SHA-256 of canonical-JSON spec is the version key",
            "Same content → same version (idempotent persist)",
            "Any field change → new immutable version row",
            "agent_runs_v2 row references spec_version_id for deterministic replay",
          ]}
          cta={{ label: "Read the deep-dive", href: "/learn/hash-locked-specs" }}
          visual={
            <CodeBlock
              filename="snapshot.py"
              language="python"
              code={`from aqp.agents import AgentRuntime, AgentSpec, persist_spec

spec = AgentSpec(
    name="alpha.researcher",
    model="claude-4-sonnet",
    prompt_template="Find 3 momentum factors over {universe}.",
    tools=["data.bars.fetch", "data.indicators.compute"],
    guardrails={
        "cost_budget_usd": 5.0,
        "max_calls": 20,
        "rate_limit_per_minute": 60,
    },
)

# First call snapshots an immutable agent_spec_versions row.
version_id = persist_spec(spec)         # 9a4f...c1d3

# Mutate any field, persist again → NEW version row.
spec.guardrails["cost_budget_usd"] = 10.0
new_version_id = persist_spec(spec)     # 2b18...77ea

# Old version is still queryable for replay.
old_run = AgentRuntime.replay(run_id=last_run_id)
assert old_run.spec_version_id == version_id`}
            />
          }
        />
      </section>

      {/* Multi-agent patterns */}
      <section id="patterns" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Multi-agent patterns"
            title="Five canonical topologies, all production-wired"
            subtitle="Whether you need deterministic linear pipelines, adversarial debate, or open-ended ReAct loops — pick the pattern, AQP handles the orchestration."
          />
          <FeatureGrid columns={3}>
            <FeatureCard
              icon={GitBranch}
              tone="primary"
              title="Sequential"
              body="Deterministic linear pipeline. Each agent's output is the next agent's input. The default for most analyses and signal generation."
            />
            <FeatureCard
              icon={Layers}
              tone="primary"
              title="Parallel"
              body="Independent multi-source research with synthesis. Run Bull, Bear, Macro researchers concurrently, fan-in to a portfolio manager."
            />
            <FeatureCard
              icon={MessagesSquare}
              tone="secondary"
              title="Debate / Dialectical"
              body="Adversarial analysis inspired by TradingAgents. Bull and Bear researchers exchange arguments; a portfolio manager synthesises a verdict."
            />
            <FeatureCard
              icon={Network}
              tone="tertiary"
              title="Coordinator / Router"
              body="Hierarchical delegation. A coordinator agent picks the right specialist for the task and routes the request through the matching spec."
            />
            <FeatureCard
              icon={Activity}
              tone="warn"
              title="ReAct"
              body="Loop-with-observation for open-ended forecasting. Agent reasons, takes a tool action, observes the result, and iterates until a stop condition."
            />
            <FeatureCard
              icon={Workflow}
              tone="secondary"
              title="Compose any of the above"
              body="WorkflowSpec composes these patterns. A research workflow can be parallel-debate at the top, sequential at the bottom, with a coordinator router in the middle."
            />
          </FeatureGrid>
          <div className="mt-10 text-center">
            <a
              href="/learn/multi-agent-patterns"
              className="inline-flex items-center gap-2 text-sm font-semibold"
              style={{ color: "var(--accent-primary)" }}
            >
              <BookOpen size={14} />
              Deep-dive: when to pick which pattern →
            </a>
          </div>
        </div>
      </section>

      {/* Workflow Studio */}
      <section
        id="workflows"
        className="px-6"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <FeatureBreakdown
          eyebrow="Workflow Studio"
          tone="secondary"
          title="Compose agents into hash-locked, replayable pipelines."
          body="A workflow selects exactly one OrchestrationAdapter by alias and hands it adapter-specific params. Seven adapter kinds — graph, crew, debate, fusion, execution, schedule, studio — auto-register through OrchestrationAdapterMeta. Every run produces a workflow_runs row, per-adapter OTEL spans, WebSocket live progress frames, and optional agent_runs_v2 rows for inner AgentRuntime calls."
          bullets={[
            "Halt check between every adapter transition (~250ms global stop)",
            "Immutable workflow_spec_versions snapshots — same hash → same version",
            "Topbar KillSwitch fans out to /workflows/halt with five sibling endpoints",
            "Replay any run with /workflows/runs/{run_id}/replay",
          ]}
          cta={{ label: "Workflow Studio docs", href: "/docs/workflows" }}
          reverse
          visual={
            <div
              className="overflow-hidden rounded-xl p-2"
              style={{
                background: "var(--glass-bg)",
                border: "1px solid var(--glass-border)",
                backdropFilter: "blur(var(--glass-blur))",
              }}
            >
              <WorkflowOrchestrationDiagram />
            </div>
          }
        />
      </section>

      {/* Guardrails */}
      <section id="guardrails" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Guardrails"
            title="Cost, rate, and content limits enforced at runtime"
            subtitle="AgentSpec.guardrails is parsed by AgentRuntime._guardrail_check. Violations raise GuardrailViolation BEFORE the LLM call executes. No quiet over-budget runs."
          />
          <FeatureGrid columns={3}>
            <FeatureCard
              icon={ShieldCheck}
              tone="primary"
              title="cost_budget_usd"
              body="Hard ceiling per run. The runtime tracks cumulative provider cost via the token catalog and raises when the budget is hit."
            />
            <FeatureCard
              icon={Activity}
              tone="tertiary"
              title="rate_limit_per_minute"
              body="Per-spec rate limit honoured across concurrent runs. Pair with max_calls for total budget control."
            />
            <FeatureCard
              icon={CheckCircle}
              tone="secondary"
              title="max_calls"
              body="Caps the number of LLM round-trips per run. Prevents ReAct loops from spinning forever."
            />
            <FeatureCard
              icon={Lock}
              tone="warn"
              title="forbidden_terms"
              body="Substring blacklist applied to LLM output. Use it to keep agents off PII, brokerage account numbers, or anything else you can string-match."
            />
            <FeatureCard
              icon={ScrollText}
              tone="primary"
              title="require_rationale"
              body="Forces the agent to emit a structured rationale alongside the result. Recorded on agent_runs_v2 for audit."
            />
            <FeatureCard
              icon={Sparkles}
              tone="secondary"
              title="min_confidence"
              body="Minimum self-reported confidence floor. Agent runs with confidence < threshold are flagged for review (not silently dropped)."
            />
          </FeatureGrid>
        </div>
      </section>

      {/* DataMCP boundary */}
      <section
        id="datamcp"
        className="px-6"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <FeatureBreakdown
          eyebrow="DataMCP boundary"
          tone="tertiary"
          title="Agents never touch the database directly."
          body="Every catalog / dataset / entity / pipeline read from agent code goes through a registered DataMCPTool. Agent bodies are forbidden from `import aqp.persistence.models...` or `iceberg_catalog.append_arrow`. The boundary lets you reason about agent capability the same way you reason about a microservice's RPC surface."
          bullets={[
            "Subclass DataMCPTool, decorate with @register_data_mcp_tool",
            "Bridge auto-installs into the AgentRuntime TOOL_REGISTRY",
            "Same catalog exposed externally via FastAPI /mcp/data + aqp-data-mcp stdio binary",
            "RFC 9728 + RFC 8707 conformant (per-tool aud claim)",
          ]}
          cta={{ label: "DataMCP architecture", href: "/docs/datamcp" }}
          visual={
            <CodeBlock
              filename="data_mcp_tool.py"
              language="python"
              code={`from aqp.data.mcp.base import DataMCPTool
from aqp.data.mcp.registry import register_data_mcp_tool

@register_data_mcp_tool
class FetchEarningsCalendar(DataMCPTool):
    """Returns the next 7 days of earnings releases for a symbol set."""

    name = "data.earnings.calendar"
    audience_aud = "https://aqp.fund/mcp/data"
    schema_in = EarningsCalendarRequest
    schema_out = EarningsCalendarResponse

    def invoke(self, req: EarningsCalendarRequest) -> EarningsCalendarResponse:
        # Reads through DatasetCatalog + Iceberg via the platform helpers.
        # Never \`import aqp.persistence.models...\` here.
        bars = read_dataset("aqp_silver_earnings.calendar", req.symbols)
        return EarningsCalendarResponse(events=summarise(bars, req.window))`}
            />
          }
        />
      </section>

      {/* Wrap-up benefits */}
      <section className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="What you get"
            title="Audit-grade agents without the boilerplate"
          />
          <FeatureGrid columns={4}>
            <FeatureCard
              icon={ScrollText}
              tone="primary"
              title="agent_runs_v2 ledger"
              body="Every run writes spec_version_id, model, cost_usd, latency_ms, findings_count, halt reason."
            />
            <FeatureCard
              icon={Lock}
              tone="tertiary"
              title="Halt at any time"
              body="Topbar KillSwitch hits /agents/halt + /workflows/halt + 4 siblings via Promise.allSettled."
            />
            <FeatureCard
              icon={Workflow}
              tone="secondary"
              title="One LLM gateway"
              body="All LLM calls route through router_complete. Provider failover, semantic cache, token catalog."
            />
            <FeatureCard
              icon={Sparkles}
              tone="warn"
              title="Watchdog included"
              body="A Celery beat task auto-halts stalled rows; /agents/health surfaces them in the dashboard."
            />
          </FeatureGrid>
        </div>
      </section>

      {/* FAQ */}
      <section
        id="faq"
        className="px-6 py-20"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="FAQ"
            title="AgentOps questions"
          />
          <FaqAccordion items={FAQ_ITEMS} />
        </div>
      </section>

      <CallToActionBlock
        eyebrow="Ready to ship"
        title="Wire your first agent in under five minutes."
        subtitle="Start free. Author a spec, snapshot it, run it through AgentRuntime. The ledger row writes itself."
        primaryCta={{ label: "Start free", href: "/signup" }}
        secondaryCta={{
          label: "Read AgentOps in finance",
          href: "/learn/agentops-in-finance",
        }}
      />
    </>
  );
}

const FAQ_ITEMS = [
  {
    question: "Why not let agents self-modify their prompts?",
    answer:
      "Three reasons: auditability (every behaviour change must be a new hash-locked version row); replay (runs reference spec_version_id, and mutating breaks the replay invariant); compliance (financial systems need an append-only audit trail). AQP forbids the self-modifying-skill pattern by design.",
  },
  {
    question: "How are LLM costs controlled?",
    answer:
      "Two layers. (1) AgentSpec.guardrails.cost_budget_usd is enforced per run by AgentRuntime via the token catalog — a violation raises GuardrailViolation BEFORE the next LLM call. (2) The router_complete gateway provides provider-level failover, semantic cache, and a token catalog for cross-org budget rollups.",
  },
  {
    question: "Can I bring my own LLM provider?",
    answer:
      "Yes. router_complete is built on LiteLLM and supports OpenAI, Anthropic, Google, Cohere, Mistral, Together, Groq, Fireworks, Bedrock, Azure OpenAI, plus a local Ollama / vLLM endpoint. Configure provider priority + failover order via Settings; reference the provider alias in AgentSpec.model.",
  },
  {
    question: "What does the Workflow Studio give me that AgentRuntime doesn't?",
    answer:
      "AgentRuntime executes one agent against one spec. WorkflowRuntime composes multiple agents (or bots / RL experiments / analyses) into a single hash-locked pipeline. Workflows pick exactly one OrchestrationAdapter (graph, crew, debate, fusion, execution, schedule, studio) and inherit its semantics — halt-checks, replay, OTEL spans, WebSocket progress.",
  },
  {
    question: "Is the DataMCP boundary enforced or just convention?",
    answer:
      "Both. The convention is in AGENTS.md rule 22 (no `import aqp.persistence.models...` inside agent code). The enforcement is a source linter that fails CI on direct imports plus the in-process bridge that only exposes registered DataMCPTool instances to AgentRuntime. External agent clients connect over HTTP / stdio and authenticate per RFC 8707 audience checks.",
  },
];
