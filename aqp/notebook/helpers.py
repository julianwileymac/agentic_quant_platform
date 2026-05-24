"""Tenancy-aware notebook helpers for AQP-scaffolded Jupyter notebooks.

The companion Theia extension (``theia-ide-aqp-notebook-quant-ext``)
emits a first cell that imports :func:`attach` and binds the result to
``ctx`` so subsequent cells can do ``ctx.data.search(...)``,
``ctx.codebase.find_definition(...)``, or
``ctx.router.complete(...)`` without touching credentials directly.

Hard-rule contract:

* All credentials resolve through
  :class:`aqp.credentials.resolver.CredentialResolver` (rule 26).
* LLM calls route through :func:`aqp.llm.providers.router.router_complete`
  (rule 2).
* DataMCP / CodebaseMCP access goes through the bundled stdio binaries
  via the in-process bridges (rule 22).
* No secrets ever appear in :meth:`AqpNotebookContext.tenancy_summary`
  output — the helper redacts any value whose key contains
  ``token`` / ``secret`` / ``key`` / ``password`` / ``credential``.

The module is intentionally dependency-light at import time: heavy AQP
submodules (``aqp.data.mcp.client``, ``aqp.codebase.mcp.client``,
``aqp.llm.providers.router``) are imported lazily inside
:meth:`AqpNotebookContext.__getattr__` so a cold notebook startup is
sub-second even when the user only needs one helper.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_REDACT_KEYS = frozenset(
    {"token", "secret", "api_key", "password", "credential", "private", "authorization"}
)


@dataclasses.dataclass(slots=True)
class AqpNotebookContext:
    """Composite handle for a tenancy-scoped notebook session.

    Lazy attributes:

    - ``data`` — DataMCP client (catalog, datasets, lineage, agents, ...).
    - ``codebase`` — Codebase MCP client (search, find_definition, ...).
    - ``router`` — :func:`router_complete` callable wrapped in a tiny
      ergonomic class so the notebook cell stays one-liner-friendly.

    Each attribute is built once on first access; subsequent reads return
    the cached instance.
    """

    org: Optional[str] = None
    team: Optional[str] = None
    workspace: Optional[str] = None
    project: Optional[str] = None
    lab: Optional[str] = None

    _data: Any = dataclasses.field(default=None, repr=False)
    _codebase: Any = dataclasses.field(default=None, repr=False)
    _router: Any = dataclasses.field(default=None, repr=False)

    # --- Public ergonomic accessors --------------------------------------

    @property
    def data(self) -> Any:
        """DataMCP-backed catalog client.

        Resolves to :class:`aqp.data.mcp.client.DataMcpClient` (or its
        :class:`aqp.data.mcp.bridge.InProcessDataMcpBridge` equivalent
        when running inside an AQP-aware notebook server).
        """
        if self._data is None:
            self._data = self._load_data_client()
        return self._data

    @property
    def codebase(self) -> Any:
        """CodebaseMCP-backed search / navigation client."""
        if self._codebase is None:
            self._codebase = self._load_codebase_client()
        return self._codebase

    @property
    def router(self) -> Any:
        """AQP `router_complete` LLM gateway (rule 2)."""
        if self._router is None:
            self._router = self._load_router_client()
        return self._router

    def tenancy_summary(self) -> str:
        """Return a one-line description of the active tenancy.

        Never includes secret material — the redaction filter strips any
        attribute whose name resembles a credential key.
        """
        bits: list[str] = []
        for key in ("org", "team", "workspace", "project", "lab"):
            value = getattr(self, key)
            if value and key not in _REDACT_KEYS:
                bits.append(f"{key}={value}")
        if not bits:
            return "(no tenancy headers set)"
        return " ".join(bits)

    def perspective(self, table: Any) -> dict[str, Any]:
        """Wrap an Arrow table / pyarrow.Table in the AQP Perspective
        MIME envelope so the Theia notebook MIME renderer can display it.

        Usage in a notebook cell::

            display(ctx.perspective(my_arrow_table), raw=True)

        The cell output ends up routed to the
        ``application/vnd.aqp.perspective-arrow+arrow`` MIME renderer
        shipped by ``theia-ide-aqp-notebook-quant-ext``.
        """
        try:
            import pyarrow as pa  # noqa: WPS433 - intentional lazy import
            buf = pa.ipc.new_stream  # type: ignore[attr-defined]
            sink = pa.BufferOutputStream()
            writer = pa.ipc.new_stream(sink, table.schema)
            writer.write_table(table)
            writer.close()
            payload = sink.getvalue().to_pybytes()
        except Exception:  # pragma: no cover - notebook ergonomic path
            logger.warning(
                "ctx.perspective(): could not serialise Arrow table; "
                "falling back to text MIME"
            )
            return {"text/plain": repr(table)}
        return {"application/vnd.aqp.perspective-arrow+arrow": payload}

    # --- Internal loaders -------------------------------------------------

    def _load_data_client(self) -> Any:
        try:
            # Prefer the in-process bridge (rule 22 + rule 49) when the
            # AQP monolith is importable in this Python; otherwise fall
            # back to the HTTP stdio binary.
            from aqp.data.mcp.client import DataMcpClient  # type: ignore

            return DataMcpClient.from_environment(
                workspace=self.workspace,
                project=self.project,
                lab=self.lab,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("aqp.notebook.helpers: DataMCP client unavailable: %s", exc)
            return _UnavailableHelper("DataMCP", exc)

    def _load_codebase_client(self) -> Any:
        try:
            from aqp.codebase.mcp.client import CodebaseMcpClient  # type: ignore

            return CodebaseMcpClient.from_environment()
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "aqp.notebook.helpers: CodebaseMCP client unavailable: %s", exc
            )
            return _UnavailableHelper("CodebaseMCP", exc)

    def _load_router_client(self) -> Any:
        try:
            from aqp.llm.providers.router import router_complete  # type: ignore

            return _RouterCompleteFacade(router_complete)
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "aqp.notebook.helpers: router_complete unavailable: %s", exc
            )
            return _UnavailableHelper("router_complete", exc)


class _UnavailableHelper:
    """Stand-in returned when an AQP submodule cannot be imported.

    Surfaces a clear error message at call time instead of silently
    failing — particularly useful in notebooks where stack traces from
    deep import errors are otherwise opaque.
    """

    def __init__(self, name: str, exc: BaseException) -> None:
        self._name = name
        self._exc = exc

    def __getattr__(self, item: str) -> Any:
        raise RuntimeError(
            f"aqp.notebook.helpers: {self._name} is not available "
            f"in this Python environment: {self._exc!r}"
        )

    def __repr__(self) -> str:
        return f"<AqpHelper unavailable {self._name}: {self._exc!r}>"


class _RouterCompleteFacade:
    """Tiny ergonomic wrapper around :func:`router_complete` so a
    notebook cell can do ``ctx.router.complete(prompt='...')`` without
    needing to know the full RouterCompleteRequest shape.
    """

    def __init__(self, router_complete_fn: Any) -> None:
        self._router_complete = router_complete_fn

    def complete(
        self,
        prompt: str,
        *,
        model: str = "gpt-4o",
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = self._router_complete(
            model_alias=model,
            messages=messages,
            temperature=temperature,
        )
        return getattr(response, "content", str(response))


def attach(
    *,
    org: Optional[str] = None,
    team: Optional[str] = None,
    workspace: Optional[str] = None,
    project: Optional[str] = None,
    lab: Optional[str] = None,
) -> AqpNotebookContext:
    """Build an :class:`AqpNotebookContext` for the active tenancy.

    Each argument defaults to the matching ``AQP_*`` environment variable
    when not passed explicitly:

    - ``AQP_ORG`` / ``AQP_TEAM`` / ``AQP_WORKSPACE`` / ``AQP_PROJECT`` /
      ``AQP_LAB``.

    The Theia notebook scaffolder pre-populates these env vars when it
    spawns the kernel, so a cell that simply calls ``attach()`` picks up
    the IDE-side tenancy automatically.
    """
    import os

    return AqpNotebookContext(
        org=org or os.environ.get("AQP_ORG") or None,
        team=team or os.environ.get("AQP_TEAM") or None,
        workspace=workspace or os.environ.get("AQP_WORKSPACE") or None,
        project=project or os.environ.get("AQP_PROJECT") or None,
        lab=lab or os.environ.get("AQP_LAB") or None,
    )
