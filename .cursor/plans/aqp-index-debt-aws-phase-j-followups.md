# aqp-index debt — AWS Hybrid Phase J follow-ups

> Per the always-on
> [aqp-index-reflect rule](../rules/aqp-index-reflect.mdc), the
> Phase J cleanup (gaps the Phases A–I implementation left open)
> touches enough qualifying surfaces that `aqp_index/` MUST be
> refreshed by the
> [`aqp-index-curator`](../agents/aqp-index-curator.md) subagent in
> the same PR — OR a debt note (this file) must capture the changed
> surfaces so the curator's next scheduled pass picks them up.
>
> This note is option 2. Invoke the curator before merging if at all
> possible.
>
> Companion: [aqp-index-debt-aws-bedrock-deployment.md](aqp-index-debt-aws-bedrock-deployment.md)
> (the Phase A–I parent).

## Phase J item coverage

| Item | Status | Files touched |
| --- | --- | --- |
| J1 | landed | `infrastructure/modules/ecr-repositories/main.tf` (default repos += `aqp-agent`) |
| J2 | landed | `aqp/persistence/models_workloads.py` (`upsert_from_payload`); `aqp/api/routes/_internal_audit.py` (route uses it) |
| J3 | landed | NEW `aqp_control_plane/src/aqp_cp/auth/stepup.py`; `aqp_control_plane/src/aqp_cp/api/routers/terraform.py` adds `require_step_up` to apply/destroy/halt/halt_clear |
| J4 | landed | `aqp_control_plane/src/aqp_cp/providers/aws.py` (`_register_task_definition_from_spec`) |
| J5 | landed | `aqp_control_plane/src/aqp_cp/providers/aws.py` (`_exec_sync` AWS CLI path behind `AQP_AWS_ECS_EXEC_CAPTURE_OUTPUT`) |
| J6 | landed | `aqp_control_plane/src/aqp_cp/providers/aws.py` (`tail_logs` per-stream `nextForwardToken`) |
| J7 | landed | `aqp/agents/tools/bedrock_agentcore_gateway.py` (`_converge_gateway_targets`) |
| J8 | landed | `aqp/agents/agentcore_entrypoint.py` (FastAPI `create_app` + `/ping` + `/invocations`); `aqp_platform/build/docker/aqp-agent/Dockerfile` (port 8080, +api extra) |
| J9 | landed | NEW `infrastructure/modules/bedrock-kb-sync-lambda/` (module + Python handler); `aqp_platform/terraform/environments/live/main.tf` composes it |
| J10 | landed | NEW `scripts/render_nightly_sfn.py` |
| J11 | landed | NEW `aqp/config/aws_bootstrap.py`; `aqp/api/main.py` calls it from the lifespan |
| J12 | landed | NEW `infrastructure/policies/rego/{baseline,cost,README}.{rego,md}` |
| J13 | landed | NEW `infrastructure/modules/cloudwatch-alarms/`; `infrastructure/envs/minimum/main.tf` composes it |

## Surfaces the curator should refresh

| `aqp_index/` file | Why |
| --- | --- |
| `aqp_index/configs/deployment.md` | New SSM bootstrap helper changes the env-bootstrap path; mention `AQP_DEPLOY_TARGET=aws` flips the lifespan |
| `aqp_index/architecture/boundaries.md` | CP-side `require_step_up` is now the second step-up implementation (mirrors AQP side); note both must stay in sync |
| `aqp_index/code-index/modules.md` | New helpers: `_register_task_definition_from_spec`, `_converge_gateway_targets`, `hydrate_settings_from_ssm`, `_handle_envelope` (agentcore_entrypoint), `PostgresWorkloadAuditSink.upsert_from_payload`, KB-sync Lambda `handler.handler` |
| `aqp_index/projects/aqp_platform.md` | New `infrastructure/modules/{bedrock-kb-sync-lambda,cloudwatch-alarms}/`; `aqp_platform/build/docker/aqp-agent/Dockerfile` switched to port 8080 + api extra; SFN renderer at `scripts/render_nightly_sfn.py` |
| `aqp_index/projects/aqp_control_plane.md` | New `aqp_cp/auth/stepup.py`; `AwsProvider` now fully implements every mutating op surface |
| `aqp_index/config-sets/ci-workflows.md` | `terraform-pipeline.yml` `conftest` step references `infrastructure/policies/rego/` (now populated) |
| `aqp_index/sources-of-truth.md` | New SSM contract — `/aqp/${env}/*` is the source-of-truth handle for cross-tier wiring |

## Follow-ups (Phase K — not in this work)

These are now the smallest set of remaining items:

1. **Bedrock model access via Terraform** — the
   `aws_bedrock_invocation_logging_configuration` resource exists but
   model-access enablement remains console-only. AWS may ship
   `aws_bedrockcontrol_model_access` shortly; wire it then.
2. **Cell-tier IaC** for `cell-shared-prem-us-east-1a` +
   `cell-silo-reg-acme` — currently `state: provisioning` in topology.yaml.
   Needs per-cell EKS namespace + RLS database + cell router.
3. **`AwsProvider.exec` AWS CLI path** requires `session-manager-plugin`
   in the CP base image — the Chainguard image doesn't ship it.
   Either add it to the CP Dockerfile or wait for a pure boto3
   streaming API (AWS roadmap).
4. **CP terraform router workspace_id mismatch test** — the
   `model_copy(update=...)` chain assumes pydantic v2; add a test that
   confirms a mismatched body.spec.workspace_id rewrites correctly.
5. **HttpAuditSink test** — coverage for the `/_internal/audit/*`
   monolith ingest path with a mock M2M token.
6. **AgentCore entrypoint streaming** — `/invocations` currently
   returns a unary JSON response. AgentCore Runtime supports NDJSON
   streaming for partial outputs; wire `StreamingResponse` for the
   long-running spec types.

## Provenance

- Implemented as the Phase J cleanup follow-up to
  [aqp-index-debt-aws-bedrock-deployment.md](aqp-index-debt-aws-bedrock-deployment.md).
- Every surface listed above shows up in this PR's diff; the curator
  can scan it directly on its next pass.
