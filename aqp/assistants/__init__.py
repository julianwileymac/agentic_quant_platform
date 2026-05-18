"""Assistant Engine — interactive assistants over AQP runtimes.

Public surface:

- :class:`aqp.assistants.spec.AssistantSpec` — declarative blueprint.
- :class:`aqp.assistants.runtime.AssistantRuntime` — single sanctioned
  executor that dispatches into :class:`AgentRuntime` /
  :class:`WorkflowRuntime`.
- :func:`aqp.assistants.registry.get_assistant_spec` etc — registry.
- :class:`aqp.assistants.sandbox.AssistantSandbox` — blocked-by-default
  command sandbox.
- :func:`aqp.assistants.skills.list_markdown_skills` — read-only
  Markdown skill descriptor catalog.
"""
from __future__ import annotations

from aqp.assistants.registry import (
    add_assistant_spec,
    clear_assistant_registry,
    get_assistant_spec,
    list_assistant_specs,
    persist_spec,
    register_assistant,
    reload_yaml_dir,
    replay_spec_version,
)
from aqp.assistants.runtime import AssistantRuntime, runtime_for
from aqp.assistants.sandbox import (
    AssistantSandbox,
    SandboxExecutionResult,
    SandboxPolicyError,
)
from aqp.assistants.skills import (
    AssistantSkillDescriptor,
    default_skill_root,
    list_markdown_skills,
)
from aqp.assistants.spec import (
    AssistantMemoryPolicy,
    AssistantModelPolicy,
    AssistantSandboxPolicy,
    AssistantSpec,
    AssistantToolPolicy,
)

__all__ = [
    "AssistantMemoryPolicy",
    "AssistantModelPolicy",
    "AssistantRuntime",
    "AssistantSandbox",
    "AssistantSandboxPolicy",
    "AssistantSkillDescriptor",
    "AssistantSpec",
    "AssistantToolPolicy",
    "SandboxExecutionResult",
    "SandboxPolicyError",
    "add_assistant_spec",
    "clear_assistant_registry",
    "default_skill_root",
    "get_assistant_spec",
    "list_assistant_specs",
    "list_markdown_skills",
    "persist_spec",
    "register_assistant",
    "reload_yaml_dir",
    "replay_spec_version",
    "runtime_for",
]
