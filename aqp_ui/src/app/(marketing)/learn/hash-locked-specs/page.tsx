import type { Metadata } from "next";

import { CodeBlock } from "@/components/marketing/CodeBlock";
import { LearnArticleLayout } from "@/components/marketing/LearnArticleLayout";

export const metadata: Metadata = {
  title: "Hash-locked specs",
  description:
    "Why AQP rejects self-modifying agents in financial systems and what it does instead: immutable snapshots, deterministic replay, append-only audit ledgers.",
};

export const dynamic = "force-static";
export const revalidate = 86400;

export default function HashLockedSpecsPage() {
  return (
    <LearnArticleLayout
      eyebrow="Agentic · 8 min read"
      title="Hash-locked specs: the case against self-modifying agents"
      readMinutes={8}
      dateLine="Updated May 2026"
      toc={[
        { id: "two-philosophies", label: "Two philosophies" },
        { id: "why-not-mutate", label: "Why not self-mutate?" },
        { id: "what-is-locked", label: "What is hash-locked?" },
        { id: "the-runtime-shape", label: "The runtime shape" },
        { id: "replay-as-primitive", label: "Replay as a primitive" },
        { id: "ledger-rows", label: "The ledger rows" },
        { id: "where-it-shows", label: "Where it shows up" },
      ]}
      related={[
        {
          href: "/learn/agentops-in-finance",
          title: "AgentOps in finance",
          category: "Agentic",
        },
        {
          href: "/learn/multi-agent-patterns",
          title: "Multi-agent patterns",
          category: "Agentic",
        },
        {
          href: "/product/agentops",
          title: "AgentOps product page",
          category: "Product",
        },
      ]}
      cta={{
        title: "See it in action",
        body: "Author an AgentSpec, snapshot it, mutate a field, and watch a new version row appear — all in under a minute.",
        label: "Start free",
        href: "/signup",
      }}
    >
      <p
        className="rounded-lg p-4 text-base"
        style={{
          background: "rgba(96,165,250,0.06)",
          border: "1px solid rgba(96,165,250,0.3)",
          color: "var(--text-primary)",
        }}
      >
        <strong>TL;DR.</strong> Self-modifying agents — where the agent
        rewrites its own prompt or skill on failure — are a popular pattern
        in research libraries. They are a non-starter in finance because they
        break four things at once: auditability, replay, compliance, and
        risk. AQP locks specs by SHA-256, snapshots them on first use, and
        makes every behaviour change a new immutable version row.
      </p>

      <h2 id="two-philosophies">Two philosophies of agentic state</h2>
      <p>
        The agentic-coder literature splits into two camps. The first treats
        the agent's prompt / skill / tool list as <em>mutable</em>: the
        agent rewrites it on failure, the next run uses the new version, and
        the system "learns." Many open-source agent frameworks default to
        this — it's intuitive and demos well.
      </p>
      <p>
        The second camp treats agent definitions as <em>immutable values</em>:
        every behaviour change produces a new version, the old version stays
        addressable, and the agent never silently changes underneath you.
        This is the camp AQP joins, and the choice is deliberate.
      </p>

      <h2 id="why-not-mutate">Why AQP forbids self-mutation</h2>
      <p>
        Four reasons. Each is by itself sufficient to disqualify the
        mutable-state pattern from a financial system:
      </p>
      <ul>
        <li>
          <strong>Auditability.</strong> The whole point of a financial
          audit ledger is that every behaviour change is attributable. If
          the agent mutates its own prompt on failure, the new prompt is
          authored by no one identifiable; the audit trail dies at the
          moment it matters most.
        </li>
        <li>
          <strong>Replay.</strong> Replay-as-a-primitive only works if the
          spec is stable. If you call <code>AgentRuntime.replay(run_id)</code>{" "}
          and the spec has mutated since the original run, you cannot
          reproduce the original trajectory. Mutation breaks the replay
          invariant.
        </li>
        <li>
          <strong>Compliance.</strong> Financial systems are required to
          retain an append-only audit trail. "The agent rewrote itself" is
          not a defensible regulatory answer. Append-only ledgers + immutable
          spec versions are a defensible one.
        </li>
        <li>
          <strong>Risk.</strong> A self-mutating spec next to live capital
          can rewrite itself into an aggressive position-sizing rule in
          response to a string-matching prompt-injection. The mutable-state
          pattern doesn't even survive the threat-model conversation.
        </li>
      </ul>

      <h2 id="what-is-locked">What is hash-locked, exactly?</h2>
      <p>
        AQP serialises every spec to canonical JSON (sorted keys, stable
        numeric representation, no inline whitespace) and takes the SHA-256.
        That hash is the version key. The same content always produces the
        same hash; any field change produces a new hash.
      </p>
      <p>
        The fields covered include the obvious ones (model alias, prompt
        template, tool list, guardrails) and the non-obvious ones (default
        temperature, max tokens, output schema, semantic-cache TTL). The
        rule is: if changing it could change the output, it's part of the
        hash.
      </p>

      <CodeBlock
        filename="snapshot.py"
        language="python"
        code={`from aqp.agents import AgentSpec, persist_spec

spec = AgentSpec(
    name="alpha.researcher",
    model="claude-4-sonnet",
    prompt_template="Find 3 momentum factors over {universe}.",
    tools=["data.bars.fetch", "data.indicators.compute"],
    guardrails={
        "cost_budget_usd": 5.0,
        "max_calls": 20,
    },
)

# First call snapshots an immutable agent_spec_versions row.
v1 = persist_spec(spec)             # 9a4f...c1d3

# Same content → same version. Idempotent.
v1_again = persist_spec(spec)
assert v1 == v1_again

# Mutate any field, persist again → NEW version row.
spec.guardrails["cost_budget_usd"] = 10.0
v2 = persist_spec(spec)             # 2b18...77ea
assert v2 != v1

# v1 is still there and queryable for replay.`}
      />

      <h2 id="the-runtime-shape">The runtime shape</h2>
      <p>
        The Runtime is the only sanctioned executor for a spec. It enforces
        the guardrails, attaches the cost-tracking, writes the audit row,
        and emits the canonical WebSocket progress frames. AQP applies the
        same shape across five spec kinds: AgentSpec, BotSpec,
        RLExperimentSpec, AnalysisSpec, WorkflowSpec. All five share the
        hash-lock + immutable + ledger-backed semantics.
      </p>
      <p>
        Importantly, you never call the model directly from inside an agent
        body. You declare the model alias on the AgentSpec, and the runtime
        drives the call through the central LLM gateway (<code>router_complete</code>{" "}
        in AQP, AGENTS rule 2). That keeps cost tracking, provider failover,
        and semantic-cache decisions centralised.
      </p>

      <h2 id="replay-as-primitive">Replay as a first-class primitive</h2>
      <p>
        Because the spec is hash-locked, "what would this agent have done on
        last week's data?" is a deterministic question. You point{" "}
        <code>AgentRuntime.replay()</code> at the original run id and a new
        data window; the runtime loads the snapshotted spec version, replays
        against the new window, and writes a new run row that references the
        original spec version id.
      </p>
      <p>
        The same primitive works for backtests, RL experiments, analysis
        flows, and full workflows. "Show me last quarter's strategy applied
        to this quarter's data" stops being a code-archaeology exercise.
      </p>

      <h2 id="ledger-rows">The ledger rows</h2>
      <p>
        Every spec kind has a matching <code>*_runs</code> ledger table.
        AgentRuntime writes <code>agent_runs_v2</code>, BotRuntime writes{" "}
        <code>bot_deployments</code>, RLRuntime writes <code>rl_runs</code>,
        AnalysisRuntime writes <code>analysis_runs</code>, and WorkflowRuntime
        writes <code>workflow_runs</code>. Each row carries:
      </p>
      <ul>
        <li>
          The <code>spec_version_id</code> the run executed against.
        </li>
        <li>
          The user / org / workspace / project / lab / mode the run was
          authorised against (the <code>RequestContext</code>).
        </li>
        <li>
          Cost (USD), latency (ms), call count, halt reason (if any).
        </li>
        <li>
          The <code>experiment_id</code> + <code>test_id</code> umbrella FKs
          for cross-flow attribution (Phase 1 of the experiments + tests
          rollout).
        </li>
      </ul>

      <h2 id="where-it-shows">Where hash-locking shows up across AQP</h2>
      <p>
        Once you start looking for the pattern, you see it everywhere AQP
        ships a runtime. Bots have hash-locked <code>bot_versions</code>, RL
        experiments have hash-locked <code>rl_experiment_versions</code>,
        analysis flows have hash-locked <code>analysis_spec_versions</code>,
        workflows have hash-locked <code>workflow_spec_versions</code>, and
        Terraform stacks have hash-locked{" "}
        <code>terraform_stack_spec_versions</code>.
      </p>
      <p>
        The shape is intentional. Five different runtimes, one contract:
        immutable versions, append-only ledgers, replay-as-a-primitive. It
        is the contract that makes the agentic loop safe to deploy near
        live capital.
      </p>
    </LearnArticleLayout>
  );
}
