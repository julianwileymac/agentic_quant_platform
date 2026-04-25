"""Wrapper around the ``edgartools`` library.

``edgartools`` is an optional runtime dependency (``[sec]`` extra). The
wrapper defers the import so that modules which merely *reference* the
adapter (e.g. routers) still import cleanly on a base install; the
error surfaces only when you actually call into the client.

SEC compliance requires an identity string per
https://www.sec.gov/os/accessing-edgar-data — ``Your Name you@domain.com``
is the canonical format. We read it from :data:`aqp.config.settings.sec_edgar_identity`.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.config import settings

logger = logging.getLogger(__name__)


class SecClientError(RuntimeError):
    """Raised when edgartools is missing or the identity string is unset."""


_IDENTITY_SET_FOR: str | None = None


def _ensure_edgar() -> Any:
    """Import ``edgar`` lazily and set the identity string at most once."""
    global _IDENTITY_SET_FOR
    try:
        import edgar  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SecClientError(
            "edgartools is not installed; run 'pip install \"agentic-quant-platform[sec]\"'"
        ) from exc

    identity = (settings.sec_edgar_identity or "").strip()
    if not identity:
        raise SecClientError(
            "AQP_SEC_EDGAR_IDENTITY is not set; edgartools requires "
            "'Your Name your@email.com' to respect SEC fair-use guidance"
        )

    if _IDENTITY_SET_FOR != identity:
        try:
            edgar.set_identity(identity)
            _IDENTITY_SET_FOR = identity
        except Exception:
            logger.debug("edgar.set_identity failed", exc_info=True)
    return edgar


class SecClient:
    """Lazy façade exposing the small subset of edgartools we use."""

    def __init__(self) -> None:
        self._edgar: Any | None = None

    @property
    def edgar(self) -> Any:
        if self._edgar is None:
            self._edgar = _ensure_edgar()
        return self._edgar

    # ------------------------------------------------------------------
    # Probe
    # ------------------------------------------------------------------

    def probe(self) -> tuple[bool, str]:
        identity = (settings.sec_edgar_identity or "").strip()
        if not identity:
            return False, "AQP_SEC_EDGAR_IDENTITY is not set"
        try:
            self.edgar  # triggers the import + set_identity
        except SecClientError as exc:
            return False, str(exc)
        return True, "ok"

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------

    def company(self, cik_or_ticker: str | int) -> Any:
        """Return an ``edgar.Company`` object."""
        return self.edgar.Company(cik_or_ticker)

    def get_filings(
        self,
        *,
        cik_or_ticker: str | int | None = None,
        form: str | list[str] | None = None,
        year: int | list[int] | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int | None = None,
    ) -> Any:
        """Return the ``edgar.Filings`` collection for a company or universe."""
        if cik_or_ticker is not None:
            company = self.company(cik_or_ticker)
            kwargs: dict[str, Any] = {}
            if form is not None:
                kwargs["form"] = form
            if year is not None:
                kwargs["year"] = year
            filings = company.get_filings(**kwargs)
        else:
            filings = self.edgar.get_filings(form=form, year=year)

        if start or end:
            try:
                filings = filings.filter(date=(start, end))
            except Exception:
                logger.debug("edgar filings date filter failed", exc_info=True)

        if limit:
            try:
                filings = filings.head(int(limit))
            except Exception:
                logger.debug("edgar filings head() failed", exc_info=True)
        return filings

    def get_filing(self, accession_no: str) -> Any | None:
        """Return a single ``edgar.Filing`` by accession number."""
        try:
            return self.edgar.get_filings(accession_no=accession_no).head(1)[0]
        except Exception:
            logger.debug("edgar.get_filings(accession_no=...) failed", exc_info=True)
            try:
                # Some edgartools versions expose ``Filing.from_accession``.
                return self.edgar.Filing.from_accession(accession_no)  # type: ignore[attr-defined]
            except Exception:
                return None
