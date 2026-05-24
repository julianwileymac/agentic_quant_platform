"""AQP notebook helpers.

Public surface used by AQP-scaffolded Jupyter notebooks (created by
``theia-ide-aqp-notebook-quant-ext``'s `New AQP Notebook` command) and by
human-authored notebooks that want the same ergonomic clients.

The single public entry point is :func:`attach`, exposed here so a
notebook cell can simply ``from aqp.notebook.helpers import attach``.
"""

from __future__ import annotations

from .helpers import AqpNotebookContext, attach

__all__ = ["attach", "AqpNotebookContext"]
