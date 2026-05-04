"""KubernetesTarget manifest rendering + dispatch tests (no kubectl)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from aqp.bots.deploy import (
    DeploymentDispatcher,
    KubernetesTarget,
)
from aqp.bots.spec import BotSpec, DeploymentTargetSpec, UniverseRef
from aqp.bots.trading_bot import TradingBot


def _trading_spec(**overrides: Any) -> BotSpec:
    base = dict(
        name="K8s Trader",
        kind="trading",
        universe=UniverseRef(symbols=["AAPL.NASDAQ"]),
        strategy={"class": "FrameworkAlgorithm", "kwargs": {}},
        backtest={"engine": "vbt-pro:signals", "kwargs": {}},
        deployment=DeploymentTargetSpec(
            target="kubernetes",
            namespace="aqp-bots-test",
            image="ghcr.io/aqp/bot-runner:test",
        ),
    )
    base.update(overrides)
    return BotSpec(**base)


def test_render_manifest_includes_configmap_and_deployment() -> None:
    bot = TradingBot(spec=_trading_spec())
    target = KubernetesTarget(manifest_root=Path("/tmp/should-not-be-used"), apply=False)
    yaml_text = target.render_manifest(bot, overrides={})

    documents = list(yaml.safe_load_all(yaml_text))
    assert len(documents) == 2

    kinds = {d["kind"] for d in documents}
    assert kinds == {"ConfigMap", "Deployment"}

    configmap = next(d for d in documents if d["kind"] == "ConfigMap")
    deployment = next(d for d in documents if d["kind"] == "Deployment")

    assert configmap["metadata"]["namespace"] == "aqp-bots-test"
    assert configmap["metadata"]["labels"]["aqp.io/bot-slug"] == "k8s-trader"
    assert configmap["metadata"]["labels"]["aqp.io/bot-kind"] == "trading"
    assert "bot.yaml" in configmap["data"]
    assert "K8s Trader" in configmap["data"]["bot.yaml"]

    assert deployment["metadata"]["namespace"] == "aqp-bots-test"
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "ghcr.io/aqp/bot-runner:test"
    assert container["args"] == ["python", "-m", "aqp.bots.cli", "run", "k8s-trader"]
    env = {e["name"]: e["value"] for e in container["env"]}
    assert env["AQP_BOT_SLUG"] == "k8s-trader"
    volume_mounts = container["volumeMounts"]
    assert volume_mounts[0]["name"] == "spec"
    assert volume_mounts[0]["mountPath"] == "/etc/aqp/bot"


def test_render_manifest_uses_default_image_when_unspecified() -> None:
    spec = _trading_spec(deployment=DeploymentTargetSpec(target="kubernetes"))
    bot = TradingBot(spec=spec)
    target = KubernetesTarget(manifest_root=Path("/tmp"), apply=False)
    yaml_text = target.render_manifest(bot, overrides={})

    deployment = next(d for d in yaml.safe_load_all(yaml_text) if d["kind"] == "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "ghcr.io/aqp/bot-runner:latest"


def test_render_manifest_overrides_namespace_and_image_via_kwargs() -> None:
    bot = TradingBot(spec=_trading_spec())
    target = KubernetesTarget(manifest_root=Path("/tmp"), apply=False)
    yaml_text = target.render_manifest(
        bot, overrides={"namespace": "override-ns", "image": "ghcr.io/x/y:z"}
    )

    documents = list(yaml.safe_load_all(yaml_text))
    for doc in documents:
        assert doc["metadata"]["namespace"] == "override-ns"
    deployment = next(d for d in documents if d["kind"] == "Deployment")
    assert deployment["spec"]["template"]["spec"]["containers"][0]["image"] == "ghcr.io/x/y:z"


def test_render_manifest_uses_resource_overrides() -> None:
    spec = _trading_spec(
        deployment=DeploymentTargetSpec(
            target="kubernetes",
            resources={
                "requests": {"cpu": "500m", "memory": "1Gi"},
                "limits": {"cpu": "2", "memory": "4Gi"},
            },
        ),
    )
    bot = TradingBot(spec=spec)
    target = KubernetesTarget(manifest_root=Path("/tmp"), apply=False)
    yaml_text = target.render_manifest(bot, overrides={})

    deployment = next(d for d in yaml.safe_load_all(yaml_text) if d["kind"] == "Deployment")
    resources = deployment["spec"]["template"]["spec"]["containers"][0]["resources"]
    assert resources["requests"]["cpu"] == "500m"
    assert resources["limits"]["memory"] == "4Gi"


def test_kubernetes_target_writes_file_to_manifest_root(tmp_path: Path, monkeypatch) -> None:
    """Deploy with apply=False writes the manifest YAML next to the kustomization."""
    bot = TradingBot(spec=_trading_spec())
    monkeypatch.setattr("aqp.bots.deploy._open_deployment_row", lambda *a, **kw: None)
    monkeypatch.setattr("aqp.bots.deploy._finalise_deployment_row", lambda *a, **kw: None)

    target = KubernetesTarget(manifest_root=tmp_path, apply=False)
    result = target.deploy(bot, overrides={})

    assert result.status == "completed"
    manifest_path = tmp_path / "k8s-trader.yaml"
    assert manifest_path.exists()
    text = manifest_path.read_text(encoding="utf-8")
    assert "kind: ConfigMap" in text
    assert "kind: Deployment" in text
    assert result.manifest_yaml == text
    assert result.result["applied"] is False  # apply=False keeps it as a render-only artefact


def test_kubernetes_target_skips_apply_without_kubectl(tmp_path: Path, monkeypatch) -> None:
    """When apply=True but kubectl isn't on PATH the target writes the manifest only."""
    monkeypatch.setattr("aqp.bots.deploy.shutil.which", lambda name: None)
    monkeypatch.setattr("aqp.bots.deploy._open_deployment_row", lambda *a, **kw: None)
    monkeypatch.setattr("aqp.bots.deploy._finalise_deployment_row", lambda *a, **kw: None)

    bot = TradingBot(spec=_trading_spec())
    target = KubernetesTarget(manifest_root=tmp_path, apply=True)
    result = target.deploy(bot, overrides={})

    assert result.status == "completed"
    assert result.result["applied"] is False  # graceful no-op


def test_dispatcher_routes_kubernetes_target() -> None:
    dispatcher = DeploymentDispatcher()
    assert isinstance(dispatcher._targets["kubernetes"], KubernetesTarget)


def test_dispatcher_register_custom_target() -> None:
    dispatcher = DeploymentDispatcher()

    class _Custom(KubernetesTarget):
        name = "custom-k8s"

    dispatcher.register(_Custom())
    assert "custom-k8s" in dispatcher._targets
