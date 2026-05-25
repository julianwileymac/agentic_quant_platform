"""Kaniko Job-manifest snapshot tests."""
from __future__ import annotations

from aqp_cp.builders.kaniko import (
    ConfigMapBuildSource,
    GitBuildSource,
    KanikoBuilder,
    KanikoBuildSpec,
    S3BuildSource,
)


def _builder() -> KanikoBuilder:
    return KanikoBuilder(
        default_image="ghcr.io/chainguard-dev/kaniko:latest",
        default_namespace="aqp-builds",
        default_builder_sa="kaniko-builder",
        default_ttl_seconds=600,
        default_backoff_limit=2,
    )


class TestKanikoManifest:
    def test_configmap_source_mounts_workspace(self) -> None:
        builder = _builder()
        manifest = builder.render(
            KanikoBuildSpec(
                image_ref="ghcr.io/aqp/demo:dev",
                source=ConfigMapBuildSource(configmap_name="demo-df"),
            )
        )
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert container["image"].startswith("ghcr.io/chainguard-dev/kaniko")
        assert "--context=dir:///workspace" in container["args"]
        volume_mounts = container.get("volumeMounts") or []
        assert volume_mounts[0]["mountPath"] == "/workspace"
        assert manifest["spec"]["template"]["spec"]["serviceAccountName"] == "kaniko-builder"

    def test_git_source_emits_git_context(self) -> None:
        builder = _builder()
        manifest = builder.render(
            KanikoBuildSpec(
                image_ref="ghcr.io/aqp/demo:dev",
                source=GitBuildSource(
                    repo_url="github.com/aqp/demo.git",
                    branch="feature/foo",
                    sub_path="services/api",
                ),
            )
        )
        args = manifest["spec"]["template"]["spec"]["containers"][0]["args"]
        assert "--context=git://github.com/aqp/demo.git#refs/heads/feature/foo:services/api" in args

    def test_s3_source_emits_s3_context(self) -> None:
        builder = _builder()
        manifest = builder.render(
            KanikoBuildSpec(
                image_ref="ghcr.io/aqp/demo:dev",
                source=S3BuildSource(
                    bucket="aqp-builds", key="acme/demo.tar", region="us-east-1"
                ),
            )
        )
        args = manifest["spec"]["template"]["spec"]["containers"][0]["args"]
        assert "--context=s3://aqp-builds/acme/demo.tar" in args
        assert "--region=us-east-1" in args

    def test_no_secret_mounted_for_cloud_creds(self) -> None:
        builder = _builder()
        manifest = builder.render(
            KanikoBuildSpec(
                image_ref="ghcr.io/aqp/demo:dev",
                source=ConfigMapBuildSource(configmap_name="demo-df"),
            )
        )
        # IMPORTANT (Phase 1.2 rule): no Secret volumes / envFrom secretRef.
        volumes = manifest["spec"]["template"]["spec"]["volumes"]
        for vol in volumes:
            assert "secret" not in vol, f"secret volume snuck in: {vol}"
        env = manifest["spec"]["template"]["spec"]["containers"][0]["env"]
        for entry in env:
            assert "valueFrom" not in entry, f"valueFrom secret snuck in: {entry}"

    def test_owner_reference_when_uid_supplied(self) -> None:
        builder = _builder()
        manifest = builder.render(
            KanikoBuildSpec(
                image_ref="ghcr.io/aqp/demo:dev",
                source=ConfigMapBuildSource(configmap_name="demo-df"),
                owner_uid="aaaa-bbbb-cccc",
                owner_kind="QuantAgent",
                owner_name="acme-momentum",
            )
        )
        refs = manifest["metadata"]["ownerReferences"]
        assert refs[0]["uid"] == "aaaa-bbbb-cccc"
        assert refs[0]["kind"] == "QuantAgent"
        assert refs[0]["controller"] is True

    def test_ttl_and_backoff_propagate(self) -> None:
        builder = _builder()
        manifest = builder.render(
            KanikoBuildSpec(
                image_ref="ghcr.io/aqp/demo:dev",
                source=ConfigMapBuildSource(configmap_name="demo-df"),
                ttl_seconds_after_finished=120,
                backoff_limit=0,
            )
        )
        assert manifest["spec"]["ttlSecondsAfterFinished"] == 120
        assert manifest["spec"]["backoffLimit"] == 0

    def test_build_args_become_kaniko_flags(self) -> None:
        builder = _builder()
        manifest = builder.render(
            KanikoBuildSpec(
                image_ref="ghcr.io/aqp/demo:dev",
                source=ConfigMapBuildSource(configmap_name="demo-df"),
                build_args={"GIT_SHA": "abc123"},
            )
        )
        args = manifest["spec"]["template"]["spec"]["containers"][0]["args"]
        assert "--build-arg=GIT_SHA=abc123" in args
