"""Custom model-serving primitives.

This subpackage owns the slice of the historical ``aqp.llm`` package
that handled custom model pulling and serving — i.e. the parts that
are about *the model itself*, not the LLM gateway:

- :mod:`aqp_models.serving.vllm` — vLLM in-process / Compose-managed
  service controller (formerly ``aqp.llm.vllm_runner``).
- :mod:`aqp_models.serving.ollama` — Ollama client + tier helpers
  (``deep_llm`` / ``quick_llm``) and lifecycle helpers
  (``pull_model`` / ``delete_model`` / ``list_running_models``)
  (formerly ``aqp.llm.ollama_client``).

The central LLM gateway (``router_complete``) **stays in the monolith**
at ``aqp/llm/providers/router.py`` per Hard Rule 2 in the root
``AGENTS.md``. This subpackage owns model-pulling and serving
primitives, not the gateway.
"""
from __future__ import annotations
