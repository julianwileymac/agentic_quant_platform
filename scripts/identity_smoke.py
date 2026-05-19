"""End-to-end smoke for the IdentityProvider abstraction.

Run inside the api/worker container::

    docker exec aqp-api python -m scripts.identity_smoke

The script exercises the full login -> callback -> token-set flow
against the :class:`MockProvider` (the only provider that runs without
a real IdP). It also walks the M2M issuer surface so the operator can
verify the resolver chain picks up M2M tokens when the toggle is on.

This is a diagnostic + validation tool. It always uses the in-process
:class:`MockProvider` regardless of ``AQP_AUTH_PROVIDER`` so the smoke
output is deterministic.

Per the Management Engine subagent rule
(``.cursor/rules/aqp-management-engine.mdc``) this script NEVER prints
raw token prefixes. The ``--unsafe-print-token-prefixes`` flag is a
hard opt-in for local debugging only; in CI / shared-transcript
environments the redacted output keeps tokens out of audit logs.
"""
from __future__ import annotations

import argparse
import sys
from urllib.parse import parse_qs, urlparse

from aqp.auth.m2m import M2MTokenIssuer
from aqp.auth.pkce import generate_code_challenge, generate_code_verifier
from aqp.auth.providers import (
    IdentityProviderConfig,
    MockProvider,
    register_provider,
    reset_active_provider,
)


_PRINT_TOKEN_PREFIXES = False


def _safe_token(value: str | None) -> str:
    """Return ``"<redacted>"`` unless the operator opted in with the flag."""
    if not value:
        return "<empty>"
    if _PRINT_TOKEN_PREFIXES:
        return f"{value[:4]}…"
    return "<redacted>"


def _print_header(title: str) -> None:
    print()
    print("=" * len(title))
    print(title)
    print("=" * len(title))


def main() -> int:
    _print_header("Provider")
    reset_active_provider()
    provider = MockProvider(
        IdentityProviderConfig(
            issuer="http://mock-idp.local",
            audience="aqp-mock-api",
            client_id="aqp-mock-client",
            client_secret="aqp-mock-secret",
            logout_callback="http://localhost/done",
        )
    )
    register_provider(provider)
    print(provider.describe())

    _print_header("Discovery")
    discovery = provider.discovery()
    for key in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"):
        print(f"  {key}: {discovery.get(key)}")

    _print_header("PKCE login URL")
    verifier = generate_code_verifier()
    challenge = generate_code_challenge(verifier)
    state = "smoke-state-123"
    redirect_uri = "http://localhost/callback"
    login_url = provider.login_url(
        redirect_uri=redirect_uri,
        state=state,
        code_challenge=challenge,
    )
    parsed = urlparse(login_url)
    print(f"  endpoint: {parsed.scheme}://{parsed.netloc}{parsed.path}")
    qs = parse_qs(parsed.query)
    for key in ("client_id", "redirect_uri", "state", "code_challenge", "code_challenge_method"):
        print(f"  {key}: {qs.get(key, ['<missing>'])[0]}")

    _print_header("exchange_code -> token set")
    tokens = provider.exchange_code(
        code="sample-auth-code",
        redirect_uri=redirect_uri,
        code_verifier=verifier,
    )
    print(f"  access_token:  {_safe_token(tokens.access_token)}")
    print(f"  id_token:      {_safe_token(tokens.id_token)}")
    print(f"  refresh_token: {_safe_token(tokens.refresh_token)}")
    print(f"  expires_in:    {tokens.expires_in}")
    print(f"  scope:         {tokens.scope}")

    _print_header("refresh -> rotate")
    refreshed = provider.refresh(tokens.refresh_token or "")
    print(f"  rotated:       {_safe_token(refreshed.access_token)}")

    _print_header("logout URL")
    logout = provider.logout_url(return_to="http://localhost/done")
    print(f"  {logout}")

    _print_header("M2M token (mock)")
    issuer = M2MTokenIssuer(provider=provider)
    polaris = issuer.token_for("polaris", purpose="oauth")
    if polaris is None:
        print("  <m2m disabled or no audience>")
    else:
        print(
            f"  audience=polaris  access_token={_safe_token(polaris.access_token)}  "
            f"ttl={polaris.expires_in}s"
        )

    print()
    print("[OK] identity_smoke passed")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--unsafe-print-token-prefixes",
        action="store_true",
        help=(
            "Print the first 4 characters of every minted token. NEVER pass "
            "this in CI or shared transcripts — only local one-off debugging."
        ),
    )
    args = parser.parse_args()
    _PRINT_TOKEN_PREFIXES = bool(args.unsafe_print_token_prefixes)
    sys.exit(main())
