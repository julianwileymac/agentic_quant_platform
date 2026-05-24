"""Compatibility shim for ``aqp_models.serving.vllm``.

Custom model serving was extracted into the :mod:`aqp_models` boundary
package per ``aqp_docs/repository-split.md``. This shim re-exports
everything from :mod:`aqp_models.serving.vllm` so existing imports
(``from aqp.llm.vllm_runner import ...``) keep working through one
release cycle.

New code should import from :mod:`aqp_models.serving.vllm` directly.
"""
from __future__ import annotations

from aqp_models.serving.vllm import *  # noqa: F401,F403
