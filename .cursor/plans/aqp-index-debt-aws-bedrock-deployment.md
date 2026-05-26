# aqp-index debt — AWS Hybrid + Bedrock AgentCore deployment (Phases A-H)

> Per the always-on
> [aqp-index-reflect rule](../rules/aqp-index-reflect.mdc), the
> [aws_hybrid_bedrock_deployment plan](aws_hybrid_bedrock_deployment_f06bdd10.plan.md)
> touches enough qualifying surfaces that `aqp_index/` MUST be
> refreshed by the
> [`aqp-index-curator`](../agents/aqp-index-curator.md) subagent in
> the same PR — OR a debt note (this file) must capture the changed
> surfaces so the curator's next scheduled pass picks them up.
>
> This note is option 2. Invoke the curator before merging if at all
> possible.

## Phase coverage

| Phase | Status | Surfaces |
| --- | --- | --- |
| A | landed | CP TerraformRuntime completion |
| B | landed | AwsProvider mutating ops (ECS / SSM / CloudWatch / Secrets Manager) |
| C | landed | 8 new `infrastructure/modules/` + `deny_bedrock_api_keys` SCP |
| D | landed | Bedrock LLM provider entry in `router_complete` catalog |
| E | landed | AgentCore Gateway adapter + `agent_runs_v2` columns + `data.agentcore.*` MCP tools |
| F | landed | ARM64-only `aqp-agent` Dockerfile + ADOT exporter + ADOT sidecar manifest |
| G | landed | `environments/live` S3 backend wiring + topology hybrid declaration |
| H | landed | CI/CD matrix expansion + nightly Bedrock smoke + tests + runbook |
| I | this note | curator refresh |

## Surfaces changed

### `aqp_control_plane/`

- **`aqp_control_plane/src/aqp_cp/terraform/policy.py`** (NEW) — port
  of `aqp/terraform/policy.py` (OPA / Sentinel evaluator with optional
  binary).
- **`aqp_control_plane/src/aqp_cp/terraform/codegen/`** (NEW) — full
  port of the Jinja2 HCL codegen tree. Templates: `generic.tf.j2`,
  `agents_local.tf.j2`, `cloudflare_edge.tf.j2`, `faas_local.tf.j2`,
  `secrets_local.tf.j2`, `storage_aws.tf.j2`, `storage_azure.tf.j2`,
  `storage_gcp.tf.j2`, `storage_local.tf.j2`, PLUS two NEW templates
  `bedrock_agentcore.tf.j2` and `bedrock_kb_oss.tf.j2`.
- **`aqp_control_plane/src/aqp_cp/terraform/builders/manifests/`** (NEW)
  — Jinja2 tenant-namespace bundle replacing the deprecated CDKTF path.
  Renders K8s namespace + NetworkPolicy + IRSA role + Secrets Manager
  containers + per-tenant Cognito client.
- **`aqp_control_plane/src/aqp_cp/terraform/audit_sink.py`** (NEW) —
  `HttpTerraformAuditSink` posting `terraform_runs` rows to monolith
  `/_internal/audit/terraform-runs` via M2M Bearer.
- **`aqp_control_plane/src/aqp_cp/terraform/runtime.py`** — `__init__`
  gained an `audit_sink` kwarg; `execute` calls `start`/`finish` around
  every dispatch.
- **`aqp_control_plane/src/aqp_cp/providers/aws.py`** — full mutating
  ops (`start` / `stop` / `scale` / `restart` / `exec` / `tail_logs` /
  `rotate_secret` / `apply_config`) against ECS Fargate + SSM +
  CloudWatch Logs + Secrets Manager. Replaces the Phase-5 stub.

### `aqp/`

- **`aqp/api/routes/_internal_audit.py`** (NEW) — POST
  `/_internal/audit/{terraform-runs,workload-runs}` with M2M Bearer
  validation. Added to `PUBLIC_ROUTERS` allowlist as `internal-audit`.
- **`aqp/api/main.py`** — mounts the new internal audit router.
- **`aqp/api/security.py`** — `PUBLIC_ROUTERS` adds `internal-audit`.
- **`aqp/config/settings.py`** — new typed fields
  `terraform_use_control_plane: bool`,
  `terraform_audit_ingest_audience: str`, `bedrock_region`,
  `bedrock_guardrail_id`, `bedrock_guardrail_version`.
- **`aqp/llm/providers/catalog.py`** — appended `"bedrock"`
  `ProviderSpec` entry (`litellm_prefix="bedrock/"`).
- **`aqp/llm/providers/router.py`** — new `_bedrock_extra_kwargs`
  helper; routes Bedrock calls with `aws_region_name` +
  `guardrailConfig` injected.
- **`aqp/agents/runtime.py`** — `AgentRuntime.__init__` gained
  `agentcore_runtime_alias`; new `_run_via_agentcore` method;
  `_finalise` persists `agentcore_session_id` / `agentcore_runtime_arn`
  / `agentcore_memory_id` columns.
- **`aqp/agents/agentcore_entrypoint.py`** (NEW) — Bedrock AgentCore
  Runtime CMD shim. Reads envelope from stdin, dispatches into
  `AgentRuntime`, writes result to stdout.
- **`aqp/agents/tools/bedrock_agentcore_gateway.py`** (NEW) —
  `BedrockAgentCoreGatewayBridge` renders DataMCP catalog as AgentCore
  Gateway tool-config; optional S3 publish + SSM URI registration.
- **`aqp/data/mcp/tools/agentcore.py`** (NEW) — `data.agentcore.*` MCP
  tools (`list_runtimes`, `list_sessions`, `invoke`). Added to
  `aqp/data/mcp/tools/__init__.py` side-effect imports.
- **`aqp/persistence/models_agents.py`** — `AgentRunV2` gains the
  three AgentCore session columns; matching migration is
  `alembic/versions/0087_agentcore_session_columns.py`.
- **`aqp/observability/aws.py`** (NEW) — ADOT bootstrap helper. Sets
  AWS-flavoured resource attributes (`aws.local.service`,
  `cloud.platform=aws_ecs`, …) on the active TracerProvider and wires
  the X-Ray id generator when the AWS distro is installed.
- **`aqp/observability/__init__.py`** — re-exports
  `configure_aws_observability`.

### `infrastructure/`

- **8 new modules:**
  - `infrastructure/modules/bedrock-agentcore/`
  - `infrastructure/modules/bedrock-knowledge-base/`
  - `infrastructure/modules/opensearch-serverless/`
  - `infrastructure/modules/cognito-userpool/`
  - `infrastructure/modules/cloudfront/`
  - `infrastructure/modules/alb/`
  - `infrastructure/modules/ecs-fargate-control-plane/`
  - `infrastructure/modules/eventbridge-stepfunctions/`
- **`infrastructure/modules/landing-zone/main.tf`** — added
  `AqpDenyBedrockLongTermApiKeys` SCP (closes the Sonrai disclosure
  from blueprint §16.1 risk 7) plus the matching org attachment.

### `aqp_platform/`

- **`aqp_platform/terraform/environments/live/main.tf`** —
  rewritten to compose the 8 new modules + the heritage `aqp`
  composition; provider pinned to `hashicorp/aws ~> 6.21` for
  AgentCore.
- **`aqp_platform/terraform/environments/live/backend.tf`** — swapped
  from hardcoded bucket to partial S3 config (`backend "s3" {}`).
- **`aqp_platform/terraform/environments/live/backend.hcl.example`**
  (NEW) — operator template for the per-account init backend config.
- **`aqp_platform/configs/terraform/aws.yaml`** (NEW) —
  TerraformStackSpec describing the AWS hybrid stack. Slug
  `aqp-aws-live`, `prerendered_workspace_dir` semantics.
- **`aqp_platform/configs/deployment/topology.yaml`** — added the
  `aws` target (composed EKS + ECS Fargate + Bedrock surface) + 9
  new `services` entries (the 7 AWS-managed services + `alb` +
  `eventbridge-stepfunctions`) + flipped
  `cell-shared-std-us-east-1a` from `provisioning` to `active` bound
  to the new `aws` target.
- **`aqp_platform/build/docker/aqp-agent/Dockerfile`** (NEW) —
  ARM64-only Bedrock AgentCore Runtime image.
- **`aqp_platform/deployments/kubernetes/observability/adot-sidecar/`**
  (NEW) — ADOT sidecar `OpenTelemetryCollector` CR + matching IRSA
  ServiceAccount + kustomization.

### `.github/workflows/`

- **`.github/workflows/build-publish.yml`** — matrix converted from a
  flat list to `include:` so each service can declare its own
  `platforms`. `aqp-agent` ships `linux/arm64` only.
- **`.github/workflows/terraform-pipeline.yml`** — extended trigger
  paths to cover `aqp_platform/terraform/**` +
  `aqp_platform/configs/terraform/**`. Plan matrix now covers BOTH
  the `infrastructure/envs/dev` AND
  `aqp_platform/terraform/environments/live` trees. Dispatch inputs
  added `tree` (infrastructure / aqp_platform) + extended `env`
  options to include `paper` + `live`.
- **`.github/workflows/bedrock-smoke.yml`** (NEW) — nightly + dispatch
  smoke that invokes the dev AgentCore runtime + verifies an X-Ray
  trace shows up. Account id segments redacted in logs.

### `alembic/versions/`

- **`alembic/versions/0087_agentcore_session_columns.py`** (NEW) —
  adds `agentcore_session_id` + `agentcore_runtime_arn` +
  `agentcore_memory_id` columns to `agent_runs_v2`. Hash recorded in
  `.hashes.lock`.

### `aqp_docs/`

- **`aqp_docs/docs/how-to/operations/aws-deploy.md`** (NEW) —
  end-to-end deploy runbook covering bootstrap + landing zone +
  application IaC + image builds + seed secrets + smoke.
- **`aqp_docs/docs/how-to/operations/aws-runbook.md`** (NEW) — on-call
  playbook: kill switch fan-out, AgentCore session halt, ECS service
  recovery, Celery drain, break-glass assumption, Cloudflare origin
  secret rotation, common failure modes.

### `tests/`

- **`tests/terraform/test_cp_terraform_router.py`** (NEW) — CP
  TerraformRuntime + audit-sink + kill-switch smoke.
- **`tests/providers/test_aws_provider_mutating.py`** (NEW) — moto
  tests for `AwsProvider.{scale, restart, apply_config,
  rotate_secret}`.
- **`tests/llm/test_bedrock_provider.py`** (NEW) — Bedrock provider
  registration + extra-kwargs injection.
- **`tests/agents/test_agentcore_gateway.py`** (NEW) — Gateway bridge
  render + filter + stable catalog hash.

## Files the curator should refresh

The qualifying surfaces above map to these `aqp_index/` files (per
the curator's scan plan):

| `aqp_index/` file | Why it needs a refresh |
| --- | --- |
| `aqp_index/configs/deployment.md` | New `aws` target; 9 new `services`; cell-shared-std-us-east-1a flipped to active |
| `aqp_index/architecture/boundaries.md` | EKS Karpenter ↔ ECS Fargate boundary; AgentCore as a delegated dispatch target |
| `aqp_index/code-index/modules.md` | New `BedrockAgentCoreGatewayBridge` signature, new `AwsProvider.{start,stop,scale,restart,exec,tail_logs,rotate_secret,apply_config}` impls, new `data.agentcore.*` MCP tools, new `aqp/observability/aws.py` |
| `aqp_index/sources-of-truth.md` | New `aqp_platform/terraform/environments/live/backend.hcl.example` template; `infrastructure/modules/landing-zone/main.tf` deny-bedrock-api-keys SCP |
| `aqp_index/config-sets/ci-workflows.md` | `build-publish.yml` matrix expansion, new `bedrock-smoke.yml`, expanded `terraform-pipeline.yml` matrix |
| `aqp_index/projects/aqp_platform.md` | `environments/live/` rewired; new `aqp-agent` ARM64 Dockerfile; new `observability/adot-sidecar/` overlay |
| `aqp_index/projects/aqp_control_plane.md` | CP terraform/ filled out: policy + codegen + builders + audit_sink |
| `aqp_index/projects/aqp_docs.md` | New runbooks at how-to/operations/aws-{deploy,runbook}.md |
| `aqp_index/skills/aqp-control-plane-provider.md` | AwsProvider stub-to-real upgrade reference |

## Follow-ups

Not in this PR but the curator should flag them:

1. **Bedrock model access enablement is still console-only.** AWS has
   no Terraform resource for model-access yet; document captures the
   manual step.
2. **`AwsProvider.start` requires `spec.metadata['task_definition']`**
   — operators register the task def out-of-band today. A future
   enhancement could auto-create one from a `DeploymentSpec`.
3. **AgentCore Gateway `update_gateway` call** is parked behind a
   TODO inside `BedrockAgentCoreGatewayBridge.publish_to_gateway`.
   The current shape uploads the tool-config JSON to S3 + records
   the URI in SSM; the gateway picks it up on its next poll. When
   the AWS SDK shape for `update_gateway` stabilises we can wire
   the direct call.
4. **moto coverage gap** — `AwsProvider.tail_logs` is not yet covered
   because moto doesn't faithfully stub `describe_log_streams` paging.
5. **Phase 4 — Cell-tier IaC** for the multi-tenant cells is still
   pending (mentioned as Phase 4 of the larger blueprint roadmap).

## Provenance

- Implemented per the
  [aws_hybrid_bedrock_deployment plan](aws_hybrid_bedrock_deployment_f06bdd10.plan.md).
- Every surface listed above shows up in this PR's diff; the curator
  can scan the diff directly on its next pass.
