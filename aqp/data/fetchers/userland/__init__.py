"""User-generated Airbyte builder fetchers (data fabric phase 2).

Files in this package are emitted by
:func:`aqp.data.airbyte.builder.codegen_fetcher.state_to_fetcher_stub`
when the operator toggles "Custom Python" in the visual builder.
The generated stubs register through ``@register_source_fetcher``
and resolve credentials via :class:`aqp.credentials.CredentialResolver`,
keeping AGENTS hard rule 26 intact.
"""
from __future__ import annotations
