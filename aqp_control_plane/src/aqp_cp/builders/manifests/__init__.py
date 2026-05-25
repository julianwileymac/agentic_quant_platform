"""Jinja2 manifest templates rendered into Kubernetes server-side-apply payloads.

Each ``*.yaml.j2`` template emits a single Kubernetes object. The
matching renderer in the parent module loads the template via
:class:`jinja2.PackageLoader` and returns a parsed dict ready for
``client.<Api>.create_or_replace_*`` calls.
"""
from __future__ import annotations

__all__: list[str] = []
