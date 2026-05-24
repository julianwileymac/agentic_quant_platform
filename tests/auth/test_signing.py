"""Ed25519 lineage signer tests (Workstream C).

Round-trip sign + verify against deterministic payloads, exercise the
three signing modes (off / permissive / strict), confirm key rotation
keeps old signatures verifiable, and prove the canonical encoding is
stable across runs.
"""
from __future__ import annotations

import base64

import pytest


def _cryptography_available() -> bool:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: F401
            Ed25519PrivateKey,
        )

        return True
    except Exception:  # noqa: BLE001
        return False


def _make_credential_for_actor(monkeypatch: pytest.MonkeyPatch, fields: dict) -> None:
    """Patch ``CredentialResolver.resolve`` to return ``fields``."""
    from types import SimpleNamespace

    from aqp.credentials import resolver as resolver_mod

    def fake_resolve(key, *args, **kwargs):
        return SimpleNamespace(fields=dict(fields), source="test")

    monkeypatch.setattr(
        resolver_mod.CredentialResolver,
        "resolve",
        lambda self, key, **kw: SimpleNamespace(fields=dict(fields), source="test"),
        raising=False,
    )


# ---------------------------------------------------------------------------
# Canonical encoding
# ---------------------------------------------------------------------------


def test_canonical_payload_is_stable_across_orderings() -> None:
    from aqp.auth.signing import canonical_transform_payload

    p1 = canonical_transform_payload(
        job_name="ingest.foo",
        run_id="run-1",
        code_version="v1",
        parameters={"b": 2, "a": 1},
        input_hashes=["aaa", "bbb"],
        output_hashes=["ccc"],
    )
    p2 = canonical_transform_payload(
        job_name="ingest.foo",
        run_id="run-1",
        code_version="v1",
        parameters={"a": 1, "b": 2},
        input_hashes=["bbb", "aaa"],
        output_hashes=["ccc"],
    )
    assert p1 == p2
    # 32-byte SHA-256 digest.
    assert len(p1) == 32


def test_canonical_payload_changes_with_inputs() -> None:
    from aqp.auth.signing import canonical_transform_payload

    p1 = canonical_transform_payload(
        job_name="x",
        run_id="r",
        code_version="v1",
        parameters={"a": 1},
        input_hashes=["a"],
        output_hashes=["b"],
    )
    p2 = canonical_transform_payload(
        job_name="x",
        run_id="r",
        code_version="v1",
        parameters={"a": 1},
        input_hashes=["a", "c"],
        output_hashes=["b"],
    )
    assert p1 != p2


# ---------------------------------------------------------------------------
# Signing modes
# ---------------------------------------------------------------------------


def test_off_mode_returns_null_signer(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.auth.signing import ActorIdentity, NullSigner, get_signer_for, reset_signer_cache
    from aqp.config import settings

    monkeypatch.setattr(settings, "lineage_signing_enabled", False, raising=False)
    reset_signer_cache()

    signer = get_signer_for(ActorIdentity(kind="service", ref="iceberg_catalog"))
    assert isinstance(signer, NullSigner)
    assert signer.sign(b"anything") == ""


def test_permissive_mode_falls_back_when_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.auth.signing import ActorIdentity, NullSigner, get_signer_for, reset_signer_cache
    from aqp.config import settings

    monkeypatch.setattr(settings, "lineage_signing_enabled", True, raising=False)
    monkeypatch.setattr(settings, "lineage_signing_mode", "permissive", raising=False)
    _make_credential_for_actor(monkeypatch, {})  # empty fields == no key
    reset_signer_cache()

    signer = get_signer_for(ActorIdentity(kind="service", ref="x"))
    assert isinstance(signer, NullSigner)


def test_strict_mode_raises_when_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.auth.signing import (
        ActorIdentity,
        LineageSigningError,
        get_signer_for,
        reset_signer_cache,
    )
    from aqp.config import settings

    monkeypatch.setattr(settings, "lineage_signing_enabled", True, raising=False)
    monkeypatch.setattr(settings, "lineage_signing_mode", "strict", raising=False)
    _make_credential_for_actor(monkeypatch, {})
    reset_signer_cache()

    with pytest.raises(LineageSigningError):
        get_signer_for(ActorIdentity(kind="service", ref="x"))


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _cryptography_available(), reason="cryptography not installed")
def test_sign_and_verify_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.auth.signing import (
        ActorIdentity,
        canonical_transform_payload,
        get_signer_for,
        reset_signer_cache,
        verify_signature,
    )
    from aqp.auth.signing_keys import generate_ed25519_keypair
    from aqp.config import settings

    monkeypatch.setattr(settings, "lineage_signing_enabled", True, raising=False)
    monkeypatch.setattr(settings, "lineage_signing_mode", "permissive", raising=False)

    seed, private_pem, public_pem = generate_ed25519_keypair()
    _make_credential_for_actor(
        monkeypatch,
        {
            "key_id": "ed25519:test:abc",
            "private_key_pem": private_pem,
            "public_key_pem": public_pem,
            "private_key_seed_b64": base64.b64encode(seed).decode("ascii"),
        },
    )
    reset_signer_cache()

    signer = get_signer_for(ActorIdentity(kind="service", ref="iceberg_catalog"))
    payload = canonical_transform_payload(
        job_name="ingest.foo",
        run_id="run-1",
        code_version="v1",
        parameters={"a": 1, "b": 2},
        input_hashes=["aaa"],
        output_hashes=["bbb"],
    )
    sig_hex = signer.sign(payload)
    assert sig_hex
    assert len(sig_hex) == 128  # 64 bytes hex-encoded

    assert verify_signature(
        signature_hex=sig_hex,
        payload=payload,
        public_key_pem=public_pem,
        public_key_bytes=seed and b"",  # not used by cryptography backend
    )

    # Tamper with the payload — verification must fail.
    bad = canonical_transform_payload(
        job_name="ingest.foo",
        run_id="run-2",  # changed
        code_version="v1",
        parameters={"a": 1, "b": 2},
        input_hashes=["aaa"],
        output_hashes=["bbb"],
    )
    assert not verify_signature(
        signature_hex=sig_hex,
        payload=bad,
        public_key_pem=public_pem,
    )


# ---------------------------------------------------------------------------
# Rotation
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _cryptography_available(), reason="cryptography not installed")
def test_rotation_preserves_old_signatures(monkeypatch: pytest.MonkeyPatch) -> None:
    """An old signature MUST still verify with the archived public key
    even after the active signer rotates to a new key."""
    from aqp.auth.signing import (
        ActorIdentity,
        canonical_transform_payload,
        get_signer_for,
        reset_signer_cache,
        verify_signature,
    )
    from aqp.auth.signing_keys import generate_ed25519_keypair
    from aqp.config import settings

    monkeypatch.setattr(settings, "lineage_signing_enabled", True, raising=False)
    monkeypatch.setattr(settings, "lineage_signing_mode", "permissive", raising=False)

    # Round 1 — initial key.
    seed_a, pem_a, pub_a = generate_ed25519_keypair()
    _make_credential_for_actor(
        monkeypatch,
        {
            "key_id": "ed25519:test:keyA",
            "private_key_pem": pem_a,
            "public_key_pem": pub_a,
            "private_key_seed_b64": base64.b64encode(seed_a).decode("ascii"),
        },
    )
    reset_signer_cache()

    signer_a = get_signer_for(ActorIdentity(kind="service", ref="rotation"))
    payload = canonical_transform_payload(
        job_name="job",
        run_id="r1",
        code_version="v1",
        parameters={},
        input_hashes=[],
        output_hashes=[],
    )
    sig_a = signer_a.sign(payload)
    assert sig_a

    # Round 2 — rotate the active key.
    seed_b, pem_b, pub_b = generate_ed25519_keypair()
    _make_credential_for_actor(
        monkeypatch,
        {
            "key_id": "ed25519:test:keyB",
            "private_key_pem": pem_b,
            "public_key_pem": pub_b,
            "private_key_seed_b64": base64.b64encode(seed_b).decode("ascii"),
        },
    )
    reset_signer_cache()
    signer_b = get_signer_for(ActorIdentity(kind="service", ref="rotation"))
    assert signer_b.key_id == "ed25519:test:keyB"
    assert signer_a.key_id == "ed25519:test:keyA"

    # Old signature still verifies against the archived public key.
    assert verify_signature(
        signature_hex=sig_a,
        payload=payload,
        public_key_pem=pub_a,
    )


# ---------------------------------------------------------------------------
# Credential key derivation
# ---------------------------------------------------------------------------


def test_credential_key_for_user() -> None:
    from aqp.auth.signing import ActorIdentity, credential_key_for_actor

    key = credential_key_for_actor(ActorIdentity(kind="user", ref="user-uuid-1"))
    assert key.service == "lineage_signing"
    assert key.purpose == "user:user-uuid-1"


def test_credential_key_for_service_falls_back() -> None:
    from aqp.auth.signing import ActorIdentity, credential_key_for_actor

    key = credential_key_for_actor(ActorIdentity(kind="service", ref="iceberg"))
    assert key.purpose == "service"


# ---------------------------------------------------------------------------
# Helper round-trip via sign_transform_payload
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _cryptography_available(), reason="cryptography not installed")
def test_sign_transform_payload_top_level_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.auth.signing import (
        ActorIdentity,
        canonical_transform_payload,
        reset_signer_cache,
        sign_transform_payload,
        verify_signature,
    )
    from aqp.auth.signing_keys import generate_ed25519_keypair
    from aqp.config import settings

    monkeypatch.setattr(settings, "lineage_signing_enabled", True, raising=False)
    monkeypatch.setattr(settings, "lineage_signing_mode", "permissive", raising=False)

    seed, pem, pub = generate_ed25519_keypair()
    _make_credential_for_actor(
        monkeypatch,
        {
            "key_id": "ed25519:test:helper",
            "private_key_pem": pem,
            "public_key_pem": pub,
            "private_key_seed_b64": base64.b64encode(seed).decode("ascii"),
        },
    )
    reset_signer_cache()

    sig, kid = sign_transform_payload(
        actor=ActorIdentity(kind="service", ref="iceberg"),
        job_name="job",
        run_id="r1",
        code_version="v1",
        parameters={"k": "v"},
        input_hashes=["i1"],
        output_hashes=["o1"],
    )
    assert sig
    assert kid == "ed25519:test:helper"

    payload = canonical_transform_payload(
        job_name="job",
        run_id="r1",
        code_version="v1",
        parameters={"k": "v"},
        input_hashes=["i1"],
        output_hashes=["o1"],
    )
    assert verify_signature(signature_hex=sig, payload=payload, public_key_pem=pub)
