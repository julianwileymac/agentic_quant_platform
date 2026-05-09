"""Tests for :mod:`aqp.auth.pkce`."""
from __future__ import annotations

import base64
import hashlib

import pytest

from aqp.auth.pkce import (
    generate_code_challenge,
    generate_code_verifier,
    generate_random_string,
)


def test_random_string_length_default():
    assert len(generate_random_string()) == 64


def test_random_string_length_custom():
    assert len(generate_random_string(43)) == 43
    assert len(generate_random_string(128)) == 128


def test_random_string_rejects_out_of_range_lengths():
    with pytest.raises(ValueError):
        generate_random_string(42)
    with pytest.raises(ValueError):
        generate_random_string(129)


def test_random_string_uses_unreserved_alphabet():
    sample = generate_random_string(128)
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~")
    assert set(sample).issubset(allowed)


def test_random_strings_are_unique():
    a = generate_random_string()
    b = generate_random_string()
    assert a != b


def test_generate_code_verifier_default():
    verifier = generate_code_verifier()
    assert 43 <= len(verifier) <= 128


def test_code_challenge_matches_rfc7636_s256():
    verifier = "ThisIsAValidPKCEVerifierAtLeast43Chars1234567890"
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("utf-8")).digest()
    ).decode("utf-8").rstrip("=")
    assert generate_code_challenge(verifier) == expected


def test_code_challenge_changes_with_verifier():
    a = generate_code_challenge("verifier-a-and-it-is-long-enough-for-rfc7636-43c")
    b = generate_code_challenge("verifier-b-and-it-is-long-enough-for-rfc7636-43c")
    assert a != b
