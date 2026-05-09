"""Tests for :mod:`aqp.auth.session.crypto`.

The crypto layer is the second-most security-sensitive piece of the
auth port (after JWT verification). These tests verify:

- Round-trip encryption decrypts to the original payload.
- Wrong secret OR wrong salt fail to decrypt.
- Empty secret / salt are rejected before HKDF runs.
- Distinct salts produce distinct ciphertexts even with identical
  payload + secret (per-user salt is the whole point).

Skipped wholesale when ``jwcrypto`` is not installed (the optional
``[auth]`` extra) so unrelated CI jobs aren't blocked. The dependency
is declared in :file:`pyproject.toml` and ships with rebuilt images.
"""
from __future__ import annotations

import pytest

jwcrypto = pytest.importorskip("jwcrypto")

from aqp.auth.session.crypto import decrypt_payload, encrypt_payload  # noqa: E402


SECRET = "0123456789abcdef0123456789abcdef"  # 32 bytes
SALT_A = "user-a"
SALT_B = "user-b"


def test_round_trip_recovers_payload():
    payload = {"user": {"sub": "auth0|abc"}, "token_sets": [{"audience": "aqp"}]}
    token = encrypt_payload(payload, SECRET, SALT_A)
    assert isinstance(token, str)
    assert token != ""
    out = decrypt_payload(token, SECRET, SALT_A)
    assert out == payload


def test_wrong_secret_rejects_decryption():
    token = encrypt_payload({"a": 1}, SECRET, SALT_A)
    with pytest.raises(Exception):
        decrypt_payload(token, "different-secret-32-bytes-1234567", SALT_A)


def test_wrong_salt_rejects_decryption():
    token = encrypt_payload({"a": 1}, SECRET, SALT_A)
    with pytest.raises(Exception):
        decrypt_payload(token, SECRET, SALT_B)


def test_empty_secret_rejected():
    with pytest.raises(ValueError):
        encrypt_payload({"a": 1}, "", SALT_A)


def test_empty_salt_rejected():
    with pytest.raises(ValueError):
        encrypt_payload({"a": 1}, SECRET, "")


def test_per_salt_ciphertext_is_distinct():
    a = encrypt_payload({"a": 1}, SECRET, SALT_A)
    b = encrypt_payload({"a": 1}, SECRET, SALT_B)
    assert a != b


def test_payload_with_unicode_round_trips():
    payload = {"name": "ünîcôdé", "lang": "日本語"}
    token = encrypt_payload(payload, SECRET, SALT_A)
    assert decrypt_payload(token, SECRET, SALT_A) == payload
