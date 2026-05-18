"""AWS EKS :class:`KubernetesAdapter` — auth via boto3 + STS GetToken.

Subclasses :class:`InClusterAdapter` so all the pod-level surface
(exec / logs / archive / list_pods / scale / apply_manifest) is
inherited as-is. Only the kubeconfig construction step differs:

- When running OUTSIDE the cluster (operator laptop / CI): uses
  :func:`boto3.client('sts').get_caller_identity` to derive STS
  credentials and calls ``aws eks get-token``-equivalent logic
  (via the official ``awscli`` ``STSTokenGenerator``).
- When running INSIDE an EKS cluster (the runner pod): IRSA
  (IAM Roles for Service Accounts) gives boto3 first-class
  credentials automatically and the EKS control-plane endpoint is
  injected into the pod via the ``AWS_EKS_CLUSTER_NAME`` env var.

Both paths build an in-memory :class:`kubernetes.client.Configuration`
and set it as the default; the parent class then drives every other
operation through the standard ``CoreV1Api`` / ``AppsV1Api`` /
``CustomObjectsApi``.

The cloud SDKs are optional: when ``boto3`` is not installed,
:meth:`is_available` returns ``False`` and routes degrade to 503.
"""
from __future__ import annotations

import base64
import logging
from typing import Any

from aqp.kubernetes.adapters.in_cluster import InClusterAdapter

logger = logging.getLogger(__name__)


class AwsEksAdapter(InClusterAdapter):
    """AWS EKS adapter built on the standard kubernetes-python-client."""

    adapter_kind = "aws_eks"
    adapter_alias = "AwsEksAdapter"

    def __init__(self) -> None:
        # Skip InClusterAdapter.__init__'s _load_config and run our own.
        self._loaded = False
        self._k8s_module = None
        self._cluster_name: str | None = None
        self._region: str | None = None
        try:
            self._load_config()
        except Exception as exc:  # noqa: BLE001
            logger.debug("AwsEksAdapter unavailable: %s", exc)

    def _load_config(self) -> None:  # type: ignore[override]
        try:
            import kubernetes as k8s  # type: ignore
        except ImportError:
            self._loaded = False
            return
        try:
            import boto3  # type: ignore
            from botocore.signers import RequestSigner  # type: ignore
        except ImportError:
            logger.info(
                "AwsEksAdapter requires boto3; install with 'pip install agentic-quant-platform[cloud-aws]'"
            )
            self._loaded = False
            return

        try:
            from aqp.config import settings

            cluster_name = (str(getattr(settings, "aws_eks_cluster_name", "") or "")).strip()
            region = (str(getattr(settings, "aws_region", "") or "")).strip()
        except Exception:
            cluster_name = ""
            region = ""

        if not cluster_name:
            logger.info("AwsEksAdapter: AQP_AWS_EKS_CLUSTER_NAME not set; disabled")
            self._loaded = False
            return

        try:
            eks = boto3.client("eks", region_name=region or None)
            described = eks.describe_cluster(name=cluster_name)["cluster"]
            endpoint = described["endpoint"]
            ca_bytes = base64.b64decode(described["certificateAuthority"]["data"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("AwsEksAdapter describe_cluster failed: %s", exc)
            self._loaded = False
            return

        # Build a presigned STS GetCallerIdentity URL — that's what
        # ``aws-iam-authenticator`` / ``aws eks get-token`` would
        # generate. The K8s API server uses it as a bearer token.
        try:
            session = boto3.session.Session()
            sts = session.client("sts", region_name=region or None)
            signer = RequestSigner(
                sts.meta.service_model.service_id,
                region or sts.meta.region_name,
                "sts",
                "v4",
                session.get_credentials(),
                session.events,
            )
            params = {
                "method": "GET",
                "url": (
                    "https://sts."
                    f"{region or sts.meta.region_name}"
                    ".amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15"
                ),
                "body": {},
                "headers": {"x-k8s-aws-id": cluster_name},
                "context": {},
            }
            signed_url = signer.generate_presigned_url(
                params,
                region_name=region or sts.meta.region_name,
                expires_in=60,
                operation_name="",
            )
            token = "k8s-aws-v1." + base64.urlsafe_b64encode(
                signed_url.encode("utf-8")
            ).decode("utf-8").rstrip("=")
        except Exception as exc:  # noqa: BLE001
            logger.warning("AwsEksAdapter token signing failed: %s", exc)
            self._loaded = False
            return

        # Write the CA cert to a temp file (the K8s client needs a file path).
        import tempfile

        ca_file = tempfile.NamedTemporaryFile(
            mode="wb", suffix="-eks-ca.pem", delete=False
        )
        try:
            ca_file.write(ca_bytes)
            ca_file.flush()
        finally:
            ca_file.close()

        configuration = k8s.client.Configuration()
        configuration.host = endpoint
        configuration.ssl_ca_cert = ca_file.name
        configuration.api_key = {"authorization": f"Bearer {token}"}
        k8s.client.Configuration.set_default(configuration)

        self._loaded = True
        self._k8s_module = k8s
        self._cluster_name = cluster_name
        self._region = region
        logger.info(
            "AwsEksAdapter loaded cluster=%s region=%s", cluster_name, region
        )

    def describe(self) -> dict[str, Any]:
        out = super().describe()
        out.update(
            {
                "cluster_name": self._cluster_name,
                "region": self._region,
            }
        )
        return out


__all__ = ["AwsEksAdapter"]
