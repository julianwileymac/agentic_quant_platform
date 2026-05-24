"""REST adapter base.

Built on :class:`httpx.AsyncClient` with:

- ``tenacity`` exponential-backoff retry
- ``aiolimiter`` token-bucket rate limiting (matches venue API caps)
- Optional auth-header injection via :class:`aqp.credentials.CredentialResolver`
  (preserves AGENTS hard rule 26 — no direct ``settings.*_token`` reads)
"""
from __future__ import annotations

from aqp_bots.adapters.rest.base import RestAdapterBase, RestAdapterError

__all__ = ["RestAdapterBase", "RestAdapterError"]
