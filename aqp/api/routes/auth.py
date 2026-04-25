"""Auth surface — placeholder ``whoami`` for the local-first deployment.

This is intentionally minimal: the platform is local-first and there are no
real users today. The webui needs *some* identity to round-trip a session
cookie and to render a "logged in as" indicator, so we expose a single
endpoint that returns a stable local user record.

When we eventually adopt JWT (per the fastapi-template pattern) this module
becomes the home for ``/auth/login``, ``/auth/refresh``, ``/auth/logout``
and ``Depends(current_user)`` plumbing.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])


class WhoAmI(BaseModel):
    id: str
    name: str
    role: str
    auth_kind: str = "local"


@router.get("/whoami", response_model=WhoAmI)
def whoami() -> WhoAmI:
    return WhoAmI(id="local", name="Local User", role="owner")
