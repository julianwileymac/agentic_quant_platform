"""Compatibility shim for ``aqp_models.serving.ollama``.

Custom model pulling + serving was extracted into the :mod:`aqp_models`
boundary package per ``aqp_docs/docs/concepts/platform/repository-split.md``. This shim
re-exports everything from :mod:`aqp_models.serving.ollama` so existing
imports (``from aqp.llm.ollama_client import deep_llm, quick_llm,
complete, get_crewai_llm, check_health, list_local_models, pull_model,
delete_model, list_running_models``) keep working through one release
cycle.

New code should import from :mod:`aqp_models.serving.ollama` directly.

The central LLM gateway (``router_complete``) **stays in the monolith**
at :mod:`aqp.llm.providers.router` per Hard Rule 2 in the root
``AGENTS.md``.
"""
from __future__ import annotations

from aqp_models.serving.ollama import *  # noqa: F401,F403
