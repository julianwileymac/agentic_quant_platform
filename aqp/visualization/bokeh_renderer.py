"""Bokeh JSON renderer for agent-produced visualization specs."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

from aqp.config import settings
from aqp.data import iceberg_catalog
from aqp.observability import get_tracer

logger = logging.getLogger(__name__)
_TRACER = get_tracer("aqp.visualization.bokeh")

ChartKind = Literal["line", "scatter", "histogram", "candlestick", "table"]


class BokehChartSpec(BaseModel):
    kind: ChartKind = "line"
    dataset_identifier: str
    title: str | None = None
    x: str = "timestamp"
    y: str = "close"
    groupby: str | None = "vt_symbol"
    limit: int = Field(default=1000, ge=1, le=50_000)
    target_id: str | None = None


def render_bokeh_item(spec: BokehChartSpec) -> dict[str, Any]:
    """Render a Bokeh ``json_item`` and cache it (Redis when configured, file-tier always).

    Caches are keyed on the spec + the underlying Iceberg snapshot id so any
    write to the source table naturally invalidates a stale chart by changing
    the cache key.
    """

    with _TRACER.start_as_current_span("bokeh.render_item") as span:
        span.set_attribute("bokeh.dataset", spec.dataset_identifier)
        span.set_attribute("bokeh.kind", spec.kind)
        span.set_attribute("bokeh.limit", spec.limit)

        cache_key = _cache_key(spec)
        span.set_attribute("bokeh.cache_key", cache_key)

        cached = _read_cache(cache_key)
        if cached is not None:
            span.set_attribute("bokeh.cache_hit", True)
            return cached
        span.set_attribute("bokeh.cache_hit", False)

        frame = _load_frame(spec)
        span.set_attribute("bokeh.rows", int(frame.shape[0]))
        item = _render_frame(spec, frame)
        item["cache_key"] = cache_key
        _write_cache(cache_key, item)
        return item


def _load_frame(spec: BokehChartSpec) -> pd.DataFrame:
    arrow = iceberg_catalog.read_arrow(spec.dataset_identifier, limit=spec.limit)
    if arrow is None:
        raise ValueError(f"dataset {spec.dataset_identifier!r} not found or empty")
    return arrow.to_pandas()


def _render_frame(spec: BokehChartSpec, frame: pd.DataFrame) -> dict[str, Any]:
    try:
        from bokeh.embed import json_item
        from bokeh.models import ColumnDataSource, DataTable, HoverTool, TableColumn
        from bokeh.plotting import figure
    except ImportError as exc:  # pragma: no cover - exercised only in lean installs
        raise RuntimeError("Install agentic-quant-platform[visualization] to render Bokeh charts") from exc

    title = spec.title or f"{spec.dataset_identifier} {spec.kind}"
    if spec.kind == "table":
        source = ColumnDataSource(frame.head(spec.limit))
        columns = [TableColumn(field=col, title=col) for col in frame.columns]
        return json_item(DataTable(source=source, columns=columns, width=900, height=420), spec.target_id)

    if spec.x not in frame.columns:
        raise ValueError(f"x column {spec.x!r} is not present")
    if spec.kind != "histogram" and spec.y not in frame.columns:
        raise ValueError(f"y column {spec.y!r} is not present")

    x_axis_type = "datetime" if pd.api.types.is_datetime64_any_dtype(frame[spec.x]) else "auto"
    plot = figure(title=title, x_axis_type=x_axis_type, height=420, sizing_mode="stretch_width")
    plot.add_tools(HoverTool(tooltips=[(spec.x, f"@{spec.x}"), (spec.y, f"@{spec.y}")]))

    if spec.kind == "histogram":
        values = pd.to_numeric(frame[spec.y], errors="coerce").dropna()
        hist = values.value_counts(bins=min(30, max(5, len(values) // 20))).sort_index()
        hist_frame = pd.DataFrame(
            {
                "left": [interval.left for interval in hist.index],
                "right": [interval.right for interval in hist.index],
                "top": hist.values,
            }
        )
        plot.quad(source=ColumnDataSource(hist_frame), top="top", bottom=0, left="left", right="right", alpha=0.6)
    elif spec.kind == "candlestick":
        required = {"open", "high", "low", "close", spec.x}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"candlestick chart requires columns: {', '.join(missing)}")
        candle = frame.sort_values(spec.x).head(spec.limit).copy()
        candle["bar_top"] = candle[["open", "close"]].max(axis=1)
        candle["bar_bottom"] = candle[["open", "close"]].min(axis=1)
        source = ColumnDataSource(candle)
        plot.segment(spec.x, "high", spec.x, "low", source=source, color="black")
        plot.vbar(spec.x, width=12 * 60 * 60 * 1000, top="bar_top", bottom="bar_bottom", source=source, alpha=0.7)
    elif spec.groupby and spec.groupby in frame.columns:
        for _, group in frame.groupby(spec.groupby, sort=False):
            source = ColumnDataSource(group.sort_values(spec.x).head(spec.limit))
            label = str(group[spec.groupby].iloc[0])
            if spec.kind == "scatter":
                plot.scatter(spec.x, spec.y, source=source, legend_label=label, size=5)
            else:
                plot.line(spec.x, spec.y, source=source, legend_label=label)
    else:
        source = ColumnDataSource(frame.sort_values(spec.x).head(spec.limit))
        if spec.kind == "scatter":
            plot.scatter(spec.x, spec.y, source=source, size=5)
        else:
            plot.line(spec.x, spec.y, source=source)

    plot.legend.click_policy = "hide"
    return json_item(plot, spec.target_id)


def _cache_key(spec: BokehChartSpec) -> str:
    payload = {
        "spec": spec.model_dump(mode="json"),
        "snapshot": _snapshot_marker(spec.dataset_identifier),
    }
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _snapshot_marker(identifier: str) -> str:
    try:
        table = iceberg_catalog.load_table(identifier)
        if table is None:
            return "missing"
        snapshot = table.current_snapshot()
        return str(getattr(snapshot, "snapshot_id", "none") if snapshot else "none")
    except Exception:  # noqa: BLE001
        return "unknown"


def _read_cache(cache_key: str) -> dict[str, Any] | None:
    """Look the entry up in Redis (when configured) then fall back to the file tier.

    Both tiers are TTL-checked against ``settings.visualization_cache_ttl_seconds``;
    expired entries are evicted before being returned so the renderer recomputes.
    """

    backend = (settings.visualization_cache_backend or "both").lower()
    if backend in {"both", "redis"}:
        cached = _redis_read(cache_key)
        if cached is not None:
            return cached
    if backend in {"both", "file"}:
        return _file_read(cache_key)
    return None


def _write_cache(cache_key: str, item: dict[str, Any]) -> None:
    backend = (settings.visualization_cache_backend or "both").lower()
    if backend in {"both", "file"}:
        _file_write(cache_key, item)
    if backend in {"both", "redis"}:
        _redis_write(cache_key, item)


def _cache_path(cache_key: str) -> Path:
    cache_dir = Path(settings.visualization_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{cache_key}.json"


def _file_read(cache_key: str) -> dict[str, Any] | None:
    cache_path = _cache_path(cache_key)
    if not cache_path.exists():
        return None
    ttl = max(int(settings.visualization_cache_ttl_seconds or 0), 0)
    if ttl > 0:
        age = time.time() - cache_path.stat().st_mtime
        if age > ttl:
            try:
                cache_path.unlink(missing_ok=True)
            except OSError:
                logger.debug("expired cache eviction failed for %s", cache_path, exc_info=True)
            return None
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        logger.debug("Bokeh cache read failed for %s", cache_path, exc_info=True)
        return None


def _file_write(cache_key: str, item: dict[str, Any]) -> None:
    try:
        _cache_path(cache_key).write_text(json.dumps(item), encoding="utf-8")
    except OSError:
        logger.warning("failed to write Bokeh file cache for %s", cache_key, exc_info=True)


_REDIS_KEY_PREFIX = "aqp:viz:bokeh:"


def _redis_client() -> Any | None:
    try:
        import redis  # local import keeps the dep optional
    except ImportError:
        return None
    try:
        return redis.Redis.from_url(settings.redis_url, decode_responses=True)
    except Exception:  # noqa: BLE001
        logger.debug("redis client init failed for visualization cache", exc_info=True)
        return None


def _redis_read(cache_key: str) -> dict[str, Any] | None:
    client = _redis_client()
    if client is None:
        return None
    try:
        raw = client.get(_REDIS_KEY_PREFIX + cache_key)
    except Exception:  # noqa: BLE001
        logger.debug("redis cache read failed for %s", cache_key, exc_info=True)
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        logger.debug("redis cache parse failed for %s", cache_key, exc_info=True)
        return None


def _redis_write(cache_key: str, item: dict[str, Any]) -> None:
    client = _redis_client()
    if client is None:
        return
    ttl = max(int(settings.visualization_cache_ttl_seconds or 0), 0)
    try:
        if ttl > 0:
            client.setex(_REDIS_KEY_PREFIX + cache_key, ttl, json.dumps(item))
        else:
            client.set(_REDIS_KEY_PREFIX + cache_key, json.dumps(item))
    except Exception:  # noqa: BLE001
        logger.debug("redis cache write failed for %s", cache_key, exc_info=True)


def clear_cache(*, older_than_seconds: int | None = None) -> dict[str, int]:
    """Evict stale Bokeh cache entries from both tiers.

    Returns ``{"file": N, "redis": M}`` indicating how many entries were removed
    from each tier. ``older_than_seconds=None`` clears everything.
    """

    summary = {"file": 0, "redis": 0}
    cache_dir = Path(settings.visualization_cache_dir)
    if cache_dir.exists():
        cutoff = time.time() - older_than_seconds if older_than_seconds is not None else None
        for path in cache_dir.glob("*.json"):
            if cutoff is not None and path.stat().st_mtime > cutoff:
                continue
            try:
                path.unlink()
                summary["file"] += 1
            except OSError:
                logger.debug("failed to delete %s", path, exc_info=True)

    client = _redis_client()
    if client is not None:
        try:
            for key in client.scan_iter(match=_REDIS_KEY_PREFIX + "*"):
                if older_than_seconds is not None:
                    ttl = client.ttl(key)
                    full_ttl = max(int(settings.visualization_cache_ttl_seconds or 0), 0)
                    age = full_ttl - ttl if (ttl is not None and ttl > 0 and full_ttl) else 0
                    if age < older_than_seconds:
                        continue
                client.delete(key)
                summary["redis"] += 1
        except Exception:  # noqa: BLE001
            logger.debug("redis cache scan failed during clear_cache", exc_info=True)

    return summary
