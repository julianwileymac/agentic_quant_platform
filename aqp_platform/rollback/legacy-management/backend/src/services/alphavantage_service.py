"""Alpha Vantage service layer.

Wires the :class:`alphavantage_client.AlphaVantageClient` into the management
backend:

* Owns a lazily initialised async client that shares a ``RateLimiter`` + Redis
  cache with every other AV call routed through the API.
* Exposes thin async methods that map 1:1 to the HTTP router endpoints in
  ``api/alphavantage.py``.
* Provides helpers to toggle the AV Kafka producer Deployment (replicas 0/1)
  and to submit Argo ``WorkflowTemplates`` for bulk ingestion.

Degrades gracefully when the optional ``alphavantage_client`` package is
missing by returning a ``503``-compatible error payload.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from opentelemetry import trace
from opentelemetry.trace import SpanKind

from ..config import AlphaVantageSettings, Settings

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer("rpi.management.alphavantage")

try:  # pragma: no cover - optional dependency
    from alphavantage_client import (
        AlphaVantageClient,
        AlphaVantageError,
        InvalidApiKeyError,
        RateLimiter,
        RateLimitError,
        load_api_key,
    )
    from alphavantage_client._cache import MemoryCache, RedisCache
    from alphavantage_client._rate_limiter import RateLimiterSnapshot

    _CLIENT_AVAILABLE = True
    _CLIENT_IMPORT_ERROR: str | None = None
except ImportError as exc:  # pragma: no cover
    _CLIENT_AVAILABLE = False
    _CLIENT_IMPORT_ERROR = str(exc)
    AlphaVantageClient = None  # type: ignore[assignment]
    AlphaVantageError = Exception  # type: ignore[assignment]
    InvalidApiKeyError = Exception  # type: ignore[assignment]
    RateLimiter = None  # type: ignore[assignment]
    RateLimitError = Exception  # type: ignore[assignment]
    MemoryCache = None  # type: ignore[assignment]
    RedisCache = None  # type: ignore[assignment]
    RateLimiterSnapshot = None  # type: ignore[assignment]

    def load_api_key(*args: Any, **kwargs: Any) -> None:  # type: ignore[no-redef]
        raise RuntimeError("alphavantage_client not installed")


_CLIENT_VERSION: Optional[str] = None
if _CLIENT_AVAILABLE:
    try:
        from alphavantage_client import __version__ as _CLIENT_VERSION  # type: ignore[no-redef]
    except ImportError:
        _CLIENT_VERSION = None


class AlphaVantageService:
    """Async service bridging FastAPI handlers and the AV client engine."""

    def __init__(
        self,
        settings: Settings,
        *,
        redis_client: Any | None = None,
    ) -> None:
        self.settings = settings
        self.cfg: AlphaVantageSettings = settings.alphavantage
        self._client: Any | None = None
        self._client_lock = asyncio.Lock()
        self._redis_client = redis_client
        self._credentials_loaded: bool = False
        self._credentials_error: Optional[str] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        return _CLIENT_AVAILABLE and self.cfg.enabled

    async def _get_client(self) -> Any:
        if not _CLIENT_AVAILABLE:
            raise RuntimeError(
                f"alphavantage_client package not installed: {_CLIENT_IMPORT_ERROR}"
            )
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                self._client = await asyncio.to_thread(self._build_client)
        return self._client

    def _build_client(self) -> Any:
        cache = None
        cache_backend = (self.cfg.cache_backend or "memory").lower()
        if cache_backend == "redis" and self._redis_client is not None:
            cache = RedisCache(self._redis_client, prefix="rpi:av:cache")
        elif cache_backend == "memory":
            cache = MemoryCache(max_entries=self.cfg.cache_max_entries)
        # Otherwise let AlphaVantageClient build its own default (memory).

        try:
            return AlphaVantageClient(
                api_key=self.cfg.api_key,
                api_key_file=self.cfg.api_key_file,
                extra_api_key_paths=[self.cfg.k8s_key_mount] if self.cfg.k8s_key_mount else None,
                base_url=self.cfg.base_url,
                rate_limit_rpm=self.cfg.rpm_limit,
                daily_limit=self.cfg.daily_limit,
                timeout_seconds=self.cfg.timeout_seconds,
                max_retries=self.cfg.max_retries,
                cache=cache,
                cache_backend=cache_backend,
                cache_max_entries=self.cfg.cache_max_entries,
                cache_sqlite_path=self.cfg.cache_sqlite_path,
                rapidapi=self.cfg.rapidapi,
            )
        except InvalidApiKeyError as exc:
            self._credentials_error = str(exc)
            raise

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception as exc:  # pragma: no cover
                logger.warning("AV client aclose failed: %s", exc)
            self._client = None

    # ------------------------------------------------------------------
    # Health / usage
    # ------------------------------------------------------------------

    async def health(self) -> Dict[str, Any]:
        credentials_ok = False
        message: Optional[str] = None
        if not _CLIENT_AVAILABLE:
            message = f"client library missing: {_CLIENT_IMPORT_ERROR}"
        else:
            try:
                key = await asyncio.to_thread(
                    load_api_key,
                    self.cfg.api_key,
                    file_path=self.cfg.api_key_file,
                    extra_paths=[self.cfg.k8s_key_mount] if self.cfg.k8s_key_mount else None,
                    strict=False,
                )
                credentials_ok = bool(key)
                if not credentials_ok:
                    message = "API key not resolved"
            except Exception as exc:
                message = str(exc)
        self._credentials_loaded = credentials_ok
        return {
            "enabled": self.cfg.enabled,
            "credentials_loaded": credentials_ok,
            "base_url": self.cfg.base_url,
            "rpm_limit": self.cfg.rpm_limit,
            "daily_limit": self.cfg.daily_limit,
            "cache_backend": self.cfg.cache_backend,
            "client_version": _CLIENT_VERSION,
            "client_available": _CLIENT_AVAILABLE,
            "message": message,
        }

    async def usage(self) -> Dict[str, Any]:
        client = await self._get_client()
        snap: RateLimiterSnapshot = await asyncio.to_thread(client.rate_limiter.snapshot)
        return {
            "rpm_limit": snap.rpm_limit,
            "daily_limit": snap.daily_limit,
            "requests_this_minute": snap.requests_this_minute,
            "requests_today": snap.requests_today,
            "tokens_available": snap.tokens_available,
            "next_refill_seconds": snap.next_refill_seconds,
            "daily_reset_utc": snap.daily_reset_utc,
        }

    # ------------------------------------------------------------------
    # Time series
    # ------------------------------------------------------------------

    async def timeseries(self, function: str, **params: Any) -> Any:
        client = await self._get_client()
        ts = client.timeseries
        dispatch = {
            "intraday": ts.aintraday,
            "daily": ts.adaily,
            "daily_adjusted": ts.adaily_adjusted,
            "weekly": ts.aweekly,
            "weekly_adjusted": ts.aweekly_adjusted,
            "monthly": ts.amonthly,
            "monthly_adjusted": ts.amonthly_adjusted,
        }
        with _tracer.start_as_current_span("av.timeseries", kind=SpanKind.CLIENT) as span:
            span.set_attribute("av.function", function)
            if function == "global_quote":
                result = await ts.aglobal_quote(
                    params["symbol"], entitlement=params.get("entitlement")
                )
                return result.model_dump(by_alias=False)
            if function == "bulk_quotes":
                symbols = params.get("symbols") or []
                return await ts.arealtime_bulk_quotes(symbols, entitlement=params.get("entitlement"))
            if function not in dispatch:
                raise ValueError(f"Unsupported timeseries function: {function}")
            payload = await dispatch[function](**_prune(params))
            return payload.model_dump(by_alias=False)

    async def symbol_search(self, keywords: str) -> List[Dict[str, Any]]:
        client = await self._get_client()
        hits = await client.timeseries.asearch(keywords)
        return [h.model_dump(by_alias=False) for h in hits]

    async def market_status(self) -> Dict[str, Any]:
        client = await self._get_client()
        payload = await client.timeseries.amarket_status()
        return payload.model_dump(by_alias=False)

    # ------------------------------------------------------------------
    # Fundamentals / Intelligence / Options / Forex / Crypto / ...
    # ------------------------------------------------------------------

    async def fundamentals(self, kind: str, **params: Any) -> Any:
        client = await self._get_client()
        f = client.fundamentals
        symbol = params.get("symbol", "")
        dispatch = {
            "overview": (f.aoverview, (symbol,)),
            "etf": (f.aetf_profile, (symbol,)),
            "dividends": (f.adividends, (symbol,)),
            "splits": (f.asplits, (symbol,)),
            "income": (f.aincome_statement, (symbol,)),
            "balance": (f.abalance_sheet, (symbol,)),
            "cashflow": (f.acash_flow, (symbol,)),
            "earnings": (f.aearnings, (symbol,)),
            "estimates": (f.aearnings_estimates, (symbol,)),
            "shares": (f.ashares_outstanding, (symbol,)),
        }
        if kind in dispatch:
            callable_, args = dispatch[kind]
            result = await callable_(*args)
            return _serialize(result)
        if kind == "ipo":
            return await f.aipo_calendar()
        if kind == "earnings_calendar":
            return await f.aearnings_calendar(
                symbol=params.get("symbol"), horizon=params.get("horizon"),
            )
        if kind == "listing":
            return await f.alisting_status(
                date=params.get("date"), state=params.get("state"),
            )
        raise ValueError(f"Unsupported fundamentals kind: {kind}")

    async def intelligence(self, kind: str, **params: Any) -> Any:
        client = await self._get_client()
        ai = client.intelligence
        if kind == "news":
            res = await ai.anews(**_prune(params))
            return _serialize(res)
        if kind == "transcript":
            res = await ai.aearnings_transcript(params["symbol"], params["quarter"])
            return _serialize(res)
        if kind == "top-movers":
            res = await ai.atop_movers(entitlement=params.get("entitlement"))
            return _serialize(res)
        if kind == "insider":
            items = await ai.ainsider(params["symbol"])
            return [_serialize(i) for i in items]
        if kind == "institutional":
            items = await ai.ainstitutional(params["symbol"])
            return [_serialize(i) for i in items]
        if kind == "analytics-fixed":
            res = await ai.aanalytics_fixed(**_prune(params))
            return _serialize(res)
        if kind == "analytics-sliding":
            res = await ai.aanalytics_sliding(**_prune(params))
            return _serialize(res)
        raise ValueError(f"Unsupported intelligence kind: {kind}")

    async def forex(self, kind: str, **params: Any) -> Any:
        client = await self._get_client()
        fx = client.forex
        if kind == "rate":
            res = await fx.aexchange_rate(params["from_currency"], params["to_currency"])
            return _serialize(res)
        if kind == "intraday":
            return _serialize(await fx.aintraday(**_prune(params)))
        if kind == "daily":
            return _serialize(await fx.adaily(**_prune(params)))
        if kind == "weekly":
            return _serialize(await fx.aweekly(**_prune(params)))
        if kind == "monthly":
            return _serialize(await fx.amonthly(**_prune(params)))
        raise ValueError(f"Unsupported forex kind: {kind}")

    async def crypto(self, kind: str, **params: Any) -> Any:
        client = await self._get_client()
        c = client.crypto
        if kind == "rate":
            return _serialize(await c.aexchange_rate(params["symbol"], params["market"]))
        if kind == "intraday":
            return _serialize(await c.aintraday(**_prune(params)))
        if kind == "daily":
            return _serialize(await c.adaily(params["symbol"], params["market"]))
        if kind == "weekly":
            return _serialize(await c.aweekly(params["symbol"], params["market"]))
        if kind == "monthly":
            return _serialize(await c.amonthly(params["symbol"], params["market"]))
        raise ValueError(f"Unsupported crypto kind: {kind}")

    async def options(self, kind: str, **params: Any) -> Any:
        client = await self._get_client()
        o = client.options
        if kind == "realtime":
            return _serialize(await o.arealtime(params["symbol"], contract=params.get("contract")))
        if kind == "historical":
            return _serialize(await o.ahistorical(params["symbol"], date=params.get("date")))
        if kind == "pcr-realtime":
            items = await o.arealtime_put_call_ratio(params["symbol"])
            return [_serialize(i) for i in items]
        if kind == "pcr-historical":
            items = await o.ahistorical_put_call_ratio(params["symbol"], date=params.get("date"))
            return [_serialize(i) for i in items]
        if kind == "voi-realtime":
            items = await o.arealtime_voi_ratio(params["symbol"])
            return [_serialize(i) for i in items]
        if kind == "voi-historical":
            items = await o.ahistorical_voi_ratio(params["symbol"], date=params.get("date"))
            return [_serialize(i) for i in items]
        raise ValueError(f"Unsupported options kind: {kind}")

    async def commodities(self, name: str, **params: Any) -> Any:
        client = await self._get_client()
        res = await client.commodities.aby_name(name, **_prune(params))
        return _serialize(res)

    async def economics(self, indicator: str, **params: Any) -> Any:
        client = await self._get_client()
        res = await client.economics.aby_name(indicator, **_prune(params))
        return _serialize(res)

    async def technicals(self, indicator: str, symbol: str, **params: Any) -> Any:
        client = await self._get_client()
        res = await client.technicals.aget(indicator, symbol, **_prune(params))
        return _serialize(res)

    async def indices(self, key: str, **params: Any) -> Any:
        client = await self._get_client()
        res = await client.indices.aget(key, **_prune(params))
        return _serialize(res)

    async def index_catalog(self) -> List[Dict[str, Any]]:
        client = await self._get_client()
        entries = await client.indices.acatalog()
        return [_serialize(e) for e in entries]

    # ------------------------------------------------------------------
    # Bulk load / stream controls (infra side-effects)
    # ------------------------------------------------------------------

    async def submit_bulk_workflow(
        self,
        *,
        category: str,
        symbols: Sequence[str],
        date_range: Optional[Dict[str, str]] = None,
        extra_params: Optional[Dict[str, Any]] = None,
        target_bucket: str = "av-raw",
    ) -> Dict[str, Any]:
        """Submit an Argo ``Workflow`` spawned from the AV WorkflowTemplate family.

        Uses the same pattern as ``pipelines.tasks.submit_argo_workflow_from_template``
        via the Kubernetes ``CustomObjectsApi``; kept local so the backend does
        not depend on the pipelines package directly.
        """

        from kubernetes import client as kclient  # imported lazily

        params: Dict[str, Any] = {
            "category": category,
            "symbols": ",".join(symbols),
            "target_bucket": target_bucket,
        }
        if date_range:
            params["start_date"] = date_range.get("start", "")
            params["end_date"] = date_range.get("end", "")
        if extra_params:
            for k, v in extra_params.items():
                params[k] = str(v)

        template_name = _pick_template(category)
        submitted_at = datetime.now(timezone.utc).isoformat()
        name = f"av-{category}-{submitted_at.replace(':', '').replace('-', '').replace('.', '')[:25]}".lower()

        body = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Workflow",
            "metadata": {
                "generateName": f"av-{category}-",
                "namespace": self.cfg.bulk_workflow_namespace,
                "labels": {
                    "app.kubernetes.io/name": "alphavantage-bulk",
                    "alphavantage/category": category,
                },
            },
            "spec": {
                "workflowTemplateRef": {"name": template_name},
                "serviceAccountName": self.cfg.bulk_workflow_service_account,
                "arguments": {
                    "parameters": [{"name": k, "value": str(v)} for k, v in params.items()],
                },
            },
        }

        with _tracer.start_as_current_span("argo.workflow.submit", kind=SpanKind.CLIENT) as span:
            span.set_attribute("argo.template", template_name)

            def _submit() -> Dict[str, Any]:
                api = kclient.CustomObjectsApi()
                return api.create_namespaced_custom_object(
                    group="argoproj.io",
                    version="v1alpha1",
                    namespace=self.cfg.bulk_workflow_namespace,
                    plural="workflows",
                    body=body,
                )

            resp = await asyncio.to_thread(_submit)

        return {
            "workflow_name": resp.get("metadata", {}).get("name", name),
            "namespace": self.cfg.bulk_workflow_namespace,
            "category": category,
            "status": "Submitted",
            "submitted_at": submitted_at,
            "symbols": list(symbols),
            "parameters": params,
        }

    async def list_workflows(self, *, limit: int = 25) -> List[Dict[str, Any]]:
        from kubernetes import client as kclient

        def _list() -> Dict[str, Any]:
            api = kclient.CustomObjectsApi()
            return api.list_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=self.cfg.bulk_workflow_namespace,
                plural="workflows",
                label_selector="app.kubernetes.io/name=alphavantage-bulk",
                limit=limit,
            )

        payload = await asyncio.to_thread(_list)
        items = payload.get("items", [])
        return [
            {
                "name": item["metadata"]["name"],
                "namespace": item["metadata"]["namespace"],
                "phase": item.get("status", {}).get("phase", "Unknown"),
                "started_at": item.get("status", {}).get("startedAt"),
                "finished_at": item.get("status", {}).get("finishedAt"),
                "category": item["metadata"].get("labels", {}).get("alphavantage/category"),
            }
            for item in items
        ]

    async def toggle_stream(self, *, enable: bool, replicas: int = 1) -> Dict[str, Any]:
        """Scale the AV producer Deployment in ``data-services``."""

        from kubernetes import client as kclient

        namespace = self.cfg.producer_namespace
        name = self.cfg.producer_deployment
        desired = replicas if enable else 0

        def _patch() -> Dict[str, Any]:
            apps = kclient.AppsV1Api()
            try:
                current = apps.read_namespaced_deployment_scale(name, namespace)
            except Exception:  # pragma: no cover
                current = None
            previous = int(current.spec.replicas) if current and current.spec else 0
            body = {"spec": {"replicas": int(desired)}}
            apps.patch_namespaced_deployment_scale(name, namespace, body)
            updated = apps.read_namespaced_deployment_scale(name, namespace)
            status = updated.status
            return {
                "previous_replicas": previous,
                "desired_replicas": desired,
                "ready": bool(status and status.replicas == desired),
                "message": f"{'enabled' if enable else 'disabled'} {name} -> {desired} replicas",
            }

        result = await asyncio.to_thread(_patch)
        return {"deployment": name, "namespace": namespace, **result}


_TEMPLATE_BY_CATEGORY: Dict[str, str] = {
    "timeseries": "av-bulk-timeseries",
    "intraday-backfill": "av-intraday-backfill",
    "fundamentals": "av-fundamentals",
    "universe": "av-universe-sync",
    "news": "av-news-ingest",
    "earnings": "av-earnings",
    "fx": "av-fx-backfill",
    "crypto": "av-crypto-backfill",
    "technicals": "av-technicals",
    "commodities": "av-commodities",
    "economics": "av-economics",
    "bulk": "av-bulk",
}


def _pick_template(category: str) -> str:
    return _TEMPLATE_BY_CATEGORY.get(category.lower(), "av-bulk")


def _prune(params: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None and v != ""}


def _serialize(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump(by_alias=False)
    if isinstance(obj, list):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


__all__ = ["AlphaVantageService"]
