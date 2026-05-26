"""Biscuit capability tokens for agent → MCP delegation.

Phase 5 §8.2 (RESTRUCTURING_PLAN.md). Sits ALONGSIDE the existing
:class:`aqp.auth.token_exchange.TokenExchangeBroker` (Rule 54),
not replacing it.

The pre-Phase-5 path:

  user JWT  ->  TokenExchangeBroker.exchange()
            ->  delegated agent JWT (broad scopes)
            ->  agent attaches Bearer to MCP HTTP request
            ->  MCP tool validates audience + scopes

That JWT carries every scope the agent could possibly need. If the
agent is compromised mid-run, the attacker reuses the JWT for any
of those scopes.

The Phase 5 §8.2 capability-attenuated path:

  user JWT  ->  TokenExchangeBroker.exchange()
            ->  delegated agent JWT (broad scopes)
            ->  Biscuit.from_delegated_jwt()        <-- mints biscuit
            ->  biscuit.attenuate(tool, args)       <-- per-call narrow
            ->  agent attaches X-Biscuit header
            ->  MCP tool validates biscuit + biscuit.tool == descriptor

Each per-call attenuation is one-way: the attenuated biscuit can
authorise EXACTLY the tool + args of this call and nothing broader.
A compromised agent that exfiltrates an attenuated biscuit can only
re-execute the one call that biscuit was minted for.

The implementation is OPTIONAL — when ``biscuit-python`` is not
installed (Windows dev, smoke tests, environments where the Rust
toolchain is unavailable), the helpers degrade to a logged warning
and the existing TokenExchangeBroker JWT remains the only delegation
mechanism. The Phase 5 wire-up is additive: biscuits ride alongside
the JWT, never instead of it.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BiscuitUnavailable(RuntimeError):
    """Raised when the ``biscuit-python`` package is not installed.

    Callers SHOULD catch this and fall back to the JWT-only path so
    Windows dev and Chainguard images that don't ship the Rust runtime
    keep working.
    """


class BiscuitVerificationError(RuntimeError):
    """Raised when a biscuit fails to verify against the loaded policy."""


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------


def _import_biscuit():
    """Import ``biscuit-python`` lazily; raise :class:`BiscuitUnavailable` if missing."""
    try:
        import biscuit_auth  # type: ignore[import-not-found]
    except ImportError as exc:
        raise BiscuitUnavailable(
            "biscuit-python is not installed; install the [auth] extra "
            "(linux/macOS only — Windows wheels are not published upstream)"
        ) from exc
    return biscuit_auth


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Capability:
    """One ``(tool, action, resource)`` capability the agent may exercise."""

    tool: str  # MCP tool name, e.g. "data.catalog.browse"
    action: str  # MCP action verb, e.g. "read", "write", "delete"
    resource: str  # canonical resource id, e.g. "iceberg:nyse:trades"
    descriptor_hash: str = ""  # Phase 5 §8.4 — SHA-256 of tool descriptor
    cell_id: str = ""  # Phase 5 §8.5 — cell binding


@dataclass(frozen=True)
class IssuedBiscuit:
    """A biscuit ready to attach to an outbound MCP request.

    ``token_b64`` is the base64-encoded biscuit (as produced by
    ``biscuit.to_base64()``). Attach via the ``X-Biscuit`` header on
    the MCP HTTP call.
    """

    token_b64: str
    user_sub: str
    agent_sub: str
    capabilities: tuple[Capability, ...]
    expires_at: float


# ---------------------------------------------------------------------------
# Mint
# ---------------------------------------------------------------------------


def mint_biscuit(
    *,
    user_sub: str,
    agent_sub: str,
    capabilities: Iterable[Capability],
    private_key_pem: str,
    ttl_seconds: int = 900,
    cell_id: str | None = None,
) -> IssuedBiscuit:
    """Mint a fresh biscuit for an agent run.

    Built from the broad-set capabilities the
    :class:`TokenExchangeBroker` already authorised. The biscuit
    carries the same delegation audit trail (``user_sub`` + ``agent_sub``)
    as the parent JWT plus the explicit capability list — the
    attenuation pipeline below narrows that list per-call.

    ``private_key_pem`` is the AQP control plane's biscuit signing
    key (PEM-encoded ed25519). In production it lives in Vault Transit;
    operators rotate via :class:`VaultStaticSecretStore` (Phase 4 §7.6).
    """
    biscuit_auth = _import_biscuit()
    if not capabilities:
        raise ValueError("mint_biscuit: capabilities must be non-empty")
    capabilities = tuple(capabilities)

    private_key = biscuit_auth.PrivateKey.from_hex(_pem_to_hex(private_key_pem))

    builder = biscuit_auth.BiscuitBuilder()
    builder.add_fact(f'user(\"{user_sub}\")')
    builder.add_fact(f'agent(\"{agent_sub}\")')
    if cell_id:
        builder.add_fact(f'cell(\"{cell_id}\")')

    expires_at = time.time() + max(60, ttl_seconds)
    builder.add_fact(f'time({int(expires_at)})')

    for cap in capabilities:
        builder.add_fact(
            f'capability(\"{cap.tool}\", \"{cap.action}\", '
            f'\"{cap.resource}\", \"{cap.descriptor_hash}\")'
        )
        if cap.cell_id:
            builder.add_fact(f'capability_cell(\"{cap.tool}\", \"{cap.cell_id}\")')

    builder.add_check(f'check if time($t), $t > {int(time.time())}')

    biscuit = builder.build(private_key)
    return IssuedBiscuit(
        token_b64=biscuit.to_base64(),
        user_sub=user_sub,
        agent_sub=agent_sub,
        capabilities=capabilities,
        expires_at=expires_at,
    )


# ---------------------------------------------------------------------------
# Attenuate
# ---------------------------------------------------------------------------


def attenuate_for_call(
    *,
    parent_b64: str,
    tool: str,
    action: str,
    resource: str,
    descriptor_hash: str,
    cell_id: str | None = None,
) -> str:
    """Narrow a biscuit to a single (tool, action, resource) call.

    Returns the base64-encoded attenuated biscuit. The MCP server
    verifies that:

    1. The attenuated biscuit chain ends in the call we're about to
       execute.
    2. The descriptor_hash matches the currently-registered tool's
       hash (Phase 5 §8.4).
    3. The cell binding (if any) matches the receiving cell.

    The attenuated biscuit can be replayed for the SAME call but
    cannot be widened — that's biscuit's core security property.
    """
    biscuit_auth = _import_biscuit()
    parent = biscuit_auth.Biscuit.from_base64(parent_b64)

    block = biscuit_auth.BlockBuilder()
    block.add_check(
        f'check if capability(\"{tool}\", \"{action}\", '
        f'\"{resource}\", \"{descriptor_hash}\")'
    )
    if cell_id:
        block.add_check(
            f'check if capability_cell(\"{tool}\", \"{cell_id}\")'
        )
    # Per-call expiry — 60s window even if the parent was 900s.
    block.add_check(
        f'check if time($t), $t > {int(time.time())}, $t < {int(time.time() + 60)}'
    )

    attenuated = parent.append(block)
    return attenuated.to_base64()


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerifiedBiscuit:
    """Result of a successful biscuit verification."""

    user_sub: str
    agent_sub: str
    cell_id: str | None
    capability: Capability


def verify_biscuit(
    *,
    token_b64: str,
    public_key_pem: str,
    expected_tool: str,
    expected_action: str,
    expected_resource: str,
    expected_descriptor_hash: str,
    expected_cell_id: str | None = None,
) -> VerifiedBiscuit:
    """Verify a biscuit against the expected (tool, action, resource).

    Raises :class:`BiscuitVerificationError` on any failure.

    The MCP server SHOULD call this at the entry point of every tool
    handler. The expected tuple comes from the route's static
    descriptor + the runtime cell id; the verifier rejects any biscuit
    that doesn't end with a matching capability check.
    """
    biscuit_auth = _import_biscuit()
    public_key = biscuit_auth.PublicKey.from_hex(_pem_to_hex(public_key_pem))

    try:
        parsed = biscuit_auth.Biscuit.from_base64(token_b64, public_key)
    except Exception as exc:  # noqa: BLE001
        raise BiscuitVerificationError(f"biscuit parse failed: {exc}") from exc

    authorizer = biscuit_auth.Authorizer()
    authorizer.add_token(parsed)
    # The authorizer's policy MUST allow ONLY the specific capability
    # we're checking; anything narrower the biscuit chained on top still
    # has to satisfy this rule too.
    authorizer.add_policy(
        f'allow if capability(\"{expected_tool}\", \"{expected_action}\", '
        f'\"{expected_resource}\", \"{expected_descriptor_hash}\")'
    )
    if expected_cell_id is not None:
        authorizer.add_check(
            f'check if cell(\"{expected_cell_id}\") '
            f'or capability_cell(\"{expected_tool}\", \"{expected_cell_id}\")'
        )
    authorizer.add_check(f'check if time($t), $t > {int(time.time())}')

    try:
        authorizer.authorize()
    except Exception as exc:  # noqa: BLE001
        raise BiscuitVerificationError(f"authorize failed: {exc}") from exc

    facts = _collect_facts(parsed)
    user_sub = facts.get("user", "")
    agent_sub = facts.get("agent", "")
    cell_id = facts.get("cell") or None
    return VerifiedBiscuit(
        user_sub=user_sub,
        agent_sub=agent_sub,
        cell_id=cell_id,
        capability=Capability(
            tool=expected_tool,
            action=expected_action,
            resource=expected_resource,
            descriptor_hash=expected_descriptor_hash,
            cell_id=expected_cell_id or "",
        ),
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _collect_facts(biscuit: Any) -> dict[str, str]:
    """Return ``{predicate: first_arg}`` for the biscuit's authority block.

    Only used for diagnostic output — the actual capability check
    happens via the Authorizer above.
    """
    out: dict[str, str] = {}
    try:
        for line in str(biscuit).splitlines():
            line = line.strip().rstrip(";")
            if not line or "(" not in line:
                continue
            pred, _, rest = line.partition("(")
            arg = rest.split(",", 1)[0].strip().strip('"')
            if pred and arg and pred not in out:
                out[pred] = arg
    except Exception:  # noqa: BLE001 - diagnostic only
        pass
    return out


def _pem_to_hex(pem: str) -> str:
    """Strip a PEM envelope to the bare hex-encoded key bytes.

    biscuit-python's ``PrivateKey.from_hex`` and ``PublicKey.from_hex``
    expect 64-char hex strings (32 bytes ed25519). Operators sometimes
    paste full PEM blocks; accept both shapes.
    """
    raw = pem.strip()
    if raw.startswith("-----BEGIN"):
        # Drop the BEGIN/END lines and decode the base64 body.
        import base64

        body = "\n".join(
            line for line in raw.splitlines() if not line.startswith("-----")
        )
        decoded = base64.b64decode(body)
        # Strip the SubjectPublicKeyInfo / PrivateKeyInfo prefix; ed25519
        # keys land in the last 32 bytes.
        return decoded[-32:].hex()
    return raw


__all__ = [
    "BiscuitUnavailable",
    "BiscuitVerificationError",
    "Capability",
    "IssuedBiscuit",
    "VerifiedBiscuit",
    "attenuate_for_call",
    "mint_biscuit",
    "verify_biscuit",
]
