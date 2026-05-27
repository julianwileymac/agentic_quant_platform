"""Round-trip an Entra ID login + verify the resulting access token.

Workstream "Entra internal tenant"
(docs/plans/entra-internal-tenant-rollout.md). Boots an MSAL
``initiate_auth_code_flow`` against the AQP staff tenant, opens the
authorize URL in the operator's browser, exchanges the resulting code,
and validates the access token's claims against the canonical AQP
expectations:

- ``iss`` matches ``settings.auth_msal_internal_authority + /v2.0``
- ``aud`` matches ``settings.auth_msal_internal_audience``
- the configured role claim is present and non-empty
- the configured CA policy display names exist in the tenant (queried
  via Microsoft Graph using the same access token)

The script never persists the token. It prints redacted summaries
(first 4 chars of the JWT) and the parsed claims; the raw token never
hits stdout.

Usage:

    # Interactive — opens the browser.
    python scripts/identity/verify_entra_login.py

    # Headless / device-code (for SSH sessions).
    python scripts/identity/verify_entra_login.py --device-code
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import webbrowser
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger("verify_entra_login")


def _redact(token: str) -> str:
    if not token:
        return "<empty>"
    return f"{token[:4]}\u2026 ({len(token)} chars)"


def _decode_jwt(token: str) -> dict:
    import base64

    parts = token.split(".")
    if len(parts) != 3:
        return {}
    body = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(body))
    except Exception:  # noqa: BLE001 - defensive
        return {}


def _validate_claims(token: str) -> tuple[bool, list[str]]:
    from aqp.config import settings  # type: ignore[import-not-found]

    claims = _decode_jwt(token)
    errors: list[str] = []

    expected_iss = (
        f"https://login.microsoftonline.com/"
        f"{(settings.auth_msal_internal_tenant_id or '').strip()}/v2.0"
    )
    actual_iss = str(claims.get("iss") or "").rstrip("/")
    if expected_iss.rstrip("/") != actual_iss:
        errors.append(
            f"iss mismatch: expected {expected_iss!r}, got {actual_iss!r}"
        )

    expected_aud = (settings.auth_msal_internal_audience or "").strip()
    actual_aud = claims.get("aud")
    if expected_aud and expected_aud not in (actual_aud, [actual_aud]):
        if not (isinstance(actual_aud, list) and expected_aud in actual_aud):
            errors.append(
                f"aud mismatch: expected {expected_aud!r}, got {actual_aud!r}"
            )

    role_claim = (settings.auth_msal_app_role_claim or "roles").strip()
    roles = claims.get(role_claim)
    if not roles:
        errors.append(
            f"role claim {role_claim!r} missing or empty (got {roles!r})"
        )

    return len(errors) == 0, errors


def _check_ca_policies(access_token: str) -> tuple[list[str], list[str]]:
    """Query Microsoft Graph for CA policies; return (found, missing)."""
    from aqp.config import settings  # type: ignore[import-not-found]

    raw = (settings.auth_msal_required_ca_policies or "").strip()
    expected = [n.strip() for n in raw.split(",") if n.strip()]
    if not expected:
        return [], []

    import httpx  # type: ignore[import-not-found]

    try:
        response = httpx.get(
            "https://graph.microsoft.com/v1.0/identity/conditionalAccess/policies",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("CA policy query failed: %s", exc)
        return [], expected

    body = response.json()
    found_names = {
        str(p.get("displayName") or "")
        for p in body.get("value", [])
    }
    found = [n for n in expected if n in found_names]
    missing = [n for n in expected if n not in found_names]
    return found, missing


def _interactive(device_code: bool) -> int:
    import msal  # type: ignore[import-not-found]

    from aqp.config import settings  # type: ignore[import-not-found]

    tenant_id = (settings.auth_msal_internal_tenant_id or "").strip()
    client_id = (settings.auth_msal_internal_app_id or "").strip()
    audience = (settings.auth_msal_internal_audience or "").strip()
    if not (tenant_id and client_id and audience):
        logger.error(
            "AQP_AUTH_MSAL_INTERNAL_TENANT_ID + INTERNAL_APP_ID + "
            "INTERNAL_AUDIENCE must all be set"
        )
        return 1

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.PublicClientApplication(client_id, authority=authority)
    scopes = [f"{audience}/.default"]

    if device_code:
        flow = app.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            logger.error("device flow init failed: %s", flow)
            return 2
        print(flow["message"])
        result = app.acquire_token_by_device_flow(flow)
    else:
        # Browser flow — port 0 lets the OS pick a free port.
        result = app.acquire_token_interactive(scopes=scopes, port=0)

    if "access_token" not in result:
        logger.error(
            "token acquisition failed: %s",
            json.dumps(result, indent=2, default=str),
        )
        return 2

    token = result["access_token"]
    logger.info("Got access token: %s", _redact(token))

    ok, errors = _validate_claims(token)
    if not ok:
        for err in errors:
            logger.error(err)
        return 3
    logger.info("Claims look correct.")

    found, missing = _check_ca_policies(token)
    if found:
        logger.info("CA policies found: %s", ", ".join(found))
    if missing:
        logger.warning(
            "CA policies declared in AQP_AUTH_MSAL_REQUIRED_CA_POLICIES "
            "but NOT found in tenant: %s",
            ", ".join(missing),
        )
        return 4

    logger.info("All checks passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_entra_login",
        description="Round-trip an Entra login + validate claims + CA policies.",
    )
    parser.add_argument(
        "--device-code",
        action="store_true",
        help="Use device-code flow instead of opening a browser.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return _interactive(device_code=args.device_code)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
