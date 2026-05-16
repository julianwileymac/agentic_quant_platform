"""MathPix PDF parser (credential-gated commercial API)."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from aqp.rag.parsers.base import BaseDocParser, ParsedDoc, ParsedEquation

logger = logging.getLogger(__name__)

_INLINE_RE = re.compile(r"\\\((.+?)\\\)", re.DOTALL)
_DISPLAY_RE = re.compile(r"\\\[(.+?)\\\]", re.DOTALL)


def _credentials() -> tuple[str, str] | None:
    """Resolve `(app_id, app_key)` via the CredentialResolver.

    Per AGENTS.md rule 26, we never read ``os.environ`` directly. The
    resolver chain (m2m → file → env) handles credential rotation.
    Falls back to the ``mathpix_app_id`` / ``mathpix_app_key``
    Settings fields when no store offers a hit.
    """
    try:
        from aqp.config import settings
        from aqp.credentials import CredentialKey, CredentialResolver
    except Exception:  # noqa: BLE001
        return None
    try:
        resolver = CredentialResolver()
        cred = resolver.resolve(
            CredentialKey(service="mathpix", purpose="default"),
            default={
                "app_id": settings.mathpix_app_id or "",
                "app_key": settings.mathpix_app_key or "",
            },
        )
    except Exception:  # noqa: BLE001
        return None
    app_id = cred.get("app_id")
    app_key = cred.get("app_key")
    if not app_id or not app_key:
        return None
    return str(app_id), str(app_key)


class MathPixParser(BaseDocParser):
    """MathPix-API PDF parser.

    Activates only when the AQP CredentialResolver returns both
    ``mathpix.app_id`` and ``mathpix.app_key``.
    """

    name = "mathpix"

    @classmethod
    def available(cls) -> bool:
        try:
            import requests  # type: ignore[import-not-found]  # noqa: F401
        except Exception:  # noqa: BLE001
            return False
        return _credentials() is not None

    def parse(self, path: Path | str) -> ParsedDoc:
        import requests  # type: ignore[import-not-found]

        creds = _credentials()
        if not creds:
            raise RuntimeError("MathPix credentials not configured")
        app_id, app_key = creds
        path = Path(path)
        with path.open("rb") as fh:
            files: dict[str, Any] = {"file": (path.name, fh, "application/pdf")}
            options = {"conversion_formats": {"mmd": True, "md": True}}
            data = {"options_json": str(options)}
            resp = requests.post(
                "https://api.mathpix.com/v3/pdf",
                files=files,
                data=data,
                headers={"app_id": app_id, "app_key": app_key},
                timeout=120,
            )
        if not resp.ok:
            raise RuntimeError(f"MathPix POST failed: {resp.status_code} {resp.text[:200]}")
        payload = resp.json()
        pdf_id = payload.get("pdf_id")
        if not pdf_id:
            raise RuntimeError(f"MathPix did not return a pdf_id: {payload}")

        # Poll for completion. MathPix processes async; in practice
        # 30s is generous for a 10-20 page paper.
        import time

        markdown: str | None = None
        for _ in range(30):
            time.sleep(2.0)
            status_resp = requests.get(
                f"https://api.mathpix.com/v3/pdf/{pdf_id}",
                headers={"app_id": app_id, "app_key": app_key},
                timeout=30,
            )
            if status_resp.ok:
                status = status_resp.json().get("status")
                if status == "completed":
                    mmd_resp = requests.get(
                        f"https://api.mathpix.com/v3/pdf/{pdf_id}.mmd",
                        headers={"app_id": app_id, "app_key": app_key},
                        timeout=60,
                    )
                    if mmd_resp.ok:
                        markdown = mmd_resp.text
                    break
                if status == "error":
                    raise RuntimeError(
                        f"MathPix conversion errored: {status_resp.json()}"
                    )
        if not markdown:
            raise RuntimeError("MathPix conversion timed out")

        equations: list[ParsedEquation] = []
        for match in _DISPLAY_RE.finditer(markdown):
            equations.append(ParsedEquation(latex=match.group(1).strip(), inline=False))
        for match in _INLINE_RE.finditer(markdown):
            equations.append(ParsedEquation(latex=match.group(1).strip(), inline=True))
        blocks = [b.strip() for b in re.split(r"\n\s*\n", markdown) if b.strip()]
        return ParsedDoc(
            text_blocks=blocks,
            equations=equations,
            metadata={"source": "mathpix", "pdf_id": pdf_id},
            parser_name=self.name,
        )


from aqp.rag.parsers.registry import register_parser  # noqa: E402

register_parser(MathPixParser)
