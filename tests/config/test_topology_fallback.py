"""Smoke tests for ``aqp.config.topology_fallback``."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def topology_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write a minimal topology YAML with the new endpoint fields populated."""
    text = textwrap.dedent(
        """
        version: 1

        defaults:
          organization_slug: wiley-tech
          workspace_slug: main
          app_version: latest
          labels: {}

        tooling:
          terraform:
            binary_setting: AQP_TERRAFORM_BINARY
            min_version: "1.10"
            provider_mirror_path: data/terraform/plugin-cache
            plugin_cache_path: data/terraform/plugin-cache-runtime
            cli_config_file: data/terraform/terraform.tfrc

        services:
          - id: redpanda
            label: Redpanda
            role: streaming
            workload: statefulset
            app_label: redpanda
            cluster: streaming.redpanda
            namespace: aqp-streaming
            port: 9092
            protocols:
              kafka: 9092
              admin: 9644
            endpoints:
              bootstrap: redpanda.aqp-streaming.svc.cluster.local:9092
              admin: http://redpanda.aqp-streaming.svc.cluster.local:9644
          - id: questdb
            label: QuestDB
            role: timeseries
            workload: statefulset
            app_label: questdb
            cluster: timeseries.questdb
            namespace: aqp-timeseries
            port: 9000
            protocols:
              http: 9000
              ilp_tcp: 9009
              pgwire: 8812
            endpoints:
              http: http://questdb.aqp-timeseries.svc.cluster.local:9000
              ilp_tcp: questdb.aqp-timeseries.svc.cluster.local:9009
              pgwire: postgresql://aqp:aqp@questdb.aqp-timeseries.svc.cluster.local:8812/qdb

        targets:
          unit:
            id: unit
            label: unit
            kind: local
            environment: unit
            cloud_provider: local
            namespace: aqp
            adapter_preference: [in_cluster]
            terraform:
              stack_slug: aqp-unit
              spec_path: configs/terraform/local.yaml
              environment_dir: terraform/environments/local
            cluster:
              name: aqp-unit
            services: [redpanda, questdb]
        """
    ).strip()
    path = tmp_path / "topology.yaml"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setenv("AQP_DEPLOYMENT_TOPOLOGY_PATH", str(path))
    # The platform-core loader caches by path, the AQP-side loader has its own
    # lru_cache. Reset both.
    from aqp_platform_core.topology import reset_topology_cache

    reset_topology_cache()
    return path


def test_topology_fallback_populates_new_url_fields(topology_yaml: Path) -> None:
    from aqp.config.settings import Settings
    from aqp.config.topology_fallback import apply_topology_fallback

    settings = Settings()
    applied = apply_topology_fallback(settings)
    assert "redpanda_bootstrap" in applied
    assert applied["redpanda_bootstrap"].endswith(":9092")
    assert "questdb_pg_url" in applied
    assert applied["questdb_pg_url"].startswith("postgresql://")
    assert "questdb_ilp_url" in applied


def test_topology_fallback_skips_when_env_overrides(
    topology_yaml: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aqp.config.settings import Settings
    from aqp.config.topology_fallback import apply_topology_fallback

    monkeypatch.setenv("AQP_REDPANDA_BOOTSTRAP", "explicit-override:19092")
    settings = Settings()
    applied = apply_topology_fallback(settings)
    assert "redpanda_bootstrap" not in applied
    assert settings.redpanda_bootstrap == "explicit-override:19092"


def test_topology_fallback_safe_when_yaml_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from aqp.config.settings import Settings
    from aqp.config.topology_fallback import apply_topology_fallback
    from aqp_platform_core.topology import reset_topology_cache

    missing = tmp_path / "does-not-exist.yaml"
    monkeypatch.setenv("AQP_DEPLOYMENT_TOPOLOGY_PATH", str(missing))
    reset_topology_cache()

    settings = Settings()
    # Should not raise, even though the YAML is absent.
    applied = apply_topology_fallback(settings)
    assert applied == {}


def test_topology_fallback_resolves_to_aqp_namespaces_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decoupling guard: every URL resolved by the fallback must point at
    an ``aqp-*`` Kubernetes namespace.

    No legacy rpi_kubernetes namespace (``data-services``,
    ``ml-platform``, ``observability``, ``mlops``, ``flink``,
    ``development``) may surface for any field that the fallback covers
    when the operator has NOT set an explicit ``AQP_*`` env override.
    """
    import yaml

    from aqp.config.settings import Settings
    from aqp.config.topology_fallback import (
        URL_FALLBACK_FIELDS,
        apply_topology_fallback,
    )
    from aqp_platform_core.topology import reset_topology_cache

    # Use the real shipped topology - it is the operator-facing source of
    # truth for the rpi <-> AQP decoupling.
    repo_root = Path(__file__).resolve().parents[2]
    topology_path = repo_root / "configs" / "deployment" / "topology.yaml"
    if not topology_path.exists():  # pragma: no cover - sanity guard
        pytest.skip("topology.yaml missing from this checkout")

    monkeypatch.setenv("AQP_DEPLOYMENT_TOPOLOGY_PATH", str(topology_path))
    reset_topology_cache()

    # Wipe any AQP_* env vars covered by the fallback so the fallback
    # actually runs (env always wins). Anything an operator was holding
    # would mask the namespace check we want to make.
    text = topology_path.read_text(encoding="utf-8")
    payload = yaml.safe_load(text)
    declared_service_ids = {svc["id"] for svc in payload.get("services", [])}
    for mapping in URL_FALLBACK_FIELDS:
        if mapping.service_id in declared_service_ids:
            monkeypatch.delenv(
                f"AQP_{mapping.settings_field.upper()}",
                raising=False,
            )

    settings = Settings()
    applied = apply_topology_fallback(settings)
    forbidden = (
        ".data-services.svc.cluster.local",
        ".ml-platform.svc.cluster.local",
        ".observability.svc.cluster.local",
        ".mlops.svc.cluster.local",
        ".flink.svc.cluster.local",
        ".development.svc.cluster.local",
    )
    leakage = {
        field: url
        for field, url in applied.items()
        if any(needle in url for needle in forbidden)
    }
    assert not leakage, (
        "topology fallback resolved rpi-side namespaces; AQP must be "
        f"cluster-agnostic. Offending fields: {leakage}"
    )
