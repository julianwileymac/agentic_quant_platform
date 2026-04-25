"""CrewAI crew factory — assembles the full research crew from a YAML recipe.

The default recipe is ``configs/agents/research_crew.yaml``. The crew runs a
six-stage sequential pipeline: discover → hypothesise → backtest → risk-audit →
evaluate → promote. Each task handoff goes through the shared :class:`Session`.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from crewai import Crew, Process, Task

from aqp.agents.roles import (
    make_data_scout,
    make_hypothesis_designer,
    make_meta_agent,
    make_performance_evaluator,
    make_risk_controller,
    make_strategy_backtester,
)

logger = logging.getLogger(__name__)

DEFAULT_CREW_CONFIG = Path("configs/agents/research_crew.yaml")


AGENT_FACTORIES = {
    "data_scout": make_data_scout,
    "hypothesis_designer": make_hypothesis_designer,
    "strategy_backtester": make_strategy_backtester,
    "risk_controller": make_risk_controller,
    "performance_evaluator": make_performance_evaluator,
    "meta_agent": make_meta_agent,
}


def build_research_crew(
    user_prompt: str,
    config_path: Path | str = DEFAULT_CREW_CONFIG,
) -> Crew:
    """Load the crew YAML and instantiate all agents + tasks."""
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"No crew config at {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    verbose = bool(cfg.get("verbose", True))
    process_name = (cfg.get("process", "sequential") or "sequential").lower()
    process = Process.sequential if process_name == "sequential" else Process.hierarchical

    agents = {key: factory() for key, factory in AGENT_FACTORIES.items()}

    tasks: list[Task] = []
    prev: Task | None = None
    for t in cfg.get("tasks", []):
        agent_key = t["agent"]
        description = t["description"] + f"\n\nUser prompt:\n{user_prompt}"
        expected_output = t.get("expected_output", "A concise, well-structured answer.")
        task = Task(
            description=description,
            expected_output=expected_output,
            agent=agents[agent_key],
            context=[prev] if prev else None,
        )
        tasks.append(task)
        prev = task

    crew = Crew(
        agents=list(agents.values()),
        tasks=tasks,
        process=process,
        verbose=verbose,
        memory=False,
    )
    return crew


def run_research_crew(
    user_prompt: str,
    config_path: Path | str = DEFAULT_CREW_CONFIG,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Synchronously run the full research pipeline. Returns a dict of outputs."""
    crew = build_research_crew(user_prompt, config_path)
    logger.info("Running research crew for prompt: %s", user_prompt[:120])
    result = crew.kickoff(inputs=inputs or {})
    return {
        "prompt": user_prompt,
        "result": str(result),
        "tasks_output": [str(t.output) for t in crew.tasks if t.output],
    }
