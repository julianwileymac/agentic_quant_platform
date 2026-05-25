"""DataMCP tools that proxy the docs.aqp.fund MCP server.

In-platform agents query the docs corpus through ``data.docs.*``
just like they query Iceberg through ``data.iceberg.*`` or the
codebase through ``codebase.*``. The tools here are thin proxies
over the Cloudflare-Worker-hosted MCP server at
``${AQP_MCP_DOCS_CANONICAL_URI:-https://docs.aqp.fund/mcp}``.

Tools:

- ``data.docs.search``      -- search the corpus via Pagefind
- ``data.docs.fetch_page``  -- return the Markdown source for a route
- ``data.docs.list_pages``  -- return the curated sitemap (llms.txt)

Hard rules respected:

- AGENTS rule 22 (DataMCP boundary): every ``aqp.docs.*`` agent
  read flows through these tools; never query the docs site
  directly from inside an :class:`AgentSpec` body.
- AGENTS rule 49 (MCP RFC 9728 + 8707 conformance): outbound calls
  mint a fresh M2M token via :class:`M2MTokenIssuer` whose ``aud``
  claim is set to ``settings.mcp_docs_canonical_uri`` (no inbound
  token passthrough).
- AGENTS rule 26 (CredentialResolver): the M2M creds resolve
  through :class:`CredentialResolver`; never read from
  ``os.environ`` directly here.
- ``aqp-management-engine`` always-on (credential safety): the
  Authorization header on outbound calls is NEVER logged or
  returned to the caller.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

from aqp.config import settings
from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


def _docs_mcp_origin() -> str:
    """Return the canonical docs MCP URL (without /mcp suffix)."""
    canonical = (
        settings.mcp_docs_canonical_uri
        or "https://docs.aqp.fund/mcp"
    )
    return canonical


async def _docs_mcp_call(
    *,
    method: str,
    params: dict[str, Any],
    ctx: MCPToolContext,
) -> dict[str, Any]:
    """Make a JSON-RPC call to the docs MCP Worker.

    The Worker validates the ``aud`` claim against
    ``settings.mcp_docs_canonical_uri`` (rule 49). The token we mint
    here MUST therefore declare that exact audience. We deliberately
    do NOT propagate the inbound user / agent token — that would be
    a rule-49 token-passthrough violation.
    """
    # Defer the M2M issuer import to function scope to avoid a
    # module-load-time dependency from agent runtimes that don't
    # actually use the docs MCP.
    try:
        from aqp.auth.m2m import M2MTokenIssuer  # type: ignore
    except Exception:  # pragma: no cover - defensive
        M2MTokenIssuer = None  # type: ignore[assignment]
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if M2MTokenIssuer is not None:
        try:
            issuer = M2MTokenIssuer()
            token = await issuer.acquire_async(audience=_docs_mcp_origin())
            if token:
                # SAFE — value never logged.
                headers["Authorization"] = f"Bearer {token}"
        except Exception:  # pragma: no cover - upstream failure
            # Soft-fail and let the Worker reject. We avoid echoing
            # anything sensitive here per the credential-safety rule.
            logger.warning("docs MCP token issuance failed; sending anonymous request")

    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        resp = await client.post(_docs_mcp_origin(), json=body, headers=headers)
    if resp.status_code != 200:
        # Note: we deliberately do NOT include resp.text in the log
        # because some upstreams echo the Authorization header on
        # 401 responses. Only the status is logged.
        logger.warning("docs MCP non-200: status=%s", resp.status_code)
        return {"error": f"upstream status {resp.status_code}"}
    return resp.json()


# ---------------------------------------------------------------------------
# data.docs.search
# ---------------------------------------------------------------------------


class DocsSearchInput(BaseModel):
    """Args for ``data.docs.search``."""

    query: str = Field(min_length=1, max_length=200, description="Search terms.")
    k: int = Field(default=10, ge=1, le=50, description="Max number of results to return.")


@register_data_mcp_tool
class DocsSearchTool(DataMCPTool):
    """Search the docs.aqp.fund corpus via Pagefind.

    Returns up to ``k`` result entries with the page title, a short
    excerpt, and the canonical URL. Backed by the static Pagefind
    index built by the docs CI pipeline.
    """

    name = "data.docs.search"
    description = (
        "Search the public AQP documentation site at docs.aqp.fund. "
        "Returns up to k entries with title, excerpt, and URL. "
        "Use BEFORE attempting to construct a path on the docs site by hand."
    )
    args_schema = DocsSearchInput

    async def _invoke(self, args: DocsSearchInput, ctx: MCPToolContext) -> MCPToolResult:
        body = await _docs_mcp_call(
            method="tools/call",
            params={"name": "search", "arguments": args.model_dump()},
            ctx=ctx,
        )
        return MCPToolResult.from_payload(body)


# ---------------------------------------------------------------------------
# data.docs.fetch_page
# ---------------------------------------------------------------------------


class DocsFetchPageInput(BaseModel):
    """Args for ``data.docs.fetch_page``."""

    route: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "Page route relative to docs.aqp.fund (e.g. 'concepts/data/data-plane'). "
            "MUST NOT include a leading slash or '..' components."
        ),
    )


@register_data_mcp_tool
class DocsFetchPageTool(DataMCPTool):
    """Return the Markdown source for a single docs page by route.

    The Worker performs content negotiation on ``Accept: text/markdown``
    and returns the raw MDX source rather than the rendered HTML. Use
    this to feed an LLM context window without burning tokens on
    layout chrome.
    """

    name = "data.docs.fetch_page"
    description = (
        "Return the Markdown source for a docs.aqp.fund page by route. "
        "Prefer this over fetch_page in the codebase MCP for documentation reads."
    )
    args_schema = DocsFetchPageInput

    async def _invoke(self, args: DocsFetchPageInput, ctx: MCPToolContext) -> MCPToolResult:
        body = await _docs_mcp_call(
            method="tools/call",
            params={"name": "fetch_page", "arguments": args.model_dump()},
            ctx=ctx,
        )
        return MCPToolResult.from_payload(body)


# ---------------------------------------------------------------------------
# data.docs.list_pages
# ---------------------------------------------------------------------------


class DocsListPagesInput(BaseModel):
    """Args for ``data.docs.list_pages``."""

    category: str | None = Field(
        default=None,
        description=(
            "Optional Diátaxis category filter: intro | tutorials | how-to | "
            "concepts | reference | architecture | release-notes. Defaults to all."
        ),
    )


@register_data_mcp_tool
class DocsListPagesTool(DataMCPTool):
    """Return the curated sitemap (llms.txt corpus).

    Use this BEFORE attempting `fetch_page` calls to discover the
    available routes. The response is the docs site's `/llms.txt`
    file, which contains one entry per non-internal page.
    """

    name = "data.docs.list_pages"
    description = (
        "Return the curated docs.aqp.fund sitemap as the llms.txt corpus. "
        "Use to discover available pages before invoking data.docs.fetch_page."
    )
    args_schema = DocsListPagesInput

    async def _invoke(self, args: DocsListPagesInput, ctx: MCPToolContext) -> MCPToolResult:
        body = await _docs_mcp_call(
            method="tools/call",
            params={"name": "list_pages", "arguments": args.model_dump()},
            ctx=ctx,
        )
        return MCPToolResult.from_payload(body)
