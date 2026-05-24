"""Thin OPA client wrapping the existing Terraform OPA wiring.

The existing :mod:`aqp.terraform.policy` calls ``opa eval`` for
Terraform plans. Phase 6 generalises that into a general-purpose
ingestion-plane policy gate so the four new ingestion routes can
attach a Rego check next to step-up MFA.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class OPAClient:
    """Thin wrapper around ``opa eval`` or the sidecar HTTP API."""

    def __init__(
        self,
        *,
        opa_url: str | None = None,
        bundle_dir: str = "aqp/policy/rego",
    ) -> None:
        self._opa_url = opa_url
        self._bundle_dir = bundle_dir

    def evaluate(
        self,
        *,
        package: str,
        input_doc: dict[str, Any],
    ) -> dict[str, Any]:
        """Evaluate one OPA query against the bundle."""
        if self._opa_url:
            try:
                import httpx  # type: ignore[import-not-found]

                resp = httpx.post(
                    f"{self._opa_url}/v1/data/{package.replace('.', '/')}",
                    json={"input": input_doc},
                    timeout=2.0,
                )
                resp.raise_for_status()
                return resp.json().get("result", {})
            except Exception as exc:  # noqa: BLE001
                logger.warning("OPA sidecar eval failed: %s", exc)
                return {"allow": False, "error": str(exc)}
        try:
            import json
            import subprocess

            proc = subprocess.run(
                [
                    "opa",
                    "eval",
                    "--data",
                    self._bundle_dir,
                    "--input",
                    "-",
                    "--format",
                    "json",
                    f"data.{package}",
                ],
                input=json.dumps(input_doc),
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            return json.loads(proc.stdout).get("result", [{}])[0].get(
                "expressions", [{}]
            )[0].get("value", {})
        except Exception as exc:  # noqa: BLE001
            logger.warning("opa eval failed: %s", exc)
            return {"allow": True, "warning": f"opa unavailable: {exc}"}


def evaluate_policy(
    *,
    package: str,
    input_doc: dict[str, Any],
) -> dict[str, Any]:
    """Module-level convenience wrapper using the canonical client."""
    client = OPAClient(
        opa_url=_settings_opa_url(),
    )
    return client.evaluate(package=package, input_doc=input_doc)


def _settings_opa_url() -> str | None:
    try:
        from aqp.config import settings

        return getattr(settings, "opa_url", None)
    except Exception:  # noqa: BLE001
        return None


__all__ = ["OPAClient", "evaluate_policy"]
