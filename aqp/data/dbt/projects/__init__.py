"""dbt-mesh projects for AQP (Phase 2 — plan section 6).

Layout::

    aqp/data/dbt/projects/
    ├── core/                shared aqp-dbt-core (Platform)
    │   ├── dbt_project.yml
    │   ├── packages.yml
    │   ├── profiles.yml
    │   ├── macros/
    │   ├── models/
    │   │   ├── staging/
    │   │   ├── intermediate/
    │   │   └── core_facts/
    │   └── snapshots/
    ├── equities/            per-team downstream
    ├── derivatives/         per-team downstream
    └── macro/               per-team downstream

Cross-project ``ref()`` lookups go through dbt-loom v0.9.4 (the
OSS path to dbt Mesh). Each team project pulls the shared
``manifest.json`` from S3 via the
:mod:`aqp.data.dbt.loom_registry` sidecar.
"""
from __future__ import annotations
