"""Compact, filterable, row-clickable data table for every entity list.

Wraps :class:`solara.DataFrame` to add:

- quick client-side filter by free-text query across columns
- optional column whitelist + display formatting
- optional ``on_row_click`` (renders a 'Open' button per row)
- "compact" density for dense paneled layouts.
"""
from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterable
from typing import Any

import pandas as pd
import solara


@solara.component
def EntityTable(
    rows: list[dict[str, Any]] | pd.DataFrame,
    *,
    columns: Iterable[str] | None = None,
    on_row_click: Callable[[dict[str, Any]], None] | None = None,
    id_column: str = "id",
    label_columns: Iterable[str] | None = None,
    empty: str = "_Nothing to show yet._",
    items_per_page: int = 15,
    searchable: bool = True,
    density: str = "compact",
    title: str | None = None,
) -> None:
    search_text = solara.use_reactive("")

    df = _to_dataframe(rows)
    if columns is not None and not df.empty:
        keep = [c for c in columns if c in df.columns]
        if keep:
            df = df[keep].copy()

    with solara.Column(gap="6px"):
        if title:
            solara.Markdown(f"#### {title}")
        if df.empty:
            solara.Markdown(empty)
            return
        if searchable:
            solara.InputText(
                "Filter",
                value=search_text,
                on_value=lambda v: search_text.set(v),
            )
        filtered = _apply_filter(df, search_text.value)

        if density == "compact":
            _render_compact(filtered, items_per_page)
        else:
            with contextlib.suppress(Exception):
                solara.DataFrame(filtered, items_per_page=items_per_page)

        if on_row_click is not None:
            _render_actions(
                filtered,
                id_column=id_column,
                label_columns=list(label_columns or ()),
                on_row_click=on_row_click,
            )


def _to_dataframe(rows: list[dict[str, Any]] | pd.DataFrame) -> pd.DataFrame:
    if isinstance(rows, pd.DataFrame):
        return rows
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _apply_filter(df: pd.DataFrame, query: str) -> pd.DataFrame:
    if not query.strip():
        return df
    needle = query.strip().lower()
    try:
        mask = df.apply(
            lambda s: s.astype(str).str.lower().str.contains(needle, na=False)
        ).any(axis=1)
        return df.loc[mask]
    except Exception:
        return df


def _render_compact(df: pd.DataFrame, items_per_page: int) -> None:
    """Tighter rendering than `solara.DataFrame` by default.

    We use the underlying DataFrame widget but wrap it in a scroll container
    with a fixed max-height, so a 50-row table stops dominating the page.
    """
    with solara.Div(
        style={
            "max-height": f"{min(items_per_page + 3, 30) * 28}px",
            "overflow-y": "auto",
            "border": "1px solid rgba(148, 163, 184, 0.25)",
            "border-radius": "8px",
        }
    ):
        with contextlib.suppress(Exception):
            solara.DataFrame(df, items_per_page=items_per_page)


def _render_actions(
    df: pd.DataFrame,
    *,
    id_column: str,
    label_columns: list[str],
    on_row_click: Callable[[dict[str, Any]], None],
) -> None:
    if id_column not in df.columns:
        return
    # Show the first 8 rows as click-throughs so the user does not need to
    # copy-paste UUIDs — matches the Strategy Browser's "Open a strategy" UX.
    limit = min(len(df), 8)
    with solara.Column(gap="4px"):
        solara.Markdown("**Open row**")
        with solara.Row(gap="6px"):
            for _, row in df.head(limit).iterrows():
                rid = row[id_column]
                short = str(rid)[:8]
                labels = [str(row[c]) for c in label_columns if c in row.index]
                label = " / ".join([short, *labels]) if labels else short
                solara.Button(
                    label,
                    on_click=lambda r=row.to_dict(): on_row_click(r),
                    outlined=True,
                    dense=True,
                )
