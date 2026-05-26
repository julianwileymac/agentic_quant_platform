import type { Metadata } from "next";

import { AgentFlowDiagram } from "@/components/marketing/illustrations/AgentFlowDiagram";
import { CodeBlock } from "@/components/marketing/CodeBlock";
import { LearnArticleLayout } from "@/components/marketing/LearnArticleLayout";

export const metadata: Metadata = {
  title: "AgentOps in finance",
  description:
    "Why agentic loops produce better alpha than monolithic scripts, and how hash-locked specs bridge the audit gap that financial systems demand.",
};

export const dynamic = "force-static";
export const revalidate = 86400;

export default function AgentOpsInFinancePage() {
  return (
    <LearnArticleLayout
      eyebrow="Agentic · 10 min read"
      title="AgentOps in finance"
      readMinutes={10}
      dateLine="Updated May 2026"
      toc={[
        { id: "the-problem", label: "The problem with monolithic scripts" },
        { id: "what-changes", label: "What agents change" },
        { id: "the-audit-gap", label: "The audit gap" },
        { id: "five-runtimes", label: "Five hash-locked runtimes", level: 3 },
        { id: "datamcp", label: "The DataMCP boundary" },
        { id: "guardrails", label: "Guardrails as code, not docs" },
        { id: "workflows", label: "Workflows compose patterns" },
        { id: "what-this-buys", label: "What this buys you" },
      ]}
      related={[
        {
          href: "/learn/multi-agent-patterns",
          title: "Five multi-agent patterns in production",
          category: "Agentic",
        },
        {
          href: "/learn/hash-locked-specs",
          title: "The case against self-modifying agents",
          category: "Agentic",
        },
        {
          href: "/product/agentops",
          title: "AgentOps product page",
          category: "Product",
        },
      ]}
      cta={{
        title: "Try AgentOps in AQP",
        body: "Author your first hash-locked AgentSpec and snapshot it in under five minutes on the free tier.",
        label: "Start free",
        href: "/signup",
      }}
    >
      <p
        className="rounded-lg p-4 text-base"
        style={{
          background: "rgba(22,119,255,0.06)",
          border: "1px solid rgba(22,119,255,0.25)",
          color: "var(--text-primary)",
        }}
      >
        <strong>TL;DR.</strong> Monolithic alpha scripts make every behaviour
        change a silent code edit. Agentic systems decouple <em>capability</em>{" "}
        (the spec) from <em>execution</em> (the runtime). AQP hash-locks the
        spec, ledger-tracks every run, and forbids the agent from touching the
        database directly — so you get audit-grade agents without giving up the
        flexibility of LLM-driven loops.
      </p>

      <h2 id="the-problem">The problem with monolithic scripts</h2>
      <p>
        Quant teams accumulate scripts. A factor library, a backtest harness, a
        portfolio constructor, a paper-trading loop, a few notebooks that
        re-run the whole thing on a Sunday. The trouble starts when the script
        changes. Did the Sharpe go up because the strategy got better, or
        because someone tightened a stop-loss threshold three commits ago?
        Whose code ran the position-sizing for the run that posted last week's
        +$X PnL?
      </p>
      <p>
        Most production quant systems answer those questions by{" "}
        <em>convention</em>: a tag on the git commit, a docstring on the
        config, an Excel sheet on the desk. None of those are enforceable; all
        of them drift; all of them collapse the first time a regulator asks
        "show me the exact code that produced this trade."
      </p>

      <h2 id="what-changes">What agents change</h2>
      <p>
        Agentic systems split the problem into two pieces: the{" "}
        <strong>spec</strong> (what the agent should do — model, prompt, tools,
        guardrails) and the <strong>runtime</strong> (how the spec is
        executed). The spec is a value; the runtime is the function. The same
        spec executed against the same data should always produce the same
        result. The same spec executed against new data should answer "would
        this strategy have worked last quarter?" without ambiguity.
      </p>
      <p>
        That separation is what makes agentic loops more auditable than
        monolithic scripts, not less. The script bundles capability and
        execution into one file you re-edit; the agent splits them and lets
        you snapshot the capability part.
      </p>

      <h2 id="the-audit-gap">The audit gap and how AQP bridges it</h2>
      <p>
        The "audit gap" is the distance between <em>what ran</em> and{" "}
        <em>what you can prove ran</em>. In a monolithic script world, you can
        prove the git commit ran; you can't prove the prompt template at that
        commit was the prompt that produced this LLM output. AQP closes the
        gap with three contracts:
      </p>
      <ul>
        <li>
          <strong>Hash-locked spec versions.</strong> The SHA-256 of the
          canonical-JSON spec is the version key. Same spec → same version.
          Any field change → a new immutable row in{" "}
          <code>agent_spec_versions</code>.
        </li>
        <li>
          <strong>Ledger-backed runs.</strong> Every run writes an{" "}
          <code>agent_runs_v2</code> row with the <code>spec_version_id</code>{" "}
          it executed against, the LLM cost, the latency, the findings, and
          any halt reason.
        </li>
        <li>
          <strong>Replay as a primitive.</strong>{" "}
          <code>AgentRuntime.replay(run_id)</code> re-executes the snapshotted
          version against new (or original) data. The replay is deterministic
          given the spec + data + provider.
        </li>
      </ul>

      <p>
        Behaviour changes always produce a <strong>new</strong> version row —
        never an in-place mutation. AQP deliberately rejects the
        "rewrite the skill on failure" pattern that some agentic libraries
        encourage. Why? Auditability (every behaviour change must be a new
        hash-locked version row, not a mutation); replay (runs reference{" "}
        <code>spec_version_id</code>; mutating the spec breaks the replay
        invariant); compliance (financial systems need an append-only audit
        trail); risk (a self-mutating spec next to live capital is a
        non-starter).
      </p>

      <h3 id="five-runtimes">Five hash-locked runtimes</h3>
      <p>
        AQP applies the same hash-lock + immutable + ledger-backed pattern
        across five different runtimes. The shape is consistent so once you've
        learned one, you've learned all five:
      </p>
      <ul>
        <li>
          <code>AgentSpec</code> / <code>AgentRuntime</code> — a single LLM
          agent with model, tools, prompt, guardrails.
        </li>
        <li>
          <code>BotSpec</code> / <code>BotRuntime</code> — the smallest
          deployable unit, aggregating universe + strategy + engine + ML +
          agents + RAG.
        </li>
        <li>
          <code>RLExperimentSpec</code> / <code>RLRuntime</code> —
          reinforcement-learning training, evaluation, paper, replay,
          walk-forward.
        </li>
        <li>
          <code>AnalysisSpec</code> / <code>AnalysisRuntime</code> — the
          55-flow analysis catalog (distribution, time series, portfolio,
          microstructure, …).
        </li>
        <li>
          <code>WorkflowSpec</code> / <code>WorkflowRuntime</code> —
          orchestrates the above through seven adapter kinds (graph, crew,
          debate, fusion, execution, schedule, studio).
        </li>
      </ul>

      <div className="my-8">
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
      </div>

      <h2 id="datamcp">The DataMCP boundary</h2>
      <p>
        The second contract that distinguishes audit-grade agents from
        free-form chatbots is the read boundary. AQP agents{" "}
        <strong>cannot import</strong>{" "}
        <code>aqp.persistence.models...</code> and{" "}
        <strong>cannot call</strong> <code>iceberg_catalog.append_arrow</code>.
        Every catalog / dataset / entity read from inside an agent body goes
        through a registered <code>DataMCPTool</code> — a typed RPC surface
        that you can reason about the same way you reason about a
        microservice's HTTP API.
      </p>
      <p>
        The bridge auto-installs every <code>DataMCPTool</code> into
        AgentRuntime's tool registry; the same catalog is exposed externally
        via FastAPI <code>/mcp/data</code> and an{" "}
        <code>aqp-data-mcp</code> stdio binary that any third-party agent
        client can connect to. Both are RFC 9728 + RFC 8707 conformant — every
        tool carries an audience claim and the server validates inbound
        tokens against it.
      </p>

      <h2 id="guardrails">Guardrails as code, not docs</h2>
      <p>
        The <code>AgentSpec.guardrails</code> field is parsed by{" "}
        <code>AgentRuntime._guardrail_check</code>. Violations raise{" "}
        <code>GuardrailViolation</code> <strong>before</strong> the next LLM
        call — not as a runtime warning, not as a metric you discover after
        the fact. The supported guardrails are:
      </p>
      <ul>
        <li>
          <code>cost_budget_usd</code> — hard ceiling per run, enforced via
          the token catalog.
        </li>
        <li>
          <code>rate_limit_per_minute</code> — per-spec rate limit honoured
          across concurrent runs.
        </li>
        <li>
          <code>max_calls</code> — caps the number of LLM round-trips per run.
          Stops ReAct loops from spinning forever.
        </li>
        <li>
          <code>forbidden_terms</code> — substring blacklist applied to LLM
          output. Use it to keep agents off PII, account numbers, or anything
          else you can string-match.
        </li>
        <li>
          <code>require_rationale</code> — forces the agent to emit a
          structured rationale alongside the result.
        </li>
        <li>
          <code>min_confidence</code> — minimum self-reported confidence floor.
          Runs below the floor are flagged for review, not silently dropped.
        </li>
      </ul>

      <CodeBlock
        filename="agent_spec.yaml"
        language="yaml"
        code={`name: research.alpha_researcher
model: claude-4-sonnet
prompt_template: |
  Find 3 momentum factors over {universe}. For each factor,
  give: name, formula (in the symbolic DSL), expected Sharpe,
  failure modes.
tools:
  - data.bars.fetch
  - data.indicators.compute
  - data.research_papers.search
guardrails:
  cost_budget_usd: 5.0
  max_calls: 20
  rate_limit_per_minute: 60
  require_rationale: true
  min_confidence: 0.55
  forbidden_terms:
    - "social security"
    - "account number"`}
      />

      <h2 id="workflows">Workflows compose patterns</h2>
      <p>
        A single agent is rarely the right shape for a real problem. AQP's
        Workflow Studio composes agents into pipelines via five canonical
        patterns: <strong>sequential</strong> (linear pipeline),{" "}
        <strong>parallel</strong> (independent multi-source research with
        synthesis), <strong>debate</strong> (Bull / Bear / Portfolio Manager
        synthesise a verdict), <strong>coordinator</strong> (hierarchical
        delegation), and <strong>ReAct</strong> (loop-with-observation). A
        WorkflowSpec is itself hash-locked — same workflow, same version,
        replayable run.
      </p>
      <p>
        The runtime checks for halt signals between every adapter transition
        (~250ms global stop via the topbar KillSwitch), writes a{" "}
        <code>workflow_runs</code> ledger row, attaches per-adapter OTEL
        spans, and emits canonical WebSocket progress frames. Inner agent
        calls write their own <code>agent_runs_v2</code> rows, with{" "}
        <code>experiment_id</code> + <code>test_id</code> FKs propagated for
        cross-flow attribution.
      </p>

      <h2 id="what-this-buys">What this buys you</h2>
      <p>
        AgentOps in finance isn't about "wow, the LLM came up with an alpha."
        It's about being able to answer four questions on demand:
      </p>
      <ul>
        <li>
          <strong>What ran?</strong> The exact spec version, by SHA-256.
        </li>
        <li>
          <strong>What did it cost?</strong> The exact USD per run, ledger row
          included.
        </li>
        <li>
          <strong>What would it have done?</strong> Replay the snapshotted
          version against any historical window.
        </li>
        <li>
          <strong>Why did it stop?</strong> The halt reason on the run row —
          guardrail violation, kill-switch fan-out, or natural completion.
        </li>
      </ul>
      <p>
        The agentic loop is the substrate. The hash-locked spec, the typed
        runtime, the DataMCP boundary, and the audit-first ledger are what
        make it production-grade for finance.
      </p>
    </LearnArticleLayout>
  );
}
