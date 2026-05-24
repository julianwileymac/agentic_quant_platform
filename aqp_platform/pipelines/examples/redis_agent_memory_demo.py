#!/usr/bin/env python3
"""Minimal LangGraph + Redis agent memory demo.

Mirrors the upstream langgraph-redis examples: builds a tiny graph, runs
two messages on the same thread, and shows that the second invocation
sees state from the first thanks to the Redis checkpointer.  If
``langgraph-checkpoint-redis`` is not installed the script exits with a
helpful message instead of a stack trace.

Usage::

    python -m pipelines.examples.redis_agent_memory_demo
"""

from __future__ import annotations

import sys

from pipelines.agent_memory import get_checkpointer, get_store, langgraph_available
from pipelines.config import get_redis_settings
from pipelines.redis_io import ping, require_modules


def main() -> None:
    if not langgraph_available():
        print(
            "langgraph-checkpoint-redis is not installed.\n"
            "Run `pip install langgraph-checkpoint-redis langgraph` and retry."
        )
        sys.exit(0)

    if not ping():
        raise SystemExit("Cannot reach Redis. Check REDIS_URL / REDIS_PASSWORD.")
    require_modules(("search", "rejson"))

    from typing import Annotated, TypedDict

    from langgraph.graph import END, START, StateGraph
    from langgraph.graph.message import add_messages

    class AgentState(TypedDict):
        messages: Annotated[list, add_messages]

    def remember(state: AgentState) -> AgentState:
        last = state["messages"][-1].content if state["messages"] else "(empty)"
        return {"messages": [("ai", f"Got it - I will remember: {last}")]}

    builder = StateGraph(AgentState)
    builder.add_node("remember", remember)
    builder.add_edge(START, "remember")
    builder.add_edge("remember", END)

    print(f"Connecting to Redis at {get_redis_settings().host}:{get_redis_settings().port}")
    checkpointer = get_checkpointer()
    store = get_store(vector_dims=16)

    graph = builder.compile(checkpointer=checkpointer, store=store)

    config = {"configurable": {"thread_id": "demo-thread"}}
    print("\n--- First call ---")
    result1 = graph.invoke({"messages": [("user", "My favorite color is teal.")]}, config)
    for m in result1["messages"]:
        print(f"  {m.type}: {m.content}")

    print("\n--- Second call (same thread, sees prior state) ---")
    result2 = graph.invoke({"messages": [("user", "Remind me what I like.")]}, config)
    for m in result2["messages"]:
        print(f"  {m.type}: {m.content}")


if __name__ == "__main__":
    main()
