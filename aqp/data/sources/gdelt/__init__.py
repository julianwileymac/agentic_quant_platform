"""GDelt GKG 2.0 adapter — hybrid manifest + BigQuery.

Install the optional extra to enable the manifest path:

    pip install "agentic-quant-platform[gdelt]"

And/or the BigQuery federation path:

    pip install "agentic-quant-platform[gdelt-bq]"
    export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

Both paths expose the same :class:`GDeltAdapter` façade so callers
don't need to know which backend served a particular query.
"""
from __future__ import annotations

from aqp.data.sources.gdelt.adapter import GDeltAdapter
from aqp.data.sources.gdelt.manifest import GDeltManifest, ManifestEntry
from aqp.data.sources.gdelt.schema import GKG_COLUMNS
from aqp.data.sources.gdelt.subject_filter import SubjectFilter, SubjectMatch

__all__ = [
    "GDeltAdapter",
    "GDeltManifest",
    "GKG_COLUMNS",
    "ManifestEntry",
    "SubjectFilter",
    "SubjectMatch",
]
