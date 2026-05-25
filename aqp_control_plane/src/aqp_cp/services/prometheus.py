"""Identity-aware Prometheus proxy.

Phase 1.3 of the control-plane maturation. Every selector in an
inbound PromQL query is rewritten to include the active tenant's
label matcher (``{aqp_tenant="<org_id>"}``) before the request hits
Prometheus. Operators with ``admin:cluster`` may opt out via an
explicit ``disable_tenant_filter=true`` query param.

The rewriter is dependency-free — it walks the PromQL string,
identifies selector boundaries by balancing braces, and injects the
matcher in-place. A small denylist suppresses metric names that
shouldn't be returned cross-tenant (``up``, ``kube_node_*``,
``prometheus_*``, etc.). Tests cover:

- Simple selectors (``cpu_usage``).
- Selectors with existing labels (``cpu_usage{pod="foo"}``).
- Binary ops (``sum(rate(cpu_usage[5m])) / count(cpu_usage)``).
- Subqueries / functions (``rate(cpu_usage[5m:1m])``).
- Regex label matchers (``cpu_usage{pod=~"foo.*"}``).
- Deny-listed metric names (returns 403-style payload).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# PromQL identifier — metric name + label name.
_IDENT = re.compile(r"[a-zA-Z_:][a-zA-Z0-9_:]*")

# Functions / aggregations that take a vector but do NOT start a new
# metric selector at their position. We never inject the tenant
# matcher on these — the matcher belongs on the metric INSIDE the
# call, not on the function call itself.
_KEYWORDS_TO_SKIP: frozenset[str] = frozenset({
    "by",
    "without",
    "on",
    "ignoring",
    "group_left",
    "group_right",
    "and",
    "or",
    "unless",
    "offset",
    "bool",
})


@dataclass(frozen=True, slots=True)
class PromQLRewriteResult:
    """Outcome of :meth:`PromQLLabelInjector.rewrite`."""

    original: str
    rewritten: str
    metrics_seen: tuple[str, ...]
    metrics_denied: tuple[str, ...]


class PromQLDeniedError(Exception):
    """Raised when a query references a deny-listed metric name."""

    def __init__(self, metrics: tuple[str, ...]) -> None:
        super().__init__(f"deny-listed metric(s): {sorted(metrics)}")
        self.metrics = metrics


class PromQLLabelInjector:
    """Inject ``{<tenant_label>="<tenant_id>"}`` into every metric selector.

    The injector is intentionally conservative — it only rewrites
    identifiers that look like metric names (not function calls,
    aggregation modifiers, or numeric literals). Selectors that
    already contain the tenant label are left untouched.
    """

    def __init__(
        self,
        *,
        tenant_label: str = "aqp_tenant",
        deny_patterns: tuple[str, ...] = (),
    ) -> None:
        self._tenant_label = tenant_label
        self._deny_patterns = tuple(deny_patterns)

    @property
    def tenant_label(self) -> str:
        return self._tenant_label

    def rewrite(
        self,
        query: str,
        *,
        tenant_id: str,
    ) -> PromQLRewriteResult:
        if not query.strip():
            return PromQLRewriteResult(
                original=query,
                rewritten=query,
                metrics_seen=(),
                metrics_denied=(),
            )
        result_parts: list[str] = []
        metrics_seen: list[str] = []
        metrics_denied: list[str] = []
        i = 0
        n = len(query)
        while i < n:
            ch = query[i]
            # Range vector / subquery — pass the entire [..] verbatim
            # without rewriting. The unit letters (s/m/h/d/w/y) inside
            # the brackets are not metric identifiers.
            if ch == "[":
                close = _matching_bracket(query, i)
                if close == -1:
                    raise ValueError(
                        f"unterminated range vector at offset {i} in: {query!r}"
                    )
                result_parts.append(query[i:close + 1])
                i = close + 1
                continue
            # Skip past string literals untouched.
            if ch in ('"', "'", "`"):
                end = _skip_string(query, i)
                result_parts.append(query[i:end])
                i = end
                continue
            if ch.isalpha() or ch == "_" or ch == ":":
                match = _IDENT.match(query, i)
                if match is None:
                    result_parts.append(ch)
                    i += 1
                    continue
                ident = match.group(0)
                next_idx = match.end()
                if ident in _KEYWORDS_TO_SKIP:
                    result_parts.append(ident)
                    i = next_idx
                    continue
                lookahead = _peek_non_whitespace(query, next_idx)
                # Function call -> not a metric selector itself.
                if lookahead == "(":
                    result_parts.append(ident)
                    i = next_idx
                    continue
                # Found a metric reference.
                if self._is_denied(ident):
                    metrics_denied.append(ident)
                    metrics_seen.append(ident)
                    result_parts.append(ident)
                    i = next_idx
                    continue
                metrics_seen.append(ident)
                # If the selector already has an explicit label block,
                # splice the tenant matcher inside.
                if lookahead == "{":
                    open_idx = query.index("{", next_idx)
                    close_idx = _matching_brace(query, open_idx)
                    if close_idx == -1:
                        raise ValueError(
                            f"unterminated label selector at offset {open_idx} in: {query!r}"
                        )
                    inner = query[open_idx + 1 : close_idx]
                    if self._contains_label(inner):
                        result_parts.append(query[i:close_idx + 1])
                    else:
                        injected = self._format_matcher(tenant_id)
                        merged = (
                            injected if not inner.strip() else f"{injected}, {inner}"
                        )
                        result_parts.append(
                            query[i:open_idx] + "{" + merged + "}"
                        )
                    i = close_idx + 1
                else:
                    result_parts.append(
                        ident + "{" + self._format_matcher(tenant_id) + "}"
                    )
                    i = next_idx
                continue
            result_parts.append(ch)
            i += 1
        rewritten = "".join(result_parts)
        if metrics_denied:
            raise PromQLDeniedError(tuple(metrics_denied))
        return PromQLRewriteResult(
            original=query,
            rewritten=rewritten,
            metrics_seen=tuple(metrics_seen),
            metrics_denied=tuple(metrics_denied),
        )

    def _is_denied(self, ident: str) -> bool:
        for pattern in self._deny_patterns:
            if fnmatchcase(ident, pattern) or ident == pattern:
                return True
        return False

    def _contains_label(self, inner: str) -> bool:
        # Quick literal check first — covers the explicit
        # ``aqp_tenant="..."`` shape. For wildcards / regex matchers
        # the operator is still in the source string so this fires.
        return bool(
            re.search(
                rf'\b{re.escape(self._tenant_label)}\s*(=|!=|=~|!~)',
                inner,
            )
        )

    def _format_matcher(self, tenant_id: str) -> str:
        # PromQL label values use double quotes; backslash + double
        # quote inside the value must be escaped.
        escaped = tenant_id.replace("\\", "\\\\").replace('"', '\\"')
        return f'{self._tenant_label}="{escaped}"'


def _peek_non_whitespace(s: str, idx: int) -> str:
    n = len(s)
    while idx < n and s[idx].isspace():
        idx += 1
    return s[idx] if idx < n else ""


def _matching_bracket(s: str, open_idx: int) -> int:
    """Return the index of the matching ``]`` for the ``[`` at ``open_idx``."""
    depth = 0
    n = len(s)
    i = open_idx
    in_str = False
    str_quote = ""
    while i < n:
        ch = s[i]
        if in_str:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == str_quote:
                in_str = False
                i += 1
                continue
            i += 1
            continue
        if ch in ('"', "'", "`"):
            in_str = True
            str_quote = ch
            i += 1
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _skip_string(s: str, start: int) -> int:
    """Return the index one past the end of the string literal at ``start``."""
    if start >= len(s):
        return start
    quote = s[start]
    if quote not in ('"', "'", "`"):
        return start + 1
    i = start + 1
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == quote:
            return i + 1
        i += 1
    return n


def _matching_brace(s: str, open_idx: int) -> int:
    """Return the index of the matching ``}`` for the ``{`` at ``open_idx``.

    Tracks string literals so a ``{`` inside a label value doesn't
    confuse the scanner. Returns -1 if no match.
    """
    depth = 0
    n = len(s)
    i = open_idx
    in_str = False
    str_quote = ""
    while i < n:
        ch = s[i]
        if in_str:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == str_quote:
                in_str = False
                i += 1
                continue
            i += 1
            continue
        if ch in ('"', "'", "`"):
            in_str = True
            str_quote = ch
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PrometheusQueryResult:
    rewritten_query: str
    metrics_seen: tuple[str, ...]
    data: Any


class IdentityAwarePrometheusClient:
    """Async client that rewrites + proxies PromQL queries.

    Constructed once per process; the underlying httpx client is
    lazily created on first use.
    """

    def __init__(
        self,
        *,
        base_url: str,
        injector: PromQLLabelInjector,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._injector = injector
        self._timeout = timeout_seconds
        self._http: httpx.AsyncClient | None = None

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def injector(self) -> PromQLLabelInjector:
        return self._injector

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._timeout)
        return self._http

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def query(
        self,
        *,
        expression: str,
        tenant_id: str,
        time: float | None = None,
        disable_tenant_filter: bool = False,
    ) -> PrometheusQueryResult:
        if disable_tenant_filter:
            rewritten = PromQLRewriteResult(
                original=expression,
                rewritten=expression,
                metrics_seen=(),
                metrics_denied=(),
            )
        else:
            rewritten = self._injector.rewrite(expression, tenant_id=tenant_id)
        params: dict[str, str] = {"query": rewritten.rewritten}
        if time is not None:
            params["time"] = str(time)
        client = await self._client()
        response = await client.get(f"{self._base_url}/api/v1/query", params=params)
        return PrometheusQueryResult(
            rewritten_query=rewritten.rewritten,
            metrics_seen=rewritten.metrics_seen,
            data=response.json() if response.text else None,
        )

    async def query_range(
        self,
        *,
        expression: str,
        tenant_id: str,
        start: float,
        end: float,
        step: str,
        disable_tenant_filter: bool = False,
    ) -> PrometheusQueryResult:
        if disable_tenant_filter:
            rewritten = PromQLRewriteResult(
                original=expression,
                rewritten=expression,
                metrics_seen=(),
                metrics_denied=(),
            )
        else:
            rewritten = self._injector.rewrite(expression, tenant_id=tenant_id)
        params = {
            "query": rewritten.rewritten,
            "start": str(start),
            "end": str(end),
            "step": step,
        }
        client = await self._client()
        response = await client.get(f"{self._base_url}/api/v1/query_range", params=params)
        return PrometheusQueryResult(
            rewritten_query=rewritten.rewritten,
            metrics_seen=rewritten.metrics_seen,
            data=response.json() if response.text else None,
        )


__all__ = [
    "IdentityAwarePrometheusClient",
    "PromQLDeniedError",
    "PromQLLabelInjector",
    "PromQLRewriteResult",
    "PrometheusQueryResult",
]
