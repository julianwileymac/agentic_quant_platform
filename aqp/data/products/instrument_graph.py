"""Instrument-graph data product.

Walks the entity graph rooted at one ``vt_symbol`` (or root id) and
returns a bounded breadth-first slice for the LLM context pack.
Useful for "show me everything related to AAPL.NASDAQ" style queries
where the agent needs the issuer, sector, peers, identifier links,
and adjacent regulatory entries in one shot.
"""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import Any

from sqlalchemy import select

from aqp.data.products.base import BaseDataProduct, DataProductError
from aqp.persistence.db import get_session
from aqp.persistence.models import IdentifierLink, Instrument

logger = logging.getLogger(__name__)


class InstrumentGraphProduct(BaseDataProduct):
    """Bounded BFS walk of the AQP entity graph."""

    product_kind = "instrument_graph"

    def __init__(
        self,
        root_vt_symbol: str,
        *,
        as_of: datetime | None = None,
        depth: int = 2,
        max_nodes: int = 50,
    ) -> None:
        super().__init__(entity_id=root_vt_symbol, as_of=as_of)
        self.root_vt_symbol = str(root_vt_symbol)
        self.depth = max(int(depth), 1)
        self.max_nodes = max(int(max_nodes), 1)

    def load(self) -> None:
        with get_session() as session:
            root = (
                session.execute(
                    select(Instrument).where(Instrument.vt_symbol == self.root_vt_symbol)
                )
                .scalars()
                .first()
            )
            if root is None:
                raise DataProductError(
                    f"no instrument with vt_symbol={self.root_vt_symbol!r}"
                )

            nodes: dict[str, dict[str, Any]] = {}
            edges: list[dict[str, Any]] = []
            queue: deque[tuple[str, int]] = deque([(root.id, 0)])
            self._add_node(nodes, root)
            visited = {root.id}
            while queue and len(nodes) < self.max_nodes:
                current_id, level = queue.popleft()
                if level >= self.depth:
                    continue
                # Issuer relationship
                if hasattr(self, "_walk_issuer"):
                    self._walk_issuer(session, nodes, edges, queue, visited, current_id, level + 1)
                # Identifier links from this instrument
                for link in (
                    session.execute(
                        select(IdentifierLink).where(
                            IdentifierLink.instrument_id == current_id
                        )
                    )
                    .scalars()
                    .all()
                ):
                    edge_id = f"identifier:{link.id}"
                    edges.append(
                        {
                            "id": edge_id,
                            "kind": "identifier_link",
                            "from": current_id,
                            "to": f"identifier:{link.value}:{link.scheme}",
                            "scheme": link.scheme,
                            "value": link.value,
                            "confidence": float(link.confidence)
                            if link.confidence is not None
                            else None,
                        }
                    )

            self._payload["nodes"] = list(nodes.values())
            self._payload["edges"] = edges
            self._payload["truncated"] = len(nodes) >= self.max_nodes

        self.add_provenance_source("instruments")
        self.add_lineage(
            transform_kind="data_product_load",
            target_table_id=None,
            summary=(
                f"loaded instrument graph rooted at {self.root_vt_symbol} "
                f"depth={self.depth} nodes={len(self._payload.get('nodes') or [])}"
            ),
            actor=self.product_kind,
        )

    @staticmethod
    def _add_node(nodes: dict[str, dict[str, Any]], instrument: Instrument) -> None:
        nodes[instrument.id] = {
            "id": instrument.id,
            "kind": "instrument",
            "vt_symbol": instrument.vt_symbol,
            "ticker": instrument.ticker,
            "exchange": instrument.exchange,
            "asset_class": instrument.asset_class,
            "instrument_class": instrument.instrument_class,
            "issuer_id": instrument.issuer_id,
            "sector": instrument.sector,
            "industry": instrument.industry,
        }

    def _walk_issuer(
        self,
        session,
        nodes: dict[str, dict[str, Any]],
        edges: list[dict[str, Any]],
        queue: deque[tuple[str, int]],
        visited: set[str],
        instrument_id: str,
        next_level: int,
    ) -> None:
        try:
            instrument = session.get(Instrument, instrument_id)
        except Exception:  # noqa: BLE001
            return
        if instrument is None or not instrument.issuer_id:
            return
        try:
            from aqp.persistence.models_entities import Issuer

            issuer = session.get(Issuer, instrument.issuer_id)
        except Exception:  # noqa: BLE001
            return
        if issuer is None:
            return
        if issuer.id not in nodes:
            nodes[issuer.id] = {
                "id": issuer.id,
                "kind": "issuer",
                "name": getattr(issuer, "name", None),
                "country": getattr(issuer, "country", None),
                "lei": getattr(issuer, "lei", None),
                "cik": getattr(issuer, "cik", None),
                "sector_id": getattr(issuer, "sector_id", None),
                "industry_id": getattr(issuer, "industry_id", None),
            }
        edges.append(
            {
                "kind": "issuer_link",
                "from": instrument_id,
                "to": issuer.id,
            }
        )
        if next_level < self.depth and issuer.id not in visited:
            visited.add(issuer.id)
            # We don't enqueue issuer.id back into the instrument BFS
            # because we'd need to switch graph kinds; the issuer is
            # captured as a leaf node for now.


__all__ = ["InstrumentGraphProduct"]
