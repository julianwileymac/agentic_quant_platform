---
title: SPIFFE workload identity
description: Phase 4 §7.2 — SPIFFE / SPIRE workload identity for AQP service-to-service authentication.
sidebar_label: SPIFFE workload identity
---

# SPIFFE workload identity

> Phase 4 §7.2 of
> [RESTRUCTURING_PLAN.md](https://github.com/julianwiley/agentic_quant_platform/blob/main/RESTRUCTURING_PLAN.md).
> SPIFFE-bound identities replace the long-lived OAuth
> client-credentials grant currently used by `M2MTokenIssuer` for
> service-to-service authentication.

## Why workload identity

The pre-Phase-4 ``M2MTokenIssuer`` mints short-lived JWTs via the
Auth0 / Entra ``client_credentials`` grant, but those tokens are
still bearer credentials — exfiltrate the JWT and you can replay it
from anywhere until it expires. SPIFFE-bound identities (SVIDs) are
workload-attested via the platform (UID, cgroup, label selectors) —
much harder to steal and automatically rotated by the SPIRE Server.

| Aspect | OAuth `client_credentials` | SPIFFE JWT-SVID |
| --- | --- | --- |
| Issuer | Auth0 / Entra tenant | SPIRE Server (in-cluster) |
| Attestation | Shared `client_secret` (long-lived) | Node + workload attestor (live) |
| Bearer-token replay risk | High (until expiry) | Low (selectors validated by Workload API) |
| Rotation | Manual / scheduled | Automatic, per-SVID-lifetime |
| Cross-cell scope | Implicit (issuer trusts all audiences) | Explicit (`spiffe://aqp.fund/cell/<id>/...` trust-domain path) |

## Trust domain layout

AQP runs ONE trust domain — ``aqp.fund``. Each cell carries a
namespace-scoped trust-domain prefix:

```
spiffe://aqp.fund/cell/<cell-id>/<service-account-name>
```

Example SPIFFE IDs:

| Cell | Service | SPIFFE ID |
| --- | --- | --- |
| `cell-shared-std-local` | `aqp-core` | `spiffe://aqp.fund/cell/cell-shared-std-local/aqp-core` |
| `cell-silo-reg-acme` | `aqp-worker` | `spiffe://aqp.fund/cell/cell-silo-reg-acme/aqp-worker` |
| `cell-shared-std-us-east-1a` | `aqp-tenant-router` | `spiffe://aqp.fund/cell/cell-shared-std-us-east-1a/aqp-tenant-router` |

Cross-cell calls validate the full SPIFFE ID, not just the trust
domain — Cell-Bound-Authorization (Phase 5 §8.5) extends this with
biscuit capability tokens that pin a request to a specific cell.

## Deployment shape

Each cell runs ONE SPIRE control plane:

```
[ SPIRE Server StatefulSet ]  (spire-system namespace)
        ▲
        │ k8s_psat attest
        │
[ SPIRE Agent DaemonSet ]     (one per node)
        ▲
        │ unix socket: /run/spire/sockets/agent.sock
        │
[ AQP workload pod ]          (mounts the socket via hostPath volume)
        │
        └── spiffe.workloadapi.fetch_svid(audiences=[...])
```

The matching manifests live at:

- `aqp_platform/deployments/kubernetes/mesh-identity/spire/server.yaml`
- `aqp_platform/deployments/kubernetes/mesh-identity/spire/agent.yaml`

Per-cell installs come from the Argo CD `ApplicationSet` at
`aqp_platform/deployments/argocd/applicationsets/cells-appset.yaml`
(Phase 4.5 extends it with a `mesh-identity` component column).

## AQP integration

The application-side integration lives in
[`aqp/auth/providers/spiffe.py`](https://github.com/julianwiley/agentic_quant_platform/blob/main/aqp/auth/providers/spiffe.py)
(`SpiffeIdentityProvider`). It implements the
:py:class:`aqp.auth.providers.protocol.IdentityProvider` interface
but only the :py:meth:`m2m_token` method does real work — SPIFFE
is workload-only and does NOT participate in user OIDC flows. The
existing Auth0 / Entra providers stay wired for user-facing login.

### Wiring

```bash
# Operator sets the workload API socket path (default is the
# conventional /run/spire/sockets/agent.sock from the SPIRE Agent
# DaemonSet's hostPath mount).
export AQP_AUTH_SPIFFE_WORKLOAD_API_SOCKET="unix:///run/spire/sockets/agent.sock"

# Route the M2MTokenIssuer through SPIFFE instead of Auth0.
# (Phase 4.5 deliverable — the M2MTokenIssuer side is still TODO.)
export AQP_AUTH_M2M_PROVIDER=spiffe
```

When the SPIFFE socket isn't reachable (development mode, smoke
tests, migrations), `SpiffeIdentityProvider.m2m_token` raises
`IdentityProviderError`. The fallback chain in
`aqp.credentials.resolver` re-tries the legacy Auth0 path so
developers can iterate without a running SPIRE Agent.

## Pod template requirements

For a pod to consume SVIDs from the SPIRE Workload API:

1. Mount the agent's host socket:
   ```yaml
   volumes:
     - name: spire-agent-socket
       hostPath:
         path: /run/spire/sockets
         type: Directory
   containers:
     - name: ...
       volumeMounts:
         - name: spire-agent-socket
           mountPath: /run/spire/sockets
           readOnly: true
   ```
2. Set `SPIFFE_ENDPOINT_SOCKET=unix:///run/spire/sockets/agent.sock`
   in the pod env (or rely on the AQP default).
3. Be in the `spire-system` `ClusterSPIFFEID` selector — the
   matching CRD is shipped per-cell in Phase 4.5; today the
   `k8s_psat` Node Attestor accepts every workload with a
   matching ServiceAccount.

## Rotation + revocation

- **SVID lifetime**: 1h X.509-SVID, 5m JWT-SVID (configurable via
  the SPIRE Server config map).
- **Trust anchor lifetime**: 168h (7 days). Operators rotate the
  root via Vault PKI; the SPIRE Server propagates the new bundle
  to every Agent within ~1 minute.
- **Revocation**: deleting a workload's `RegistrationEntry` from
  the SPIRE Server invalidates all future SVID issuance. Existing
  in-flight SVIDs expire at their natural TTL — for an immediate
  cut-off, also rotate the trust anchor.

## Failure modes

| Failure | Behaviour |
| --- | --- |
| SPIRE Agent socket missing | `SpiffeIdentityProvider.m2m_token` raises `IdentityProviderError` |
| SPIRE Server unreachable | Agent serves cached SVID until it expires (~1h) |
| Workload not attested | `fetch_svid` raises; M2M chain falls through to Auth0 |
| Trust anchor rotation | SVIDs continue to validate during the 7-day overlap window |

## Phase 4.5 follow-ups

1. **Per-cell `ClusterSPIFFEID` CRDs** that bind workload selectors
   to SPIFFE IDs (today the spine relies on the default k8s_psat
   attestor).
2. **M2MTokenIssuer dispatch** — wire `AQP_AUTH_M2M_PROVIDER=spiffe`
   into the issuer so it picks SPIFFE for M2M without affecting
   user OIDC flows.
3. **Linkerd integration** — Linkerd consumes SPIFFE identity for
   mTLS termination (Phase 4 §7.1). Phase 4.5 wires the SPIFFE
   trust anchor into Linkerd's Identity service.
4. **OIDC discovery provider** — SPIRE Server can expose an OIDC
   discovery endpoint that lets non-SPIRE-aware services
   (Pomerium, Cloudflare Access) validate SVIDs as standard
   OIDC JWTs.
5. **Cross-cell federation** — Phase 8 §11.2 multi-region cells
   will need SPIFFE trust-domain federation.

## Related documents

- [RESTRUCTURING_PLAN.md §7.2](https://github.com/julianwiley/agentic_quant_platform/blob/main/RESTRUCTURING_PLAN.md)
- [aqp/auth/providers/spiffe.py](https://github.com/julianwiley/agentic_quant_platform/blob/main/aqp/auth/providers/spiffe.py)
- [aqp_platform/deployments/kubernetes/mesh-identity/spire/](https://github.com/julianwiley/agentic_quant_platform/blob/main/aqp_platform/deployments/kubernetes/mesh-identity/spire/)
- SPIFFE specification: https://github.com/spiffe/spiffe
- SPIRE: https://spiffe.io/docs/latest/spire-about/spire-concepts/
