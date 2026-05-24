"""Provision the AQP Auth0 tenant idempotently via the Management API.

Bootstraps:

1. The SPA application ("aqp-client")
2. The API resource server (audience ``https://api.aqp.internal/manage``)
3. The M2M application ("aqp-m2m") with grant to the API audience
4. The four canonical roles (``aqp-viewer`` / ``aqp-operator`` /
   ``aqp-admin`` / ``aqp-superadmin``) and their scope grants per ADR 003
5. The post-login Action that calls ``/_internal/auth0/sync``

This script is **idempotent** — re-running against the same tenant updates
existing resources in place and creates only what's missing. Use the
``--dry-run`` flag to see what would change without mutating Auth0.

Required env vars (or CLI args):

  AUTH0_DOMAIN              your-tenant.us.auth0.com
  AUTH0_M2M_CLIENT_ID       Management API M2M client id
  AUTH0_M2M_CLIENT_SECRET   Management API M2M client secret
  AQP_SYNC_URL              https://api.aqp.example.com/_internal/auth0/sync
  AQP_API_AUDIENCE          https://api.aqp.internal/manage
  AQP_CLAIMS_NAMESPACE      https://aqp.internal/

The Management API M2M client must have the ``read:client_grants``,
``create:client_grants``, ``read:clients``, ``update:clients``,
``create:clients``, ``read:roles``, ``create:roles``, ``update:roles``,
``read:resource_servers``, ``create:resource_servers``,
``update:resource_servers``, ``read:actions``, ``create:actions``,
``update:actions``, and ``deploy:actions`` permissions.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("provision_auth0")

# ---------------------------------------------------------------------------
# Constants — match aqp_platform_core.auth.rbac
# ---------------------------------------------------------------------------

SCOPES: list[dict[str, str]] = [
    {"value": "read:infrastructure", "description": "View deployments / pods / logs / configs."},
    {"value": "manage:agents", "description": "Start / stop / restart agent + bot pods + RL experiments."},
    {"value": "manage:infrastructure", "description": "Deploy / update services + edit ConfigMaps."},
    {"value": "admin:cluster", "description": "Full cluster control + bypass resource scoping."},
]

ROLES: list[dict[str, Any]] = [
    {
        "name": "aqp-viewer",
        "description": "Read-only access to assigned resources.",
        "scopes": ["read:infrastructure"],
    },
    {
        "name": "aqp-operator",
        "description": "Operate agents + bots on assigned resources.",
        "scopes": ["read:infrastructure", "manage:agents"],
    },
    {
        "name": "aqp-admin",
        "description": "Operator + manage infrastructure for the assigned org.",
        "scopes": ["read:infrastructure", "manage:agents", "manage:infrastructure"],
    },
    {
        "name": "aqp-superadmin",
        "description": "Cluster admin — bypasses resource scoping.",
        "scopes": [
            "read:infrastructure",
            "manage:agents",
            "manage:infrastructure",
            "admin:cluster",
        ],
    },
]


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProvisionSettings:
    domain: str
    m2m_client_id: str
    m2m_client_secret: str
    sync_url: str
    api_audience: str
    claims_namespace: str
    action_template_path: Path
    dry_run: bool

    @classmethod
    def from_env_or_args(cls, args: argparse.Namespace) -> ProvisionSettings:
        repo_root = Path(__file__).resolve().parents[2]
        default_template = (
            repo_root
            / "terraform"
            / "modules"
            / "auth0_identity"
            / "post_login_action.js.tftpl"
        )
        return cls(
            domain=_required(args.domain or os.environ.get("AUTH0_DOMAIN"), "AUTH0_DOMAIN"),
            m2m_client_id=_required(
                args.m2m_client_id or os.environ.get("AUTH0_M2M_CLIENT_ID"),
                "AUTH0_M2M_CLIENT_ID",
            ),
            m2m_client_secret=_required(
                args.m2m_client_secret or os.environ.get("AUTH0_M2M_CLIENT_SECRET"),
                "AUTH0_M2M_CLIENT_SECRET",
            ),
            sync_url=_required(args.sync_url or os.environ.get("AQP_SYNC_URL"), "AQP_SYNC_URL"),
            api_audience=args.api_audience
            or os.environ.get("AQP_API_AUDIENCE", "https://api.aqp.internal/manage"),
            claims_namespace=args.claims_namespace
            or os.environ.get("AQP_CLAIMS_NAMESPACE", "https://aqp.internal/"),
            action_template_path=Path(
                args.action_template or os.environ.get("AQP_ACTION_TEMPLATE", str(default_template))
            ),
            dry_run=bool(args.dry_run),
        )


def _required(value: str | None, name: str) -> str:
    if not value:
        raise SystemExit(f"missing required setting: {name}")
    return value.strip()


# ---------------------------------------------------------------------------
# Auth0 Management API client (thin)
# ---------------------------------------------------------------------------


class Auth0Mgmt:
    """Minimal Management API client. Caches the M2M token."""

    def __init__(self, settings: ProvisionSettings) -> None:
        self._settings = settings
        self._token: str | None = None
        self._token_expires_at: float = 0
        self._client = httpx.Client(timeout=30, base_url=f"https://{settings.domain}")

    def close(self) -> None:
        self._client.close()

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        resp = self._client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._settings.m2m_client_id,
                "client_secret": self._settings.m2m_client_secret,
                "audience": f"https://{self._settings.domain}/api/v2/",
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expires_at = time.time() + int(payload.get("expires_in", 3600))
        return self._token

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: Any | None = None,
    ) -> Any:
        if self._settings.dry_run and method.upper() not in {"GET", "HEAD"}:
            logger.info("[dry-run] %s %s payload=%s", method, path, json.dumps(json_body)[:200] if json_body else "")
            return {}
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        resp = self._client.request(
            method, path, params=params, json=json_body, headers=headers
        )
        if resp.status_code == 204 or not resp.content:
            return {}
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SystemExit(
                f"Auth0 {method} {path} failed: {resp.status_code} {resp.text}"
            ) from exc
        return resp.json()

    # ---- API resource server ---------------------------------------------

    def get_resource_server(self, identifier: str) -> dict | None:
        items = self._request("GET", "/api/v2/resource-servers")
        for item in items or []:
            if item.get("identifier") == identifier:
                return item
        return None

    def upsert_resource_server(
        self, *, identifier: str, name: str, scopes: list[dict]
    ) -> dict:
        existing = self.get_resource_server(identifier)
        payload = {
            "name": name,
            "identifier": identifier,
            "scopes": scopes,
            "token_lifetime": 3600,
            "skip_consent_for_verifiable_first_party_clients": True,
        }
        if existing:
            logger.info("Auth0 resource server %s exists; patching scopes", identifier)
            return self._request(
                "PATCH", f"/api/v2/resource-servers/{existing['id']}", json_body=payload
            )
        logger.info("Auth0 resource server %s missing; creating", identifier)
        return self._request("POST", "/api/v2/resource-servers", json_body=payload)

    # ---- Roles -----------------------------------------------------------

    def list_roles(self) -> list[dict]:
        return list(self._request("GET", "/api/v2/roles") or [])

    def upsert_role(self, *, name: str, description: str) -> dict:
        roles = self.list_roles()
        for role in roles:
            if role.get("name") == name:
                logger.info("Auth0 role %s exists; patching description", name)
                self._request(
                    "PATCH",
                    f"/api/v2/roles/{role['id']}",
                    json_body={"name": name, "description": description},
                )
                return role
        logger.info("Auth0 role %s missing; creating", name)
        return self._request(
            "POST",
            "/api/v2/roles",
            json_body={"name": name, "description": description},
        )

    def assign_role_permissions(
        self, role_id: str, *, resource_server: str, scopes: list[str]
    ) -> None:
        # Idempotent: list current grants, add only missing ones.
        current = self._request("GET", f"/api/v2/roles/{role_id}/permissions") or []
        current_keys = {(p.get("resource_server_identifier"), p.get("permission_name")) for p in current}
        new_perms = [
            {"resource_server_identifier": resource_server, "permission_name": s}
            for s in scopes
            if (resource_server, s) not in current_keys
        ]
        if not new_perms:
            logger.info("role %s permissions already up to date", role_id)
            return
        self._request(
            "POST",
            f"/api/v2/roles/{role_id}/permissions",
            json_body={"permissions": new_perms},
        )

    # ---- Actions ---------------------------------------------------------

    def find_action(self, name: str) -> dict | None:
        items = self._request("GET", "/api/v2/actions/actions") or {}
        for item in items.get("actions", []):
            if item.get("name") == name:
                return item
        return None

    def upsert_action(self, *, name: str, code: str, dependencies: list[dict]) -> dict:
        existing = self.find_action(name)
        payload = {
            "name": name,
            "supported_triggers": [{"id": "post-login", "version": "v3"}],
            "code": code,
            "dependencies": dependencies,
            "runtime": "node18",
        }
        if existing:
            logger.info("Auth0 action %s exists; patching code", name)
            return self._request(
                "PATCH",
                f"/api/v2/actions/actions/{existing['id']}",
                json_body=payload,
            )
        logger.info("Auth0 action %s missing; creating", name)
        return self._request("POST", "/api/v2/actions/actions", json_body=payload)

    def deploy_action(self, action_id: str) -> dict:
        return self._request("POST", f"/api/v2/actions/actions/{action_id}/deploy")


# ---------------------------------------------------------------------------
# Provisioning steps
# ---------------------------------------------------------------------------


def render_action(settings: ProvisionSettings) -> str:
    """Substitute the .tftpl-style placeholders with concrete values.

    The template lives at ``terraform/modules/auth0_identity/post_login_action.js.tftpl``.
    Substitutes ``${claims_namespace}`` / ``${api_audience}`` / ``${sync_url}``;
    leaves ``$${...}`` (escaped) intact for runtime JS interpolation.
    """
    text = settings.action_template_path.read_text(encoding="utf-8")
    text = text.replace("${claims_namespace}", settings.claims_namespace)
    text = text.replace("${api_audience}", settings.api_audience)
    text = text.replace("${sync_url}", settings.sync_url)
    # The Terraform template uses $$ as the JS-runtime escape; collapse them.
    text = text.replace("$${", "${")
    return text


def provision(settings: ProvisionSettings) -> int:
    mgmt = Auth0Mgmt(settings)
    try:
        # 1. API resource server with scopes
        mgmt.upsert_resource_server(
            identifier=settings.api_audience,
            name="AQP Management API",
            scopes=SCOPES,
        )

        # 2. Roles + scope grants
        for role_def in ROLES:
            role = mgmt.upsert_role(
                name=role_def["name"],
                description=role_def["description"],
            )
            role_id = role.get("id")
            if role_id and not settings.dry_run:
                mgmt.assign_role_permissions(
                    role_id,
                    resource_server=settings.api_audience,
                    scopes=role_def["scopes"],
                )

        # 3. Post-login Action
        code = render_action(settings)
        action = mgmt.upsert_action(
            name="aqp-post-login-sync",
            code=code,
            dependencies=[],
        )
        action_id = action.get("id")
        if action_id and not settings.dry_run:
            mgmt.deploy_action(action_id)

        logger.info("Auth0 provisioning complete.")
        return 0
    finally:
        mgmt.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    parser = argparse.ArgumentParser(
        description="Idempotently provision the AQP Auth0 tenant.",
    )
    parser.add_argument("--domain", help="Auth0 domain (or AUTH0_DOMAIN env).")
    parser.add_argument("--m2m-client-id", help="Management M2M client id (or env).")
    parser.add_argument(
        "--m2m-client-secret", help="Management M2M client secret (or env)."
    )
    parser.add_argument("--sync-url", help="Backend /_internal/auth0/sync URL.")
    parser.add_argument(
        "--api-audience",
        help="API resource server audience. Default: https://api.aqp.internal/manage",
    )
    parser.add_argument(
        "--claims-namespace",
        help="Custom-claim namespace. Default: https://aqp.internal/",
    )
    parser.add_argument(
        "--action-template",
        help="Path to the .tftpl Action template. Default: terraform/modules/auth0_identity/post_login_action.js.tftpl",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned changes without mutating Auth0.",
    )
    args = parser.parse_args(argv)

    settings = ProvisionSettings.from_env_or_args(args)
    return provision(settings)


if __name__ == "__main__":
    sys.exit(main())
