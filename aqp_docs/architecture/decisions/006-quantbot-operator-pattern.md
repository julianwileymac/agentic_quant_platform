# ADR 006 — QuantBot Operator Pattern (kopf + Pydantic mirrors)

**Status:** Accepted (QuantBot Platform v0.2.0)
**Date:** 2026-05-24
**Decision drivers:** AGENTS rules 14, 15, 28, 45; rpi-k8s-governance

## Context

The QuantBot Platform v0.2.0 adds a Kubernetes-native control plane on
top of the existing `BotRuntime`/`bot_versions` infrastructure. Every
running bot, every risk policy, every venue feed, every backtest job,
every kill switch is now a Kubernetes Custom Resource. That requires:

1. A controller that watches the CRs and reconciles desired state.
2. A schema source-of-truth for each CR.
3. Webhooks that reject malformed CRs before they reach the reconciler.

## Decision

- **Controller framework:** kopf (`kopf>=1.37`). Python-native, integrates
  with our Pydantic spec layer, supports level-triggered reconciliation,
  finalizers, and admission webhooks. Up to ~1000 CRs/cluster is well
  within kopf's documented operating envelope.
- **Schema source-of-truth:** each CR has both a Pydantic mirror class
  (under `aqp_bots/operator/crds/*_cr.py`) AND a CRD YAML
  (`aqp_bots/operator/crds/yaml/*_crd.yaml`). The Pydantic class is
  validated from the CR `.spec` field; the YAML is what gets applied to
  the cluster by the CRD-installer Job. The two are kept in sync by
  convention + the operator's startup self-test.
- **Reconciliation:** level-triggered. Every handler compares desired
  (from spec) against actual (queried from the cluster) and drives the
  system back. Failures reflect onto `status.conditions`.
- **Workload application:** routes through `aqp_platform_core.WorkloadRuntime`
  per AGENTS rule 45. The operator never calls
  `kubernetes.client.AppsV1Api()` directly when WorkloadRuntime is
  available; falls back to `kubernetes-asyncio` only for environments
  where WorkloadRuntime hasn't been deployed yet.

## Alternatives considered

| Option | Why rejected |
| --- | --- |
| Go operator (controller-runtime / Kubebuilder) | Re-implements the spec validation already written in Pydantic; bigger team operational burden for a Python-first shop |
| metacontroller + JSON Schema | No mature Python ecosystem for the testing + audit story we need; JSON Schema diverges from Pydantic validators |
| Native Helm charts only (no controller) | Helm can't reconcile the operator-side bookkeeping (kill switch fan-out, drain finalizer, status condition rollup) |

## Consequences

- **+** Single source of truth (Pydantic) drives both API validation and
  CR validation.
- **+** Python-native test suite for the operator (kopf can be driven
  in-process from pytest).
- **−** kopf scaling ceiling is ~1000 CRs per cluster; beyond that we
  need operator sharding (deferred per blueprint caveat #2).
- **−** Pydantic mirror + YAML CRD requires manual sync. Mitigated by
  CI: a startup check compares the Pydantic JSON schema against the
  CRD's `openAPIV3Schema` and refuses to boot on drift.

## References

- [aqp_bots/operator/](../../../aqp_bots/operator/)
- [aqp_platform/deployments/kubernetes/bots-operator/](../../../aqp_platform/deployments/kubernetes/bots-operator/)
