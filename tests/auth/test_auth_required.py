"""Strict auth-required mode tests."""
from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from aqp.auth.deps import current_user


def test_auth_required_denies_missing_token_in_auth0_mode(monkeypatch):
    from aqp.config import settings

    monkeypatch.setattr(settings, "auth_provider", "auth0", raising=True)
    monkeypatch.setattr(settings, "auth_required", True, raising=True)

    app = FastAPI()

    @app.get("/protected")
    def protected(user=Depends(current_user)):
        return {"id": user.id}

    res = TestClient(app).get("/protected")
    assert res.status_code == 401
    assert res.json()["detail"] == "Authentication required"


def test_auth_permissive_allows_default_user_without_token(monkeypatch):
    from aqp.config import settings

    monkeypatch.setattr(settings, "auth_provider", "auth0", raising=True)
    monkeypatch.setattr(settings, "auth_required", False, raising=True)

    app = FastAPI()

    @app.get("/permissive")
    def permissive(user=Depends(current_user)):
        return {"default": user.is_default}

    res = TestClient(app).get("/permissive")
    assert res.status_code == 200
    assert res.json()["default"] is True
