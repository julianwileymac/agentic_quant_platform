import type { Metadata } from "next";
import {
  Box,
  Boxes,
  Cpu,
  Code2,
  Github,
  HardDrive,
  KeyRound,
  Network,
  Server,
  Settings,
  Sparkles,
  Terminal,
  Wrench,
} from "lucide-react";

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

export const metadata: Metadata = {
  title: "Self-Hosted",
  description:
    "Local-first AQP engine. Docker Compose, Kubernetes, or native dev. AQP IDE (Theia 1.72) included. Cluster-agnostic — runs on rpi k3s, EKS, AKS, GKE, vanilla k3s. TerraformRuntime + WorkloadRuntime for full IaC.",
};

export const dynamic = "force-static";
export const revalidate = 3600;

const NAV_ITEMS = [
  { id: "overview", label: "Overview" },
  { id: "deploy", label: "3 deploy modes" },
  { id: "ide", label: "AQP IDE" },
  { id: "cluster", label: "Cluster-agnostic" },
  { id: "iac", label: "TerraformRuntime" },
  { id: "cli", label: "aqp-cli" },
  { id: "faq", label: "FAQ" },
];

export default function SelfHostedPage() {
  return (
    <>
      <Hero
        eyebrow="Self-Hosted"
        eyebrowIcon={Server}
        title="Local-first. No alpha leaves the box."
        titleHighlight="No alpha leaves the box"
        subtitle="AQP is a local-first agentic platform. Every LLM call, every backtest, every reinforcement-learning rollout, and every piece of metadata stays on your hardware. Run it on Docker Compose, any Kubernetes cluster, or native dev — same engine."
        primaryCta={{
          label: "Clone on GitHub",
          href: "https://github.com/aqp-fund/aqp",
          external: true,
        }}
        secondaryCta={{ label: "Architecture docs", href: "/docs/architecture" }}
        illustration={
          <div
            className="rounded-xl p-6"
            style={{
              background: "var(--glass-bg)",
              border: "1px solid var(--glass-border)",
              backdropFilter: "blur(var(--glass-blur))",
            }}
          >
            <CodeBlock
              filename="terminal"
              language="bash"
              code={`# Bring the whole stack up.
$ docker compose up -d
[+] Running 14/14
 ✔ Container aqp-postgres   Started
 ✔ Container aqp-redis      Started
 ✔ Container aqp-iceberg    Started
 ✔ Container aqp-celery     Started
 ✔ Container aqp-api        Started
 ✔ Container aqp-client     Started

# Verify Iceberg persists across restarts.
$ docker exec aqp-api python -m scripts.iceberg_smoke --inspect-only
OK — 12 tables across 4 namespaces

# Open the operator UI on :3001
$ open http://localhost:3001`}
              copyable={false}
            />
          </div>
        }
      />

      <ProductNav items={NAV_ITEMS} />

      <StatStrip
        stats={[
          { value: 3, label: "Deploy modes", tone: "primary" },
          { value: 6, label: "IDE extensions", tone: "secondary" },
          { value: 5, label: "K8s clusters supported", tone: "tertiary" },
          { value: 5, label: "Terraform backends", tone: "warn" },
        ]}
      />

      {/* Overview */}
      <section id="overview" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="What you get"
            title="The full agentic quant stack on your own hardware"
            subtitle="Same engine as the cloud platform — minus the multi-tenant identity broker, plus the AQP IDE, plus TerraformRuntime for managing your own IaC."
          />
          <FeatureGrid columns={3}>
            <FeatureCard
              icon={HardDrive}
              tone="primary"
              title="Local-first by design"
              body="No proprietary alpha leaves the box. LLM calls route through your provider OR local Ollama / vLLM via router_complete."
            />
            <FeatureCard
              icon={Boxes}
              tone="secondary"
              title="Three deploy modes"
              body="Docker Compose (default, zero-config), Kubernetes (any cluster), or native uvicorn/celery for dev iteration."
            />
            <FeatureCard
              icon={Code2}
              tone="tertiary"
              title="AQP IDE included"
              body="White-labeled Theia 1.72 + six AQP compile-time extensions + MCP-driven research copilot + Perspective Arrow notebook renderer."
            />
            <FeatureCard
              icon={Network}
              tone="primary"
              title="Cluster-agnostic"
              body="Runs on rpi k3s, EKS, AKS, GKE, or vanilla k3s. AQP lives in its own aqp-* namespaces — no inbound dependency on rpi_kubernetes."
            />
            <FeatureCard
              icon={Settings}
              tone="warn"
              title="TerraformRuntime"
              body="Hash-locked terraform_stack_spec_versions + OPA policy gate. Auth0 / Entra / namespaces / RBAC / KMS — all as IaC."
            />
            <FeatureCard
              icon={Terminal}
              tone="secondary"
              title="aqp-cli operator tool"
              body="RFC 8628 device-flow auth + OS keyring. Subcommands for setup, start, stop, IDE launch, upgrade, secrets rotate."
            />
          </FeatureGrid>
        </div>
      </section>

      {/* 3 deploy modes */}
      <section
        id="deploy"
        className="px-6 py-20"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="3 deploy modes"
            title="Pick the right shape for your stage"
            subtitle="Default to Docker Compose for a single-machine quant lab; promote to Kubernetes when you outgrow it; iterate natively when you're hacking on the engine itself."
          />
          <div className="grid gap-6 lg:grid-cols-3">
            <MotionInView from="up" delay={0}>
              <DeployCard
                icon={Box}
                title="Docker Compose"
                tagline="Zero-config single machine"
                description="The default. Brings up Postgres, Redis, Iceberg, Celery, API, and the operator UI — and is enough to run the full agentic stack."
                code={`# Default profile (10-min boot)
docker compose up -d

# Visualization profile adds Trino + Polaris
# + Superset + Dagster + Dask + Ray
docker compose \\
  -f aqp_platform/compose/docker-compose.yml \\
  -f aqp_platform/compose/docker-compose.viz.yml \\
  --profile visualization up -d

# Full local-platform parity (adds Apicurio,
# real Airbyte, DataHub, Loki, VictoriaMetrics)
docker compose \\
  -f aqp_platform/compose/docker-compose.yml \\
  -f aqp_platform/compose/docker-compose.platform.yml \\
  --profile platform up -d`}
              />
            </MotionInView>
            <MotionInView from="up" delay={0.1}>
              <DeployCard
                icon={Network}
                title="Kubernetes"
                tagline="Any cluster, any cloud"
                description="Deploy into your own k3s / EKS / AKS / GKE / vanilla cluster. The aqp-* namespaces are self-contained — no Helm chart conflicts with your existing workloads."
                code={`# Apply the deployment kustomize bundle
make deploy-k8s ENV=prod

# Or via aqp-cli (uses your kubeconfig)
aqp-cli deploy --cluster prod-eks --env prod

# WorkloadRuntime exposes operations via
# the management API
curl -X POST \\
  https://manage.your-domain/manage/workloads/scale \\
  -H "Authorization: Bearer $TOKEN" \\
  -d '{"workload": "aqp-celery", "replicas": 8}'`}
              />
            </MotionInView>
            <MotionInView from="up" delay={0.2}>
              <DeployCard
                icon={Wrench}
                title="Native dev"
                tagline="Iterate on the engine itself"
                description="Run the API, Celery, and the operator UI as native processes on macOS / Linux / Windows. Hot-reload code, attach a debugger, instrument with OTEL."
                code={`# Postgres + Redis + Iceberg via compose
docker compose up -d postgres redis iceberg

# API on :8000 with hot-reload
uvicorn aqp.api.main:app --reload --port 8000

# Celery worker with concurrency=4
celery -A aqp.tasks.celery_app worker \\
  --concurrency 4 --loglevel info

# Operator UI on :3001
cd aqp_client && pnpm dev`}
              />
            </MotionInView>
          </div>
        </div>
      </section>

      {/* AQP IDE */}
      <section id="ide" className="px-6">
        <FeatureBreakdown
          eyebrow="AQP IDE"
          tone="secondary"
          title="A Theia IDE that knows your AQP repo."
          body="The AQP IDE is a white-labeled Eclipse Theia 1.72 distribution + six AQP compile-time extensions + an MCP-driven research copilot + a Perspective Arrow notebook renderer + spec/run inspectors. Canonical operator entrypoint is aqp-cli ide."
          bullets={[
            "aqp + aqp-shell + aqp-mcp-bridge + aqp-research-copilot + aqp-notebook-quant + aqp-quant extensions",
            "Copilot LLM calls go through router_complete (no vendor SDKs)",
            "MCP registrations carry per-MCP aud claim (RFC 8707)",
            "Perspective Arrow notebook renderer for inspecting RL trajectories + backtest results",
          ]}
          cta={{ label: "AQP IDE docs", href: "/docs/aqp-ide" }}
          reverse
          visual={
            <div
              className="rounded-xl p-6"
              style={{
                background: "var(--glass-bg-strong)",
                border: "1px solid var(--glass-border-strong)",
                backdropFilter: "blur(var(--glass-blur))",
              }}
            >
              <div
                className="text-xs font-bold uppercase tracking-wider"
                style={{ color: "var(--accent-secondary)" }}
              >
                Six bundled extensions
              </div>
              <ul className="mt-4 space-y-3">
                {IDE_EXTENSIONS.map((ext) => (
                  <li key={ext.name} className="flex items-start gap-3">
                    <Sparkles
                      size={14}
                      style={{
                        color: "var(--accent-secondary)",
                        marginTop: 4,
                        flexShrink: 0,
                      }}
                    />
                    <div>
                      <code
                        className="font-mono text-sm font-bold"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {ext.name}
                      </code>
                      <div
                        className="mt-1 text-xs leading-relaxed"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {ext.body}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
              <div
                className="mt-5 rounded p-3 text-xs"
                style={{
                  background: "rgba(167,139,250,0.08)",
                  border: "1px solid rgba(167,139,250,0.3)",
                  color: "var(--text-secondary)",
                }}
              >
                Launch with <code style={{ color: "#a78bfa" }}>aqp-cli ide</code>. Never
                imports agentic_quant_platform source — HTTP via{" "}
                <code style={{ color: "#a78bfa" }}>AqpApiService</code> + MCP only.
              </div>
            </div>
          }
        />
      </section>

      {/* Cluster-agnostic */}
      <section
        id="cluster"
        className="px-6 py-24"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Cluster-agnostic"
            title="Runs on five Kubernetes flavours out of the box"
            subtitle="The KubernetesAdapter ABC has four concrete adapters: NoneAdapter, RpiClusterAdapter, InClusterAdapter, LocalComposeAdapter. AQP sits in its own aqp-* namespaces with no inbound dependency on your existing workloads."
          />
          <FeatureGrid columns={5}>
            {CLUSTERS.map((c) => (
              <FeatureCard
                key={c.name}
                icon={c.icon}
                tone={c.tone}
                title={c.name}
                body={c.body}
              />
            ))}
          </FeatureGrid>
          <div
            className="mt-8 rounded-lg p-5 text-sm leading-relaxed"
            style={{
              background: "rgba(22,119,255,0.06)",
              border: "1px solid rgba(22,119,255,0.25)",
              color: "var(--text-primary)",
            }}
          >
            <strong style={{ color: "var(--accent-primary)" }}>
              No closed coupling.
            </strong>{" "}
            AQP runs inside its own aqp-* namespaces and uses a topology service
            (aqp_platform/configs/deployment/topology.yaml) to resolve every
            service URL. Want to run alongside an existing k3s cluster? Drop AQP
            in a side namespace — no conflicts, no Helm chart fights.
          </div>
        </div>
      </section>

      {/* TerraformRuntime */}
      <section id="iac" className="px-6">
        <FeatureBreakdown
          eyebrow="TerraformRuntime"
          tone="warn"
          title="Provisioning as a managed runtime."
          body="The TerraformRuntime is the 5th sibling spec-runtime. It is the only sanctioned executor for terraform plan/apply/destroy/refresh. Five state backends: local, s3, azurerm, gcs, HCP Terraform. OPA Rego policy gate on every plan; hard_mandatory=True attachments block apply on violation."
          bullets={[
            "terraform_stack_spec_versions hash-locked snapshots (just like agent / bot / RL specs)",
            "OPA policy gate fails plans that violate org policies",
            "Step-up MFA on /terraform/workspaces/*/apply, /destroy, /halt",
            "Templates: tenant-namespace bundle + Auth0 / Entra IaC + cluster setup",
          ]}
          cta={{ label: "TerraformRuntime docs", href: "/docs/terraform" }}
          visual={
            <CodeBlock
              filename="provision.py"
              language="python"
              code={`from aqp.terraform import TerraformRuntime, TerraformStackSpec

# Provision an Auth0 tenant + Entra app + RBAC bundle.
spec = TerraformStackSpec.from_yaml(
    "configs/terraform/tenant_bootstrap.yaml",
)

rt = TerraformRuntime(spec)

# Plan first — runs OPA Rego against your policies.
plan = rt.plan()
assert plan.policy_violations == []

# Apply with step-up MFA (RFC 9470).
# The user is prompted for fresh MFA before the apply runs.
run = rt.apply(workspace="prod-tenant-bootstrap")

# Audit row written BEFORE the apply executed.
print(run.spec_version_id, run.policy_check, run.exit_code)`}
            />
          }
        />
      </section>

      {/* aqp-cli */}
      <section
        id="cli"
        className="px-6"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <FeatureBreakdown
          eyebrow="aqp-cli"
          tone="tertiary"
          title="The operator CLI for self-hosted clusters."
          body="aqp-cli authenticates via RFC 8628 Device Authorization Grant + OS keyring (macOS Keychain / Windows Credential Locker / Linux Secret Service). HTTP-only against the control plane — never imports aqp.*."
          bullets={[
            "aqp-cli auth login --device (default; honours slow_down / authorization_pending)",
            "aqp-cli setup — first-time stack bootstrap with detect / fetch / configure",
            "aqp-cli ide — launch the AQP IDE attached to the current cluster",
            "aqp-cli workload {start,stop,scale,restart,exec,logs,apply-config,rotate-secret}",
          ]}
          cta={{ label: "aqp-cli docs", href: "/docs/aqp-cli" }}
          reverse
          visual={
            <CodeBlock
              filename="terminal"
              language="bash"
              code={`# First-time auth (Device Authorization Grant)
$ aqp-cli auth login --device
Visit https://app.aqp.fund/device and enter: WXYZ-1234
Waiting...
✔ Authenticated as you@example.com
Token stored in macOS Keychain (service: aqp-cli)

# Bootstrap the local platform
$ aqp-cli setup
Detecting docker compose...    ✔
Fetching latest images...       ✔
Configuring topology.yaml...    ✔
Starting compose stack...       ✔
Stack ready at http://localhost:3001

# Open the AQP IDE attached to this cluster
$ aqp-cli ide

# Scale the Celery worker pool
$ aqp-cli workload scale aqp-celery --replicas 8
✔ Scaled (audit_id=wf_run_8f3a2c)`}
              copyable={false}
            />
          }
        />
      </section>

      {/* Open source / community */}
      <section className="px-6 py-24">
        <div className="mx-auto max-w-3xl text-center">
          <MotionInView from="up">
            <div
              className="mb-6 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider"
              style={{
                borderColor: "var(--border-default)",
                color: "var(--accent-primary)",
                background: "var(--glass-bg)",
              }}
            >
              <Github size={12} />
              Open source · Fair-use license
            </div>
            <h2
              className="text-3xl font-bold tracking-tight md:text-4xl"
              style={{ color: "var(--text-primary)" }}
            >
              The AQP engine is source-available.
            </h2>
            <p
              className="mt-4 text-base leading-relaxed"
              style={{ color: "var(--text-secondary)" }}
            >
              Self-hosting is the original mode. The cloud platform is the same
              engine plus managed identity, tenancy, and edge. Both code paths
              ship from the same source tree — no closed-source backend.
            </p>
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <a
                href="https://github.com/aqp-fund/aqp"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-md px-6 py-3 text-sm font-semibold"
                style={{
                  background: "var(--accent-primary)",
                  color: "white",
                  boxShadow: "var(--shadow-glow-primary)",
                }}
              >
                <Github size={14} />
                Clone on GitHub
              </a>
              <a
                href="/docs/contributing"
                className="rounded-md border px-6 py-3 text-sm font-semibold"
                style={{
                  borderColor: "var(--border-default)",
                  color: "var(--text-primary)",
                }}
              >
                Contributing guide
              </a>
            </div>
          </MotionInView>
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
            title="Self-hosted questions"
          />
          <FaqAccordion items={FAQ_ITEMS} />
        </div>
      </section>

      <CallToActionBlock
        eyebrow="Ready to run it yourself"
        title="docker compose up -d. That's the whole thing."
        subtitle="Self-host the AQP engine on your own hardware. Bring your own LLM provider (or run Ollama / vLLM locally). Your alpha never leaves your box."
        primaryCta={{
          label: "Clone on GitHub",
          href: "https://github.com/aqp-fund/aqp",
          external: true,
        }}
        secondaryCta={{ label: "Architecture overview", href: "/docs/architecture" }}
      />
    </>
  );
}

function DeployCard({
  icon: Icon,
  title,
  tagline,
  description,
  code,
}: {
  icon: React.ComponentType<{ size?: number; color?: string }>;
  title: string;
  tagline: string;
  description: string;
  code: string;
}) {
  return (
    <div
      className="flex h-full flex-col rounded-xl p-6"
      style={{
        background: "var(--glass-bg)",
        border: "1px solid var(--glass-border)",
        backdropFilter: "blur(var(--glass-blur))",
      }}
    >
      <div className="flex items-center gap-3">
        <span
          className="inline-flex h-10 w-10 items-center justify-center rounded-lg"
          style={{
            background: "var(--gradient-hero)",
            boxShadow: "var(--shadow-glow-primary)",
          }}
        >
          <Icon size={18} color="white" />
        </span>
        <div>
          <div
            className="text-lg font-bold"
            style={{ color: "var(--text-primary)" }}
          >
            {title}
          </div>
          <div className="text-xs" style={{ color: "var(--accent-primary)" }}>
            {tagline}
          </div>
        </div>
      </div>
      <p
        className="mt-3 text-sm leading-relaxed"
        style={{ color: "var(--text-secondary)" }}
      >
        {description}
      </p>
      <div className="mt-4 flex-1">
        <CodeBlock code={code} language="bash" copyable={false} />
      </div>
    </div>
  );
}

const IDE_EXTENSIONS = [
  { name: "aqp", body: "Core Theia commands + workspace orchestration for AQP repos" },
  { name: "aqp-shell", body: "AQP-flavoured terminal with pre-configured env vars + service endpoints" },
  { name: "aqp-mcp-bridge", body: "Discovers + registers MCP servers (data, codebase, custom) in the IDE" },
  { name: "aqp-research-copilot", body: "Chat-style copilot routed through router_complete + AgentRuntime" },
  { name: "aqp-notebook-quant", body: "Perspective Arrow notebook renderer for RL trajectories + backtest results" },
  { name: "aqp-quant", body: "Spec inspectors + run viewers + drag-and-drop strategy authoring widgets" },
];

const CLUSTERS = [
  { name: "rpi k3s", icon: Cpu, tone: "primary" as const, body: "The reference rpi-cluster deployment" },
  { name: "EKS", icon: Server, tone: "secondary" as const, body: "Amazon EKS with IAM roles for service accounts" },
  { name: "AKS", icon: Server, tone: "tertiary" as const, body: "Azure Kubernetes Service with Entra federation" },
  { name: "GKE", icon: Server, tone: "warn" as const, body: "Google Kubernetes Engine with Workload Identity" },
  { name: "vanilla k3s", icon: Cpu, tone: "primary" as const, body: "Any conforming Kubernetes cluster" },
];

const FAQ_ITEMS = [
  {
    question: "Is self-hosting really free?",
    answer:
      "The AQP engine is source-available under a fair-use license: you can run it on your own hardware for internal commercial use without payment. The cloud platform is a separate paid tier that adds managed identity, multi-tenant tenancy, Cloudflare edge, audit retention, and support SLAs.",
  },
  {
    question: "Can I run AQP entirely offline?",
    answer:
      "Yes. Set router_complete to use local Ollama / vLLM endpoints and disable any provider that requires external API access. The HierarchicalRAG pipeline, the backtest engines, the RL Lab, and the operator UI all work without internet access.",
  },
  {
    question: "Do I need Kubernetes to run AQP?",
    answer:
      "No. Docker Compose is the default and is enough for a single-machine quant lab. Kubernetes is the recommended path when you outgrow a single host — typically when concurrent Celery workers, dedicated GPU nodes for RL / ML, or multi-region setups become relevant.",
  },
  {
    question: "How do I manage upgrades?",
    answer:
      "The aqp-cli upgrade subcommand pulls new images, runs migrations (alembic upgrade head), and re-applies any TerraformRuntime stacks. Migrations are immutable once committed (AGENTS rule 6), so upgrades are always forward-additive — a defective shipped migration is fixed by adding a new follow-up migration, never by editing the original.",
  },
  {
    question: "Can self-hosted talk to my company's existing identity provider?",
    answer:
      "Yes. The IdentityProvider chain supports generic OIDC (any RFC-compliant IdP), Cloudflare Access for zero-trust internal users, and direct Microsoft Entra ID via MSAL Node. Configure via Settings; existing org provisioning hooks (EntraTenantLink) work the same way as on the cloud platform.",
  },
];
