---
title: 'Temporal identifier resolution'
summary: 'Financial identifiers are not stable across time. A non-exhaustive list of why:'
owner: platform-team
last_reviewed: 2026-05-25
audience: both
---

# Temporal identifier resolution

> Status: **Phase 1 shipped** (Alembic 0039 + 0040). The
> ``identifier_links`` table is now the authoritative source for
> identifier resolution; the legacy ``Instrument.identifiers`` JSON
> blob is kept for backward compatibility but is no longer
> authoritative.

## Why temporal resolution

Financial identifiers are not stable across time. A non-exhaustive
list of why:

| Event | Impact |
| --- | --- |
| Ticker change (M&A, rebranding) | ``FB`` -> ``META`` 2022-06-09 |
| Symbol change (re-listing) | ``ABEV3`` ↔ ``AMBV4`` on B3 |
| CUSIP / ISIN re-issue (corporate action) | Stock split issuance may mint a new CUSIP |
| Index reconstitution | Russell add/drops change tracker constituents |
| ADR sponsorship upgrade | Conversion ratio may change |

A backtest that resolves ``META`` to the modern ID and walks bar data
from 2018 will silently introduce **survivorship and forward-looking
bias** because the row didn't yet exist under that ticker. The
resolver service fixes this by walking time-versioned
``identifier_links`` rows scoped by ``valid_from <= as_of`` and
``(valid_to IS NULL OR valid_to > as_of)``.

## Table shape

The ``identifier_links`` table predates Phase 1; Phase 1 promotes it
to authoritative status. Its schema:

```text
identifier_links
+--------------------+-----------------------------------------------+
| id                 | UUID                                          |
| entity_kind        | instrument | fred_series | sec_filing | ...   |
| entity_id          | parent entity id                              |
| instrument_id      | denormalized FK to instruments.id (NULL OK)   |
| scheme             | ticker | vt_symbol | cik | cusip | isin |     |
|                    | figi | sedol | lei | gvkey | permid | ...     |
| value              | identifier value                              |
| valid_from         | datetime | NULL ("from the beginning")        |
| valid_to           | datetime | NULL ("still valid")               |
| source_id          | FK to data_sources.id                         |
| confidence         | 0.0 - 1.0, defaults 1.0                       |
| meta               | JSON                                          |
| created_at         | datetime                                      |
+--------------------+-----------------------------------------------+
```

## Resolver API

The two public entry points are
:class:`aqp.data.identity.IdentifierResolver` and the matching
DataMCP tools.

### Python: forward resolution

```python
from datetime import datetime
from aqp.data.identity import resolve

# "What was AAPL's CUSIP on 2018-06-12?"
hit = resolve(
    scheme="cusip",
    value="037833100",
    as_of=datetime(2018, 6, 12),
)
print(hit.value, hit.is_open_ended)
```

### Python: history walk

```python
from aqp.data.identity import history

# Every alias known for Apple
for row in history(entity_kind="instrument", entity_id="aapl-uuid"):
    print(row.scheme, row.value, row.valid_from, row.valid_to)
```

### Agent / MCP

```text
data.identity.resolve(scheme="cusip", value="037833100", as_of="2018-06-12")
data.identity.history(entity_kind="instrument", entity_id="aapl-uuid")
```

The DataMCP layer is the only path agents may use to resolve
identifiers (AGENTS rule 22). The Python module is reserved for
loaders / pipelines / persistence code; agent code never imports the
ORM model directly.

## Backfill from legacy JSON blob (migration 0040)

The legacy ``Instrument.identifiers`` JSON column is a flat
``{scheme: value}`` map. Migration 0040 walks every row, normalises
the scheme name (lower-cased, aliases collapsed), and inserts a row
into ``identifier_links`` with ``valid_from=valid_to=NULL`` ("valid
for all time the row represents") and ``confidence=0.7`` (so a
canonical loader row at ``confidence=1.0`` always wins the resolver
tiebreaker).

The legacy JSON column is **kept**: readers that haven't migrated to
the resolver continue to work. New readers MUST go through the
resolver so they see corrected validity windows.

## Validity-window semantics

| ``valid_from`` | ``valid_to`` | Meaning |
| --- | --- | --- |
| ``NULL`` | ``NULL`` | Valid for all time the row represents |
| ``2018-01-01`` | ``NULL`` | Valid from 2018-01-01, still current |
| ``NULL`` | ``2022-06-09`` | Valid up to (and including) 2022-06-09 |
| ``2010-05-01`` | ``2015-12-31`` | Valid in the closed-open interval |

The ``valid_to`` is **exclusive** -- a row with ``valid_to=2022-06-09``
is NOT valid on 2022-06-09. The lookup predicate is therefore
``valid_to > as_of``, not ``valid_to >= as_of``.

## Confidence ordering

When multiple rows satisfy the validity predicate, the highest
``confidence`` wins. Default loader rows ship with
``confidence=1.0``; the legacy-blob backfill from migration 0040
uses ``confidence=0.7`` so it's overridden the moment a canonical
loader populates the same alias.

Heuristic / fuzzy-match loaders should use ``confidence`` in the
0.3-0.6 range so they only win when no canonical row exists.
