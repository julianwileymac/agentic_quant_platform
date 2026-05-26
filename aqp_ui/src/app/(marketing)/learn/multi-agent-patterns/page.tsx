import type { Metadata } from "next";

import { CodeBlock } from "@/components/marketing/CodeBlock";
import { LearnArticleLayout } from "@/components/marketing/LearnArticleLayout";
import { WorkflowOrchestrationDiagram } from "@/components/marketing/illustrations/WorkflowOrchestrationDiagram";

export const metadata: Metadata = {
  title: "Five multi-agent patterns in production",
  description:
    "Sequential, parallel, debate, coordinator, ReAct — when each topology earns its keep, and the failure modes you should plan for.",
};

export const dynamic = "force-static";
export const revalidate = 86400;

export default function MultiAgentPatternsPage() {
  return (
    <LearnArticleLayout
      eyebrow="Agentic · 11 min read"
      title="Five multi-agent patterns in production"
      readMinutes={11}
      dateLine="Updated May 2026"
      toc={[
        { id: "why-patterns", label: "Why patterns matter" },
        { id: "sequential", label: "Sequential" },
        { id: "parallel", label: "Parallel" },
        { id: "debate", label: "Debate / Dialectical" },
        { id: "coordinator", label: "Coordinator / Router" },
        { id: "react", label: "ReAct" },
        { id: "compose", label: "Compose any of the above" },
        { id: "failures", label: "Failure modes" },
      ]}
      related={[
        {
          href: "/learn/agentops-in-finance",
          title: "AgentOps in finance",
          category: "Agentic",
        },
        {
          href: "/learn/hash-locked-specs",
          title: "Hash-locked specs",
          category: "Agentic",
        },
        {
          href: "/product/agentops#workflows",
          title: "Workflow Studio product",
          category: "Product",
        },
      ]}
      cta={{
        title: "Build a workflow",
        body: "The Workflow Studio in AQP composes any of these patterns into a hash-locked, replayable pipeline.",
        label: "Try it free",
        href: "/signup",
      }}
    >
      <p
        className="rounded-lg p-4 text-base"
        style={{
          background: "rgba(167,139,250,0.06)",
          border: "1px solid rgba(167,139,250,0.3)",
          color: "var(--text-primary)",
        }}
      >
        <strong>TL;DR.</strong> Five canonical multi-agent topologies cover
        almost every real-world quant agentic workflow: sequential, parallel,
        debate, coordinator, ReAct. Pick by the structure of the problem, not
        the personality of the LLM. AQP wires all five into hash-locked
        WorkflowSpecs and ledger-tracks every transition.
      </p>

      <h2 id="why-patterns">Why patterns matter</h2>
      <p>
        "Just give the agent more tools" is a common, expensive mistake. A
        single LLM with twenty tools and a vague prompt spends most of its
        budget rediscovering structure that the engineer already knew. The
        cure is to encode the problem's structure in the pipeline shape — to
        let the topology do work that the LLM would otherwise pay for in
        tokens.
      </p>
      <p>
        AQP supports five canonical topologies, all production-wired through
        the WorkflowRuntime + OrchestrationAdapter contract. Each one earns
        its keep on a different class of problem.
      </p>

      <h2 id="sequential">Sequential — deterministic linear pipeline</h2>
      <p>
        The default. Each agent's output is the next agent's input. Use it
        when you have a clear step-by-step structure: <em>fetch → analyse →
        decide → format</em>. Sequential workflows are the easiest to debug
        because the data flow is one-directional and any frame in the
        WebSocket stream tells you exactly where you are in the pipeline.
      </p>
      <p>
        Signal generation is the canonical sequential workflow: a Researcher
        agent proposes factors, a Strategist agent picks the most promising
        ones, a Trader agent emits orders. Each is a separate hash-locked
        AgentSpec; the workflow is a separate hash-locked WorkflowSpec.
        Behaviour change in any layer creates a new version row.
      </p>

      <h2 id="parallel">Parallel — independent research with synthesis</h2>
      <p>
        Run multiple agents concurrently against the same inputs, then fan-in
        to a synthesiser. Use it when the problem decomposes into independent
        subproblems and you want the latency of the slowest sub-agent, not
        the sum of all sub-agents.
      </p>
      <p>
        A canonical example: macro-bull researcher, macro-bear researcher,
        sector-specialist researcher all read the same news + earnings
        window, emit their independent take, and a portfolio-manager
        synthesiser composes the final stance. The fan-in latency profile
        often beats the equivalent sequential pipeline by 3-5x for the same
        token spend.
      </p>

      <h2 id="debate">Debate / Dialectical — adversarial analysis</h2>
      <p>
        Pair two agents with opposing roles (Bull researcher vs Bear
        researcher), let them exchange arguments over a configurable number
        of rounds, then have a Portfolio Manager synthesise a verdict. The
        literature behind this pattern (TradingAgents) is a known source of
        inspiration; AQP keeps the structure but routes through
        spec-driven AgentRuntime so every debate turn is logged.
      </p>
      <p>
        Each agent is a separate spec: <code>research.bull_researcher</code>,{" "}
        <code>research.bear_researcher</code>,{" "}
        <code>research.portfolio_manager</code>. The portfolio manager
        synthesises both transcripts into a single <em>debate verdict</em>{" "}
        with <code>action ∈ {"{buy, hold, sell, mutate_params}"}</code>. Debate
        is expensive (2-4x the token cost of a single agent) so use it for
        decisions where the cost of being wrong is much higher than the cost
        of the extra calls.
      </p>

      <h2 id="coordinator">Coordinator / Router — hierarchical delegation</h2>
      <p>
        One agent (the coordinator) looks at the task, picks the right
        specialist, and routes the request through the matching spec. Use it
        when you have a small set of specialised agents and want the request
        to hit the right one without the caller knowing the routing rules.
      </p>
      <p>
        A research-team workflow with coordinator routing might have:{" "}
        <code>universe.equity_specialist</code>,{" "}
        <code>universe.crypto_specialist</code>,{" "}
        <code>universe.commodity_specialist</code> — each with its own model,
        prompt, and tool set — and a <code>universe.coordinator</code> that
        dispatches based on the asset class in the request. The coordinator
        itself is just another AgentSpec; the routing is the prompt + a tool
        that emits the chosen specialist's name.
      </p>

      <h2 id="react">ReAct — loop with observation</h2>
      <p>
        The classic pattern from Yao et al. 2022. The agent reasons, takes a
        tool action, observes the result, and iterates until a stop
        condition. Use it for open-ended forecasting and research tasks where
        the trajectory is data-dependent.
      </p>
      <p>
        ReAct workflows need stop conditions or they spin forever. AQP enforces
        them via two layers: (1) the AgentSpec's <code>max_calls</code>{" "}
        guardrail caps the absolute number of LLM round-trips per run; (2) the
        WorkflowRuntime checks <code>should_halt</code> between every adapter
        transition so the topbar KillSwitch can interrupt a runaway ReAct
        loop in ~250ms.
      </p>

      <h2 id="compose">Compose any of the above</h2>
      <p>
        A real research workflow often combines patterns. The "alpha
        ideation" workflow in AQP is parallel at the top (three independent
        research streams) → debate in the middle (Bull vs Bear synthesis per
        stream) → coordinator at the bottom (which stream's verdict to act
        on, routed by current regime). The WorkflowSpec encodes the
        composition; the runtime handles the orchestration.
      </p>

      <div className="my-8">
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
      </div>

      <CodeBlock
        filename="workflow.yaml"
        language="yaml"
        code={`name: research.alpha_ideation
adapter: graph
params:
  # Parallel arm 1: macro-themed factor mining
  - id: macro_arm
    type: parallel
    branches:
      - sequential:
          - research.macro_bull_researcher
          - research.macro_bear_researcher
      - sequential:
          - research.sector_specialist
    sync: research.portfolio_manager_macro

  # Parallel arm 2: microstructure-themed factor mining
  - id: micro_arm
    type: parallel
    branches:
      - sequential:
          - research.flow_imbalance_specialist
          - research.regime_detector
      - sequential:
          - research.lob_researcher
    sync: research.portfolio_manager_micro

  # Coordinator decides which arm's verdict to act on
  - id: route
    type: coordinator
    agent: research.regime_router
    options:
      macro: macro_arm
      micro: micro_arm`}
      />

      <h2 id="failures">Failure modes you should plan for</h2>
      <p>
        Each pattern has a known failure mode. Plan for the failure when you
        pick the pattern:
      </p>
      <ul>
        <li>
          <strong>Sequential.</strong> Latency adds up. One slow agent
          blocks the whole pipeline. Cache aggressively at the boundary
          where the slow agent's input is content-addressable.
        </li>
        <li>
          <strong>Parallel.</strong> Synthesis is where good information goes
          to die. Spend most of your token budget on the synthesiser, not on
          the parallel arms.
        </li>
        <li>
          <strong>Debate.</strong> Adversarial agents converge to the same
          opinion if you let them see each other's chain-of-thought. Pass
          only the structured argument list, not the raw transcript.
        </li>
        <li>
          <strong>Coordinator.</strong> The coordinator becomes a single point
          of failure. Ship it with a sensible default route so a bad routing
          response still gets you to <em>some</em> specialist instead of
          erroring.
        </li>
        <li>
          <strong>ReAct.</strong> The loop spins forever. Always set{" "}
          <code>max_calls</code> in the AgentSpec; always have a tool that
          can emit a "done" sentinel; always test the workflow with the
          KillSwitch at least once before going live.
        </li>
      </ul>
      <p>
        Patterns are not personalities; they are shapes. Pick the shape that
        matches the problem, then hash-lock the spec and let the runtime do
        the boring parts.
      </p>
    </LearnArticleLayout>
  );
}
