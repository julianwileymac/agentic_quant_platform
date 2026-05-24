"""Phase 8: Operator manifest rendering."""
from __future__ import annotations

from aqp_bots.operator.crds.bot_cr import (
    BotCR,
    BotSpecField,
    CapabilitiesField,
    ResourcesField,
    SchedulingHints,
    StrategyRef,
)
from aqp_bots.operator.render import render_bot_workload


def _cr(frequency: str, **caps_overrides) -> BotCR:
    caps = CapabilitiesField(frequency=frequency, **caps_overrides)  # type: ignore[arg-type]
    return BotCR(
        metadata={"name": "test-bot", "namespace": "aqp-bots", "uid": "u-1"},
        spec=BotSpecField(
            capabilities=caps,
            strategyRef=StrategyRef(name="s1"),
            resources=ResourcesField(),
            schedulingHints=SchedulingHints(),
            botSpec={"name": "Test Bot", "slug": "test-bot", "kind": "trading"},
        ),
    )


def test_mid_frequency_renders_statefulset() -> None:
    docs = render_bot_workload(_cr("mid"))
    kinds = [d["kind"] for d in docs]
    assert "ConfigMap" in kinds
    assert "StatefulSet" in kinds
    assert "Service" in kinds


def test_low_frequency_renders_deployment() -> None:
    docs = render_bot_workload(_cr("low"))
    kinds = [d["kind"] for d in docs]
    assert "Deployment" in kinds


def test_hft_renders_daemonset_with_pdb() -> None:
    docs = render_bot_workload(
        _cr("hft", needsNumaPinning=True, expectedP99TickToTradeUs=50)
    )
    kinds = [d["kind"] for d in docs]
    assert "DaemonSet" in kinds
    assert "PodDisruptionBudget" in kinds


def test_eod_renders_cronjob() -> None:
    docs = render_bot_workload(_cr("eod"))
    kinds = [d["kind"] for d in docs]
    assert "CronJob" in kinds


def test_hft_pod_has_node_selector() -> None:
    docs = render_bot_workload(
        _cr("hft", needsNumaPinning=True, expectedP99TickToTradeUs=50)
    )
    ds = next(d for d in docs if d["kind"] == "DaemonSet")
    pod_spec = ds["spec"]["template"]["spec"]
    assert pod_spec["nodeSelector"]["quantbot.io/hft"] == "true"
    # HFT pods MUST have the HFT toleration.
    keys = [t["key"] for t in pod_spec["tolerations"]]
    assert "quantbot.io/hft" in keys


def test_pod_runs_as_nonroot() -> None:
    docs = render_bot_workload(_cr("low"))
    deploy = next(d for d in docs if d["kind"] == "Deployment")
    pod_spec = deploy["spec"]["template"]["spec"]
    assert pod_spec["securityContext"]["runAsNonRoot"] is True
    assert pod_spec["securityContext"]["runAsUser"] == 65532
    container = pod_spec["containers"][0]
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
