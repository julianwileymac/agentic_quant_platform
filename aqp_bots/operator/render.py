"""Render a Bot CR into a Kubernetes workload.

Maps :attr:`CapabilitiesField.frequency` → K8s workload primitive:

- ``hft``  → ``DaemonSet`` on tainted nodes (one bot per node)
- ``mid``  → ``StatefulSet`` (stable identity for state replay)
- ``low``  → ``Deployment`` (stateless, cheap rolling)
- ``eod``  → ``CronJob`` (schedule on spec)
- ``event``→ ``Deployment`` (long-running event consumer)

Backtest workloads (``BacktestJob`` CRs) render to ``Job`` with
``parallelism = spec.parallelism``.

The renderer emits manifests with full ownerReferences pointing back
at the originating CR so the operator's finalizer + cascade delete
work as documented in the kopf framework.
"""
from __future__ import annotations

from typing import Any

from aqp_bots.operator.crds.backtestjob_cr import BacktestJobCR
from aqp_bots.operator.crds.bot_cr import BotCR
from aqp_bots.operator.labels import bot_labels, selector_labels


_DEFAULT_IMAGE = "ghcr.io/aqp/quantbot-runtime:latest"


def render_bot_workload(
    cr: BotCR,
    *,
    image: str | None = None,
    spec_configmap_name: str | None = None,
) -> list[dict[str, Any]]:
    """Render a Bot CR into one or more k8s manifests.

    Returns a list of dicts (manifest documents); the caller applies
    each via :class:`kubernetes_asyncio.client.CustomObjectsApi` /
    standard apps API.
    """
    slug = cr.metadata.name
    namespace = cr.metadata.namespace
    fleet = cr.spec.fleet
    strategy_name = cr.spec.strategyRef.name if cr.spec.strategyRef else None
    capabilities = cr.spec.capabilities
    labels = bot_labels(
        bot_slug=slug,
        bot_kind=cr.spec.botSpec.get("kind", "trading") if cr.spec.botSpec else "trading",
        fleet=fleet,
        strategy=strategy_name,
        variant=cr.metadata.labels.get("quantbot.io/variant", "stable"),
    )
    owner_ref = _owner_ref(cr)

    documents: list[dict[str, Any]] = []

    # ConfigMap carrying the BotSpec YAML payload — mounted at /etc/quantbot/bot.yaml.
    cm_name = spec_configmap_name or f"bot-{slug}-spec"
    documents.append(
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": cm_name,
                "namespace": namespace,
                "labels": labels,
                "ownerReferences": [owner_ref],
            },
            "data": {
                "bot.yaml": _yaml_dump(cr.spec.botSpec or {}),
            },
        }
    )

    container = _bot_container(
        slug=slug,
        image=image or _DEFAULT_IMAGE,
        configmap_name=cm_name,
        resources=cr.spec.resources.model_dump(),
        capabilities=capabilities.model_dump(),
    )
    pod_spec = _pod_spec(
        container=container,
        configmap_name=cm_name,
        capabilities=capabilities.model_dump(),
        scheduling_hints=cr.spec.schedulingHints.model_dump(),
    )

    frequency = capabilities.frequency
    if frequency == "hft":
        documents.append(_render_daemonset(slug, namespace, labels, pod_spec, owner_ref))
    elif frequency == "eod":
        documents.append(
            _render_cronjob(
                slug,
                namespace,
                labels,
                pod_spec,
                owner_ref,
                schedule=cr.spec.config.get("schedule", "0 21 * * 1-5"),
            )
        )
    elif frequency == "mid":
        documents.append(_render_statefulset(slug, namespace, labels, pod_spec, owner_ref))
    else:
        # ``low`` and ``event`` -> Deployment.
        documents.append(_render_deployment(slug, namespace, labels, pod_spec, owner_ref))

    # Headless Service for the bot's health endpoint (port 9090).
    documents.append(_render_service(slug, namespace, labels, owner_ref))

    # PodDisruptionBudget for HFT fleets — no involuntary disruption.
    if frequency == "hft":
        documents.append(_render_pdb(slug, namespace, labels, owner_ref))

    return documents


def render_backtest_workload(
    cr: BacktestJobCR,
    *,
    image: str | None = None,
) -> list[dict[str, Any]]:
    """Render a BacktestJob CR into a ``batch/v1 Job``."""
    name = cr.metadata.name
    namespace = cr.metadata.namespace
    labels = {
        "app.kubernetes.io/name": "quantbot-backtest",
        "app.kubernetes.io/instance": name,
        "quantbot.io/backtest-kind": cr.spec.kind,
    }
    if cr.spec.botRef:
        labels["quantbot.io/bot-ref"] = cr.spec.botRef
    owner_ref = _owner_ref(cr)
    return [
        {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": name,
                "namespace": namespace,
                "labels": labels,
                "ownerReferences": [owner_ref],
            },
            "spec": {
                "parallelism": max(1, int(cr.spec.parallelism)),
                "completions": max(1, int(cr.spec.parallelism)),
                "backoffLimit": 2,
                "template": {
                    "metadata": {"labels": labels},
                    "spec": {
                        "restartPolicy": "Never",
                        "containers": [
                            {
                                "name": "backtest",
                                "image": image or _DEFAULT_IMAGE,
                                "args": [
                                    "python",
                                    "-m",
                                    "aqp_bots.cli",
                                    "backtest",
                                    cr.spec.botRef or "inline",
                                ],
                                "env": [
                                    {"name": "AQP_BACKTEST_KIND", "value": cr.spec.kind},
                                    {"name": "AQP_BACKTEST_START", "value": cr.spec.startDate or ""},
                                    {"name": "AQP_BACKTEST_END", "value": cr.spec.endDate or ""},
                                ],
                                "resources": {
                                    "requests": {"cpu": "1", "memory": "2Gi"},
                                    "limits": {"cpu": "4", "memory": "8Gi"},
                                },
                            }
                        ],
                    },
                },
            },
        }
    ]


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _bot_container(
    *,
    slug: str,
    image: str,
    configmap_name: str,
    resources: dict[str, Any],
    capabilities: dict[str, Any],
) -> dict[str, Any]:
    env = [
        {"name": "AQP_BOT_SLUG", "value": slug},
        {"name": "AQP_BOTS_FREQUENCY", "value": capabilities.get("frequency", "mid")},
    ]
    container: dict[str, Any] = {
        "name": "bot",
        "image": image,
        "imagePullPolicy": "IfNotPresent",
        "args": ["python", "-m", "aqp_bots.cli", "run", slug],
        "env": env,
        "resources": resources or {
            "requests": {"cpu": "200m", "memory": "256Mi"},
            "limits": {"cpu": "1", "memory": "1Gi"},
        },
        "ports": [
            {"name": "health", "containerPort": 9090, "protocol": "TCP"},
        ],
        "livenessProbe": {
            "httpGet": {"path": "/healthz", "port": "health"},
            "periodSeconds": 30,
            "initialDelaySeconds": 30,
        },
        "readinessProbe": {
            "httpGet": {"path": "/readyz", "port": "health"},
            "periodSeconds": 5,
            "initialDelaySeconds": 5,
        },
        "volumeMounts": [
            {"name": "spec", "mountPath": "/etc/quantbot"},
        ],
        "securityContext": {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": 65532,
            "capabilities": {"drop": ["ALL"]},
        },
    }
    if capabilities.get("needsGpu"):
        container["resources"].setdefault("limits", {})["nvidia.com/gpu"] = "1"
    return container


def _pod_spec(
    *,
    container: dict[str, Any],
    configmap_name: str,
    capabilities: dict[str, Any],
    scheduling_hints: dict[str, Any],
) -> dict[str, Any]:
    pod_spec: dict[str, Any] = {
        "serviceAccountName": "quantbot-bot",
        "automountServiceAccountToken": False,
        "containers": [container],
        "volumes": [
            {
                "name": "spec",
                "configMap": {"name": configmap_name, "defaultMode": 0o444},
            },
        ],
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": 65532,
            "fsGroup": 65532,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "terminationGracePeriodSeconds": 30 if capabilities.get("frequency") == "hft" else 300,
    }
    if scheduling_hints.get("nodeSelector"):
        pod_spec["nodeSelector"] = scheduling_hints["nodeSelector"]
    if scheduling_hints.get("tolerations"):
        pod_spec["tolerations"] = scheduling_hints["tolerations"]
    if scheduling_hints.get("affinity"):
        pod_spec["affinity"] = scheduling_hints["affinity"]
    if capabilities.get("frequency") == "hft":
        # HFT scheduling defaults: NUMA-pinned node taint + anti-affinity for one-per-node.
        pod_spec.setdefault("nodeSelector", {})["quantbot.io/hft"] = "true"
        pod_spec.setdefault("tolerations", []).append(
            {
                "key": "quantbot.io/hft",
                "operator": "Equal",
                "value": "true",
                "effect": "NoSchedule",
            }
        )
        pod_spec.setdefault("affinity", {}).setdefault("podAntiAffinity", {}).setdefault(
            "requiredDuringSchedulingIgnoredDuringExecution", []
        ).append(
            {
                "labelSelector": {"matchLabels": {"quantbot.io/hft": "true"}},
                "topologyKey": "kubernetes.io/hostname",
            }
        )
    return pod_spec


def _render_deployment(slug, namespace, labels, pod_spec, owner_ref):
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": f"bot-{slug}", "namespace": namespace, "labels": labels, "ownerReferences": [owner_ref]},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": selector_labels(slug)},
            "template": {
                "metadata": {"labels": {**labels, **selector_labels(slug)}},
                "spec": pod_spec,
            },
            "strategy": {"type": "RollingUpdate", "rollingUpdate": {"maxSurge": 0, "maxUnavailable": 1}},
        },
    }


def _render_statefulset(slug, namespace, labels, pod_spec, owner_ref):
    return {
        "apiVersion": "apps/v1",
        "kind": "StatefulSet",
        "metadata": {"name": f"bot-{slug}", "namespace": namespace, "labels": labels, "ownerReferences": [owner_ref]},
        "spec": {
            "serviceName": f"bot-{slug}",
            "replicas": 1,
            "selector": {"matchLabels": selector_labels(slug)},
            "template": {
                "metadata": {"labels": {**labels, **selector_labels(slug)}},
                "spec": pod_spec,
            },
            "podManagementPolicy": "OrderedReady",
            "updateStrategy": {"type": "RollingUpdate"},
        },
    }


def _render_daemonset(slug, namespace, labels, pod_spec, owner_ref):
    return {
        "apiVersion": "apps/v1",
        "kind": "DaemonSet",
        "metadata": {"name": f"bot-{slug}", "namespace": namespace, "labels": labels, "ownerReferences": [owner_ref]},
        "spec": {
            "selector": {"matchLabels": selector_labels(slug)},
            "template": {
                "metadata": {"labels": {**labels, **selector_labels(slug)}},
                "spec": pod_spec,
            },
            "updateStrategy": {"type": "RollingUpdate"},
        },
    }


def _render_cronjob(slug, namespace, labels, pod_spec, owner_ref, *, schedule: str):
    # CronJob pod template can't have terminationGracePeriodSeconds at top level —
    # it's already nested inside template.spec.
    return {
        "apiVersion": "batch/v1",
        "kind": "CronJob",
        "metadata": {"name": f"bot-{slug}", "namespace": namespace, "labels": labels, "ownerReferences": [owner_ref]},
        "spec": {
            "schedule": schedule,
            "concurrencyPolicy": "Forbid",
            "successfulJobsHistoryLimit": 3,
            "failedJobsHistoryLimit": 3,
            "jobTemplate": {
                "spec": {
                    "template": {
                        "metadata": {"labels": {**labels, **selector_labels(slug)}},
                        "spec": {**pod_spec, "restartPolicy": "OnFailure"},
                    },
                },
            },
        },
    }


def _render_service(slug, namespace, labels, owner_ref):
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": f"bot-{slug}",
            "namespace": namespace,
            "labels": labels,
            "ownerReferences": [owner_ref],
        },
        "spec": {
            "clusterIP": "None",
            "selector": selector_labels(slug),
            "ports": [
                {"name": "health", "port": 9090, "targetPort": "health", "protocol": "TCP"},
            ],
        },
    }


def _render_pdb(slug, namespace, labels, owner_ref):
    return {
        "apiVersion": "policy/v1",
        "kind": "PodDisruptionBudget",
        "metadata": {
            "name": f"bot-{slug}",
            "namespace": namespace,
            "labels": labels,
            "ownerReferences": [owner_ref],
        },
        "spec": {
            "maxUnavailable": 0,
            "selector": {"matchLabels": selector_labels(slug)},
        },
    }


def _owner_ref(cr: Any) -> dict[str, Any]:
    return {
        "apiVersion": cr.apiVersion,
        "kind": cr.kind,
        "name": cr.metadata.name,
        "uid": cr.metadata.uid or "",
        "controller": True,
        "blockOwnerDeletion": True,
    }


def _yaml_dump(payload: dict[str, Any]) -> str:
    import yaml

    return yaml.safe_dump(payload, sort_keys=False)


__all__ = ["render_backtest_workload", "render_bot_workload"]
