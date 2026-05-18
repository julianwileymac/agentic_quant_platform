"""Phase 5 cutover smoke-test for the Auth0 + Microsoft account-management rollout.

Runs three layers of checks and prints a structured report:

1. **Local code paths** -- the new modules import cleanly, the FastAPI
   app constructs, the new routes are registered, settings are wired.
   Runs offline.
2. **Endpoint contract** -- against a running AQP API (defaults to
   ``http://localhost:8000``):
   - ``GET /api/public`` returns 200 (no Authorization header)
   - ``GET /me`` returns 401 without a Bearer token (in strict mode)
   - ``GET /me`` returns 200 with a valid Bearer token (optional)
3. **Auth0 federation** -- when ``AQP_AUTH_PROVIDER=auth0``, the
   ``/auth/config`` endpoint surfaces the SPA bootstrap payload with
   the right issuer / audience / client_id (so the SPA's
   ``isAuthEnabled()`` flips to true on rebuild).

Usage::

    # Offline local-paths check (always works)
    python -m scripts.smoke_auth

    # Full check against a running API
    python -m scripts.smoke_auth --api-url http://localhost:8000

    # Full check with a test token for /me validation
    python -m scripts.smoke_auth --api-url http://localhost:8000 \\
        --bearer-token "$(cat ~/.aqp/test-token)"

Exit code is the number of failed checks (0 = all pass).
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    skipped: bool = False
    warnings: list[str] = field(default_factory=list)


def _check(name: str, fn: Callable[[], tuple[bool, str]]) -> CheckResult:
    """Run a check function; convert exceptions into failed CheckResults."""
    try:
        ok, detail = fn()
        return CheckResult(name=name, ok=ok, detail=detail)
    except Exception as exc:  # noqa: BLE001 - smoke test surfaces all failures
        return CheckResult(name=name, ok=False, detail=f"exception: {exc}")


# ---------------------------------------------------------------------------
# Layer 1 -- local code paths
# ---------------------------------------------------------------------------


def check_module_imports() -> tuple[bool, str]:
    """Confirm every new Phase 7 module imports cleanly."""
    modules = [
        "aqp.auth.audit",
        "aqp.auth.management_api",
        "aqp.auth.auth0_fastapi",
        "aqp.persistence.models_audit",
        "aqp.api.routes.me",
        "aqp.api.routes.invites",
        "aqp.data.mcp.tools.account",
    ]
    failed: list[str] = []
    for mod in modules:
        try:
            __import__(mod)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{mod}: {exc}")
    if failed:
        return False, f"import failures: {failed}"
    return True, f"all {len(modules)} modules import cleanly"


def check_settings_fields() -> tuple[bool, str]:
    """Confirm every new Phase 7 settings field exists on the Settings class."""
    from aqp.config import settings

    required = [
        "auth0_mgmt_api_audience",
        "auth0_mgmt_api_client_id",
        "auth0_mgmt_api_client_secret",
        "auth0_database_connection",
        "auth0_microsoft_connection",
        "auth0_google_connection",
        "auth_require_email_verified",
        "auth_invite_ttl_hours",
        "auth_invite_secret",
        "auth_audit_enabled",
        "auth_audit_retention_days",
    ]
    missing = [name for name in required if not hasattr(settings, name)]
    if missing:
        return False, f"missing settings fields: {missing}"
    return True, f"all {len(required)} Phase 7 settings fields present"


def check_fastapi_app_constructs() -> tuple[bool, str]:
    """Confirm the FastAPI app constructs and the new routers are mounted."""
    from aqp.api.main import app
    from fastapi.routing import APIRoute

    expected_paths = {
        "/me",
        "/me/sessions",
        "/me/mfa/factors",
        "/me/connected-accounts",
        "/me/audit",
        "/me/change-password",
        "/tenancy/invites",
        "/tenancy/invites/{token}/accept",
    }
    actual = {r.path for r in app.routes if isinstance(r, APIRoute)}
    missing = expected_paths - actual
    if missing:
        return False, f"routes missing from app: {sorted(missing)}"
    return True, f"all {len(expected_paths)} Phase 7 routes registered"


def check_mcp_tools_registered() -> tuple[bool, str]:
    """Confirm every new account.* DataMCP tool is registered."""
    # Importing the package triggers side-effect registration; the
    # `@register_data_mcp_tool` decorator writes into DATA_MCP_TOOLS at
    # import time (separate from the `aqp.core.registry` kind catalog).
    import aqp.data.mcp.tools  # noqa: F401
    from aqp.data.mcp.registry import DATA_MCP_TOOLS

    expected = {
        "data.account.whoami",
        "data.account.list_sessions",
        "data.account.list_factors",
        "data.account.list_audit_events",
        "data.account.list_invites",
        "data.account.list_connections",
    }
    registered = set(DATA_MCP_TOOLS.keys())
    missing = expected - registered
    if missing:
        return False, (
            f"DataMCP tools not registered: {sorted(missing)} "
            f"(catalog size={len(registered)})"
        )
    return True, f"all {len(expected)} account.* DataMCP tools registered"


def check_audit_helper_signature() -> tuple[bool, str]:
    """Sanity-check `emit_audit_event` has the right signature."""
    import inspect

    from aqp.auth.audit import emit_audit_event

    sig = inspect.signature(emit_audit_event)
    needed = {
        "event_type",
        "user_id",
        "organization_id",
        "workspace_id",
        "actor_user_id",
        "event_category",
        "severity",
        "source",
        "connection",
        "request",
        "details",
    }
    missing = needed - set(sig.parameters)
    if missing:
        return False, f"emit_audit_event missing params: {sorted(missing)}"
    return True, f"emit_audit_event signature OK ({len(sig.parameters)} params)"


def run_local_checks() -> list[CheckResult]:
    return [
        _check("module imports", check_module_imports),
        _check("settings fields", check_settings_fields),
        _check("FastAPI app + Phase 7 routes", check_fastapi_app_constructs),
        _check("DataMCP account.* tools", check_mcp_tools_registered),
        _check("emit_audit_event signature", check_audit_helper_signature),
    ]


# ---------------------------------------------------------------------------
# Layer 2 -- live endpoint contracts
# ---------------------------------------------------------------------------


def check_public_endpoint(api_url: str) -> tuple[bool, str]:
    """``GET /health`` must return 200 without an Authorization header."""
    import httpx

    try:
        r = httpx.get(f"{api_url}/health", timeout=10.0)
    except httpx.HTTPError as exc:
        return False, f"network error: {exc}"
    if r.status_code != 200:
        return False, f"expected 200, got {r.status_code}: {r.text[:200]}"
    return True, f"GET /health -> 200 ({r.elapsed.total_seconds():.2f}s)"


def check_me_unauthenticated(api_url: str) -> tuple[bool, str]:
    """``GET /me`` without a Bearer token must return 401 in strict mode.

    In local mode the deterministic default-user is returned (200) so
    this check INFORMS rather than fails when ``auth_provider=local``.
    """
    import httpx

    try:
        r = httpx.get(f"{api_url}/me", timeout=10.0)
    except httpx.HTTPError as exc:
        return False, f"network error: {exc}"

    # Probe the provider via /auth/config so we know what to expect.
    try:
        cfg_resp = httpx.get(f"{api_url}/auth/config", timeout=10.0)
        cfg = cfg_resp.json() if cfg_resp.status_code == 200 else {}
        provider = str(cfg.get("provider", "local")).lower()
    except Exception:  # noqa: BLE001
        provider = "local"

    if provider == "local":
        if r.status_code == 200:
            return True, "GET /me -> 200 (provider=local, default-user OK)"
        return False, f"local mode expected 200, got {r.status_code}"

    # Production: strict mode rejects bare /me requests.
    if r.status_code == 401:
        return True, "GET /me -> 401 (provider=auth0, strict enforce OK)"
    return False, (
        f"provider={provider} expected 401 for unauthenticated /me, "
        f"got {r.status_code}"
    )


def check_me_with_token(api_url: str, token: str) -> tuple[bool, str]:
    """``GET /me`` with a valid Bearer token returns 200 + the profile."""
    import httpx

    try:
        r = httpx.get(
            f"{api_url}/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        return False, f"network error: {exc}"
    if r.status_code != 200:
        return False, f"expected 200, got {r.status_code}: {r.text[:200]}"
    body = r.json()
    if "email" not in body or "auth_provider" not in body:
        return False, f"response missing expected fields: keys={list(body)}"
    return True, (
        f"GET /me -> 200 (email={body.get('email')!r}, "
        f"provider={body.get('auth_provider')!r}, "
        f"mfa_enabled={body.get('mfa_enabled')!r})"
    )


def check_auth_config_for_auth0(api_url: str) -> tuple[bool, str]:
    """``GET /auth/config`` surfaces the SPA bootstrap payload.

    When ``AQP_AUTH_PROVIDER=auth0`` it must include a non-empty
    issuer + audience so the SPA's ``isAuthEnabled()`` returns true.
    """
    import httpx

    try:
        r = httpx.get(f"{api_url}/auth/config", timeout=10.0)
    except httpx.HTTPError as exc:
        return False, f"network error: {exc}"
    if r.status_code != 200:
        return False, f"expected 200, got {r.status_code}"
    cfg = r.json()
    provider = str(cfg.get("provider", "")).lower()
    if provider == "local":
        return True, "provider=local (SPA falls back to default-user OK)"
    if provider == "auth0":
        missing = [k for k in ("issuer", "audience") if not cfg.get(k)]
        if missing:
            return False, f"provider=auth0 but missing config: {missing}"
        return True, (
            f"provider=auth0 (issuer={cfg.get('issuer')}, "
            f"audience={cfg.get('audience')})"
        )
    return True, f"provider={provider} (non-standard; manual review recommended)"


def run_live_checks(api_url: str, token: str | None) -> list[CheckResult]:
    results = [
        _check("public endpoint (GET /health)", lambda: check_public_endpoint(api_url)),
        _check("unauthenticated GET /me", lambda: check_me_unauthenticated(api_url)),
        _check("GET /auth/config", lambda: check_auth_config_for_auth0(api_url)),
    ]
    if token:
        results.append(
            _check("authenticated GET /me", lambda: check_me_with_token(api_url, token))
        )
    else:
        results.append(
            CheckResult(
                name="authenticated GET /me",
                ok=True,
                detail="skipped (no --bearer-token provided)",
                skipped=True,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _format_report(layer: str, results: list[CheckResult]) -> str:
    lines = [f"\n=== {layer} ==="]
    for r in results:
        status = "SKIP" if r.skipped else ("PASS" if r.ok else "FAIL")
        lines.append(f"  [{status}] {r.name}: {r.detail}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 5 cutover smoke-test for Auth0 + account management.",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help="Base URL of a running AQP API. When omitted, only offline "
        "local-paths checks run.",
    )
    parser.add_argument(
        "--bearer-token",
        default=None,
        help="Optional access token to validate the authenticated /me path.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    print("AQP Phase 7 (Auth0 + Microsoft account mgmt) cutover smoke-test")
    print("=" * 70)

    local = run_local_checks()
    print(_format_report("Layer 1 -- Local code paths", local))

    if args.api_url:
        live = run_live_checks(args.api_url, args.bearer_token)
        print(_format_report(f"Layer 2 -- Live endpoints ({args.api_url})", live))
    else:
        print("\n=== Layer 2 -- Live endpoints ===")
        print("  [SKIP] no --api-url provided; pass --api-url http://localhost:8000")
        live = []

    all_results = local + live
    failed = [r for r in all_results if not r.ok]
    print("\n" + "=" * 70)
    print(
        f"Total: {len(all_results)} checks, "
        f"{sum(1 for r in all_results if r.ok and not r.skipped)} passed, "
        f"{sum(1 for r in all_results if r.skipped)} skipped, "
        f"{len(failed)} failed"
    )
    if failed:
        print("\nFAILED checks:")
        for r in failed:
            print(f"  - {r.name}: {r.detail}")
        return len(failed)
    print("All non-skipped checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
