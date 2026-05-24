"""Bipartite lineage layer (Workstream A + B).

Modules:

- :mod:`aqp.lineage.graph` — bipartite DAG vertex/edge ORM, writer,
  observer, content addressing.
- :mod:`aqp.lineage.openlineage` — OpenLineage outbox + Marquez relay.

The legacy flat-log :mod:`aqp.data.catalog.lineage` keeps its existing
public surface (:class:`LineageEvent`, :class:`LineageBus`,
:class:`LineageWriter`, :class:`BaseLineageObserver`); the bipartite
graph and the OpenLineage relay are purely additive observers on the
same bus.
"""
from __future__ import annotations

__all__: list[str] = []
