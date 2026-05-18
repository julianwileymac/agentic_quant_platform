"""Persistence + helper tests for tenancy invite models."""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession


def _prepare_schema(session: OrmSession) -> None:
    from aqp.persistence import models_audit, models_tenancy  # noqa: F401
    from aqp.persistence.models import Base

    session.execute(sa.text("PRAGMA foreign_keys = ON"))
    Base.metadata.create_all(bind=session.get_bind())


def test_hash_invite_token_is_deterministic_hex() -> None:
    from aqp.persistence.models_audit import hash_invite_token

    raw = "raw-invite-token"
    secret = "unit-test-secret"
    digest = hash_invite_token(raw, secret=secret)
    expected = hmac.new(
        secret.encode("utf-8"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert digest == expected
    assert len(digest) == 64


def test_generate_invite_token_returns_raw_plus_matching_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.config import settings as app_settings
    from aqp.persistence.models_audit import generate_invite_token, hash_invite_token

    monkeypatch.setattr(app_settings, "auth_invite_secret", "x" * 32)
    raw, token_hash = generate_invite_token()
    assert raw
    assert token_hash == hash_invite_token(raw)
    assert len(token_hash) == 64


def test_hash_invite_token_raises_when_secret_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.config import settings as app_settings
    from aqp.persistence.models_audit import hash_invite_token

    monkeypatch.setattr(app_settings, "auth_invite_secret", "")
    with pytest.raises(RuntimeError, match="auth_invite_secret"):
        hash_invite_token("raw")


def test_tenancy_invite_round_trip_insert_and_accept(
    in_memory_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.config import settings as app_settings
    from aqp.persistence.models_audit import TenancyInvite, generate_invite_token
    from aqp.persistence.models_tenancy import Organization, User, Workspace

    monkeypatch.setattr(app_settings, "auth_invite_secret", "y" * 32)
    Session = in_memory_db
    with Session() as session:
        _prepare_schema(session)
        org = Organization(slug="invite-org", name="Invite Org")
        session.add(org)
        session.flush()
        workspace = Workspace(org_id=org.id, slug="invite-ws", name="Invite Workspace")
        session.add(workspace)
        inviter = User(email="inviter@example.com", display_name="Inviter")
        accepter = User(email="accepter@example.com", display_name="Accepter")
        session.add_all([inviter, accepter])
        session.flush()

        raw_token, token_hash = generate_invite_token()
        invite = TenancyInvite(
            organization_id=org.id,
            workspace_id=workspace.id,
            email="pending@example.com",
            role="viewer",
            invited_by_user_id=inviter.id,
            token_hash=token_hash,
            token_prefix=raw_token[:8],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        session.add(invite)
        session.commit()
        session.refresh(invite)
        assert invite.status == "pending"

        invite.status = "accepted"
        invite.accepted_at = datetime.now(timezone.utc)
        invite.accepted_by_user_id = accepter.id
        session.commit()
        session.refresh(invite)
        assert invite.status == "accepted"
        assert invite.accepted_at is not None
        assert invite.accepted_by_user_id == accepter.id


def test_tenancy_invite_partial_unique_index_blocks_second_pending_for_same_email(
    in_memory_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.config import settings as app_settings
    from aqp.persistence.models_audit import TenancyInvite, generate_invite_token
    from aqp.persistence.models_tenancy import Organization

    monkeypatch.setattr(app_settings, "auth_invite_secret", "z" * 32)
    Session = in_memory_db
    with Session() as session:
        _prepare_schema(session)
        org = Organization(slug="dup-org", name="Dup Org")
        session.add(org)
        session.flush()

        raw_one, hash_one = generate_invite_token()
        first = TenancyInvite(
            organization_id=org.id,
            email="dup@example.com",
            role="viewer",
            token_hash=hash_one,
            token_prefix=raw_one[:8],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            status="pending",
        )
        session.add(first)
        session.commit()

        raw_two, hash_two = generate_invite_token()
        second = TenancyInvite(
            organization_id=org.id,
            email="dup@example.com",
            role="editor",
            token_hash=hash_two,
            token_prefix=raw_two[:8],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            status="pending",
        )
        session.add(second)
        with pytest.raises(Exception):
            session.commit()
