---
name: aqp-management-engine
description: Direct-control workflows for the AQP Management Engine — start / stop / scale / restart / exec / log workloads via `WorkloadRuntime`; manage Cloudflare tunnels, DNS records, and Access apps; rotate Auth0 + Entra secrets; promote Entra tenant links; halt every long-running runtime. Use when the user asks to bring a service up or down, run a debug command in a pod, tail a log slice for reasoning, provision a public endpoint behind Cloudflare Zero Trust, onboard a new Entra tenant, or stop the platform. Disabled for ambient invocation — load explicitly when the `aqp-management-engine` subagent is invoked.
disable-model-invocation: true
---

# AQP Management Engine workflows

This skill is the procedural companion to
`.cursor/agents/aqp-management-engine.md`. It lists the named
operations the subagent should reach for first, in the order they
typically chain in real operator sessions.

## Prerequisites

Every workflow assumes:

- The user is authenticated through one of the registered
  `IdentityProvider` instances (Auth0 / Entra MSAL / Cloudflare
  Access / Mock).
- The active control plane is reachable — either the in-monolith
  `/manage/*` proxy (`AQP_MANAGEMENT_MODE=embedded`) or the
  sidecar `aqp_control_plane` service
  (`AQP_MANAGEMENT_MODE=sidecar`).
- The required scope is granted on the user's JWT — see the
  per-workflow scope rows below.

## Workflow: start-service

Required scope: `manage:agents`.

Steps:

1. Call `data.workloads.list` to confirm the service is currently
   stopped (or unknown) — do NOT call `start` against a running
   service; the runtime is idempotent but auditing duplicates
   pollutes the `workload_runs` ledger.
2. If the deployment spec already exists on the provider (K8s
   Deployment is present, just scaled to 0), call
   `data.workloads.scale` with `replicas=1`. Otherwise call
   `data.workloads.start` with the full `DeploymentSpec` (image,
   env, ports, resources).
3. Poll `data.workloads.status` until
   `replicas_ready == replicas_desired` or 60 s elapsed; surface
   the `conditions` array on failure.

## Workflow: stop-service

Required scope: `manage:agents`. Friction-gate: the SPA uses
`ConfirmFrictionDialog` (`STOP`); the subagent equivalent is to
state the consequence ("scales to zero, in-flight traffic may
drop") and wait for explicit user confirmation BEFORE calling
`data.workloads.stop`.

## Workflow: restart-service

Required scope: `manage:agents`. Use
`data.workloads.restart` — the runtime bumps the
`aqp.internal/restarted-at` annotation (K8s) or runs `docker
compose restart` (compose). NEVER chain stop + start as a
"restart" — that creates two `workload_runs` rows where one is
sufficient and races against the user pressing the halt button
between calls.

## Workflow: exec-debug-command

Required scope: `cluster:exec`. Strict guardrails:

1. The `command` argv list MUST be quoted argv, not a shell
   string. Do not pass `"/bin/sh -c 'rm -rf …'"` as a single
   element.
2. Default `timeout_seconds` to 30 unless the user explicitly
   asks for longer.
3. NEVER pass `stdin_b64` carrying secret material — base64
   does not hide the value. If the command needs a secret, write
   it to a Kubernetes Secret first via the rotate-secret
   workflow.
4. Surface ONLY the `stdout` and `stderr` strings + `returncode`
   to the user. Never log the `command` array if it embeds a
   token.

## Workflow: tail-logs

Required scope: `cluster:read`. For reasoning, call
`data.kubernetes.stream_pod_logs` with bounded `tail_lines` and
`max_lines` (default 200). For live operator viewing, hand the
user the WebSocket URL `/cluster/pods/{ns}/{name}/logs/stream`
— the subagent should NOT keep that socket open itself.

## Workflow: provision-cloudflare-tunnel

Required scope: `cluster:admin`. Two paths:

1. **Quick (runtime adapter)** — single tunnel for a new
   hostname. Call:
   - `data.cloudflare.create_tunnel` (returns tunnel id)
   - `data.cloudflare.put_tunnel_config` with the ingress rules
     (the adapter appends the required `http_status:404`
     catch-all)
   - `data.cloudflare.put_dns_record` to point the public name
     at `<tunnel-id>.cfargotunnel.com` (`type=CNAME`, `proxied=true`)
   - Optionally `data.cloudflare.put_access_app` to require
     Cloudflare Access on the hostname.
2. **Durable (IaC)** — preferred for production. Render the
   `cloudflare_edge` Jinja template via the TerraformRuntime
   path (`data.terraform.plan_stack` ->
   `data.terraform.apply_stack`) so the tunnel + DNS + Access
   app live in an immutable `terraform_stack_spec_versions` row.

## Workflow: rotate-auth0-secret

Required scope: `manage:infrastructure`. Auth0 Management API
rotation is operator-driven; the subagent walks the user through:

1. Confirm the target Auth0 application id and the calling
   M2M token has `update:client_keys`.
2. Call `data.workloads.rotate_secret` with the
   `auth0_management_api` backend identifier — the runtime calls
   the Auth0 Management API on behalf of the user; the new
   client_secret NEVER leaves the AQP backend.
3. Trigger a rolling restart of every service that uses the old
   secret via `data.workloads.restart`.
4. Audit the rotation through `data.tenancy.audit` (the
   `SecurityAuditEvent` writer; never write raw secrets).

## Workflow: promote-entra-link

Required scope: `tenancy:admin`. Routes through
`POST /tenancy/entra-links/{id}/promote` (Phase E). Payload:

```json
{
  "organization_id": "...",
  "default_role": "viewer | editor | admin | owner",
  "role_mapping": { "_default": "viewer" },
  "allowed_email_domains": ["example.com"]
}
```

The subagent should:

1. Call `data.tenancy.list_entra_links` filtered to `status=pending`
   to enumerate candidates.
2. Confirm the target organization id (an EntityPicker on the
   frontend; the subagent equivalent is `data.tenancy.list_organizations`).
3. POST the promote payload, then surface the resulting
   `EntraTenantLink` row so the operator sees the new status.

## Workflow: halt-all

Required scope: `admin:cluster`. The user-facing path is the
`KillSwitch` topbar component (frontend); the subagent equivalent
fans out POSTs in parallel to:

- `/agents/halt`
- `/quant-agents/halt`
- `/paper/stop-all`
- `/bots/halt-all`
- `/rl/halt-all`
- `/workflows/halt`
- `/assistants/halt`
- `/terraform/halt`
- `/workloads/halt`  (Phase B of `aqp_management_engine`)

The subagent must NOT skip any endpoint just because the matching
runtime is not currently active — every endpoint is idempotent
(404/503 is "nothing to halt") so the aggregate envelope is the
operator's only chance to spot a partial failure.

## Credentials reminder

The companion rule (`.cursor/rules/aqp-management-engine.mdc`)
forbids ever printing token material in transcripts. Every
workflow above returns enough metadata for the operator to verify
success without ever surfacing the underlying secret value.
