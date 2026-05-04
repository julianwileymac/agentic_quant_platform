"""Tests for the Flink session-job template + submit_factor_job fallback."""
from __future__ import annotations


def test_render_factor_session_job_shape() -> None:
    from aqp.streaming.templates import render_factor_session_job

    manifest = render_factor_session_job(
        name="test-job",
        namespace="data-services",
        factor_jar_uri="s3://flink-jobs/factor.jar",
        entry_class="io.aqp.flink.factor.FactorJob",
        args=["--factor", "RSI(14)"],
        parallelism=2,
    )
    assert manifest["apiVersion"] == "flink.apache.org/v1beta1"
    assert manifest["kind"] == "FlinkSessionJob"
    assert manifest["metadata"]["name"] == "test-job"
    assert manifest["spec"]["job"]["jarURI"] == "s3://flink-jobs/factor.jar"
    assert manifest["spec"]["job"]["parallelism"] == 2
    assert manifest["spec"]["job"]["state"] == "running"
    assert "--factor" in manifest["spec"]["job"]["args"]


def test_submit_factor_job_returns_unavailable_without_k8s(monkeypatch) -> None:
    from aqp.streaming import runtime as r

    def _raise() -> None:
        from aqp.streaming.admin import FlinkAdminUnavailableError

        raise FlinkAdminUnavailableError("kubernetes SDK not installed")

    # Monkeypatch the lazy session-job factory to raise unavailable.
    from aqp.streaming.admin import flink_admin as fa

    monkeypatch.setattr(fa, "get_flink_session_jobs", _raise)
    monkeypatch.setattr(r, "get_flink_session_jobs", _raise, raising=False)
    # Also patch the module-level import used inside submit_factor_job.
    import aqp.streaming.admin as admin_module

    monkeypatch.setattr(admin_module, "get_flink_session_jobs", _raise)

    result = r.submit_factor_job(
        name="test",
        factor_expression="RSI(14)",
        namespace="data-services",
    )
    assert result["status"] == "unavailable"
    assert result["manifest"]["kind"] == "FlinkSessionJob"
