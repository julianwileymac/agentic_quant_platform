"""Sync Auth0 settings from `.env` into Kubernetes auth manifests.

This script deliberately separates tracked config from local secret material:

- tracked:
  - deployments/kubernetes/base/configmaps/aqp-config.yaml
  - deployments/kubernetes/base/configmaps/aqp-admin-config.yaml
  - deployments/kubernetes/base/secrets/*.yaml.template (placeholders only)
- ignored:
  - deployments/kubernetes/generated/aqp-secrets.local.yaml
  - deployments/kubernetes/generated/aqp-admin-secrets.local.yaml

It never prints raw secret values. The generated files under
`deployments/kubernetes/generated/` are git-ignored because Kubernetes Secret
`data` fields are only base64-encoded, not encrypted.
"""
from __future__ import annotations

import argparse
import base64
import secrets
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV = REPO_ROOT / ".env"
CONFIGMAP_PATH = REPO_ROOT / "deployments" / "kubernetes" / "base" / "configmaps" / "aqp-config.yaml"
ADMIN_CONFIGMAP_PATH = (
    REPO_ROOT / "deployments" / "kubernetes" / "base" / "configmaps" / "aqp-admin-config.yaml"
)
SECRET_TEMPLATE_PATH = (
    REPO_ROOT / "deployments" / "kubernetes" / "base" / "secrets" / "aqp-secrets.yaml.template"
)
ADMIN_SECRET_TEMPLATE_PATH = (
    REPO_ROOT / "deployments" / "kubernetes" / "base" / "secrets" / "aqp-admin-secrets.yaml.template"
)
GENERATED_DIR = REPO_ROOT / "deployments" / "kubernetes" / "generated"

DEFAULT_AUDIENCE = "https://api.aqp.internal/manage"
DEFAULT_CLAIMS_NAMESPACE = "https://aqp.internal/"


def parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _domain_to_issuer(domain: str) -> str:
    domain = domain.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    return f"https://{domain}/" if domain else ""


def derive_values(env: dict[str, str]) -> tuple[dict[str, str], dict[str, str], list[str]]:
    warnings: list[str] = []
    domain = env.get("AQP_AUTH0_DOMAIN") or env.get("AUTH0_DOMAIN") or env.get("VITE_AUTH0_DOMAIN") or ""
    issuer = env.get("AQP_AUTH_OIDC_ISSUER") or _domain_to_issuer(domain)
    audience = (
        env.get("AQP_AUTH_OIDC_AUDIENCE")
        or env.get("AQP_AUTH_M2M_AUDIENCE")
        or env.get("AUTH0_AUDIENCE")
        or DEFAULT_AUDIENCE
    )
    client_id = (
        env.get("AQP_AUTH_OIDC_CLIENT_ID")
        or env.get("VITE_AUTH0_CLIENT_ID")
        or env.get("AUTH0_CLIENT_ID")
        or ""
    )
    client_secret = env.get("AQP_AUTH_OIDC_CLIENT_SECRET") or env.get("AUTH0_CLIENT_SECRET") or ""
    m2m_client_id = env.get("AQP_AUTH_M2M_CLIENT_ID") or ""
    m2m_secret = env.get("AQP_AUTH_M2M_CLIENT_SECRET") or ""
    scim_hash = env.get("AQP_AUTH_SCIM_BEARER_TOKEN_HASH") or ""
    session_secret = env.get("AQP_SESSION_COOKIE_SECRET") or secrets.token_urlsafe(64)

    if not domain:
        warnings.append("AUTH0_DOMAIN missing; VITE_AUTH0_DOMAIN and issuer will remain empty.")
    if not client_id:
        warnings.append("AUTH0_CLIENT_ID missing; SPA login cannot be enabled.")
    if not client_secret:
        warnings.append("AUTH0_CLIENT_SECRET missing; backend confidential/M2M fallback remains unset.")
    if not m2m_client_id or not m2m_secret:
        warnings.append(
            "AQP_AUTH_M2M_CLIENT_ID/AQP_AUTH_M2M_CLIENT_SECRET missing; "
            "Auth0 Action sync must use a dedicated M2M app before production."
        )
    if not scim_hash:
        warnings.append("AQP_AUTH_SCIM_BEARER_TOKEN_HASH missing; SCIM remains disabled/unusable.")

    plain = {
        "AQP_AUTH_PROVIDER": "auth0",
        "AQP_AUTH_ENFORCE": "strict",
        "AQP_AUTH_OIDC_ISSUER": issuer,
        "AQP_AUTH_OIDC_AUDIENCE": audience,
        "AQP_AUTH_OIDC_CLIENT_ID": client_id,
        "AQP_AUTH_M2M_CLIENT_ID": m2m_client_id,
        "AQP_AUTH_M2M_AUDIENCE": audience,
        "AQP_AUTH_CLAIMS_NAMESPACE": DEFAULT_CLAIMS_NAMESPACE,
        "AQP_AUTH_SCIM_ENABLED": "true" if scim_hash else "false",
        "VITE_AUTH_REQUIRED": "true",
        "VITE_AUTH0_DOMAIN": domain,
        "VITE_AUTH0_CLIENT_ID": client_id,
        "VITE_AUTH0_AUDIENCE": audience,
    }
    secret = {
        # Only include populated secrets in the ignored generated files.
        "AQP_AUTH_OIDC_CLIENT_SECRET": client_secret,
        "AQP_AUTH_M2M_CLIENT_SECRET": m2m_secret,
        "AQP_AUTH_SCIM_BEARER_TOKEN_HASH": scim_hash,
        "AQP_SESSION_COOKIE_SECRET": session_secret,
    }
    return plain, secret, warnings


def load_yaml(path: Path) -> dict[str, Any]:
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def write_yaml(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def upsert_configmap(path: Path, *, namespace: str, values: dict[str, str]) -> None:
    doc = load_yaml(path) or {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "aqp-config"},
        "data": {},
    }
    doc.setdefault("apiVersion", "v1")
    doc["kind"] = "ConfigMap"
    metadata = doc.setdefault("metadata", {})
    metadata["name"] = "aqp-config"
    metadata["namespace"] = namespace
    metadata.setdefault("labels", {})
    metadata["labels"].setdefault("app.kubernetes.io/part-of", "aqp")
    data = doc.setdefault("data", {})
    data.update(values)
    write_yaml(path, doc)


def secret_template(*, namespace: str, include_admin_note: bool = False) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "aqp-secrets",
            "namespace": namespace,
            "labels": {
                "app.kubernetes.io/part-of": "aqp",
                "app.kubernetes.io/managed-by": "generate-config",
            },
            "annotations": {
                "aqp.internal/template": "true",
                "aqp.internal/note": (
                    "Placeholder values only. Real secret manifests are rendered to "
                    "deployments/kubernetes/generated/ and are git-ignored."
                ),
            },
        },
        "type": "Opaque",
        "data": {
            "AQP_AUTH_OIDC_CLIENT_SECRET": "Y2hhbmdlbWU=",
            "AQP_AUTH_M2M_CLIENT_SECRET": "Y2hhbmdlbWU=",
            "AQP_AUTH_SCIM_BEARER_TOKEN_HASH": "Y2hhbmdlbWU=",
            "AQP_SESSION_COOKIE_SECRET": "Y2hhbmdlbWU=",
        },
    }


def write_secret_template(path: Path, *, namespace: str) -> None:
    write_yaml(path, secret_template(namespace=namespace))


def write_generated_secret(path: Path, *, namespace: str, secrets_map: dict[str, str]) -> None:
    data = {k: b64(v) for k, v in secrets_map.items() if v}
    doc = secret_template(namespace=namespace)
    doc["metadata"]["annotations"]["aqp.internal/template"] = "false"
    doc["metadata"]["annotations"]["aqp.internal/note"] = (
        "Generated from local .env; git-ignored because it contains base64-encoded secrets."
    )
    doc["data"] = data
    write_yaml(path, doc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--no-generated-secret", action="store_true")
    args = parser.parse_args(argv)

    env = parse_env(args.env_file)
    plain, secret, warnings = derive_values(env)

    upsert_configmap(CONFIGMAP_PATH, namespace="aqp", values=plain)
    upsert_configmap(ADMIN_CONFIGMAP_PATH, namespace="aqp-admin", values=plain)
    write_secret_template(SECRET_TEMPLATE_PATH, namespace="aqp")
    write_secret_template(ADMIN_SECRET_TEMPLATE_PATH, namespace="aqp-admin")

    if not args.no_generated_secret:
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        write_generated_secret(GENERATED_DIR / "aqp-secrets.local.yaml", namespace="aqp", secrets_map=secret)
        write_generated_secret(
            GENERATED_DIR / "aqp-admin-secrets.local.yaml",
            namespace="aqp-admin",
            secrets_map=secret,
        )

    print("[sync_auth0_env_to_k8s] updated tracked ConfigMap/Secret templates")
    if not args.no_generated_secret:
        print("[sync_auth0_env_to_k8s] wrote git-ignored generated Secret manifests")
    for warning in warnings:
        print(f"[sync_auth0_env_to_k8s] warning: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
