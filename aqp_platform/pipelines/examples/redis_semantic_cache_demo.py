#!/usr/bin/env python3
"""Demonstrate the RedisVL-backed semantic cache.

Repeatedly calls a (mock) LLM through ``SemanticCache``; paraphrased
prompts hit the cache while novel prompts miss and populate it.
Usage::

    python -m pipelines.examples.redis_semantic_cache_demo

Outputs a small report (hit ratio, time saved) and writes counters to
the ``stats:semcache:*`` keyspace consumed by the Redis Document Store
Grafana dashboard.
"""

from __future__ import annotations

import time

from pipelines.redis_cache import SemanticCache


def fake_llm(prompt: str) -> str:
    """Pretend to be an expensive LLM call."""
    time.sleep(0.5)
    return f"Generated response for: {prompt}"


PROMPTS = [
    "What is the cache-aside pattern?",
    "Explain cache aside.",  # paraphrase #1
    "How does cache-aside work in microservices?",  # paraphrase #2
    "Tell me about Redis Streams.",
    "What is RediSearch?",
    "Describe RediSearch index types.",  # paraphrase
    "What is the cache-aside pattern?",  # exact repeat
]


def main() -> None:
    cache = SemanticCache(name="example_llm_cache", distance_threshold=0.2, ttl=600)
    if not cache.enabled:
        print("redisvl is not installed; install `redisvl` to run the demo.")
        return

    hits = 0
    misses = 0
    total_seconds = 0.0
    for prompt in PROMPTS:
        started = time.perf_counter()
        cached = cache.check(prompt)
        if cached is not None:
            hits += 1
            elapsed = time.perf_counter() - started
            total_seconds += elapsed
            print(f"HIT  ({elapsed*1000:5.0f} ms) {prompt!r} -> {cached.response!r}")
            continue
        misses += 1
        response = fake_llm(prompt)
        cache.store(prompt, response, metadata={"example": True})
        elapsed = time.perf_counter() - started
        total_seconds += elapsed
        print(f"MISS ({elapsed*1000:5.0f} ms) {prompt!r}")

    total = hits + misses
    print(
        f"\nHits: {hits}/{total} ({hits / total:.0%}); "
        f"avg latency {total_seconds / total * 1000:.0f} ms"
    )


if __name__ == "__main__":
    main()
