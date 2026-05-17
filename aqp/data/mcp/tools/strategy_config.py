"""Controlled-write DataMCP tool for strategy YAML mutations.

Lets the toxicity-aware regime adapter agent (see
``configs/agents/research_toxicity_regime_adapter.yaml``) update a
small whitelist of fields on a ``configs/paper/*.yaml`` file. Every
update emits a :class:`~aqp.data.catalog.lineage.LineageEvent` with
``transform_kind="strategy.parameter_update"`` so the change is
auditable and reversible.

The whitelist is intentionally narrow:

- ``gamma`` — Avellaneda-Stoikov risk aversion (or Lucic-Tse
  ``gamma_inv``).
- ``sigma`` — assumed mid-price volatility.
- ``kappa`` — order-book liquidity / temporary impact.
- ``order_size`` — order quantity.
- ``max_position`` — inventory cap.

Anything outside the whitelist is rejected up-front so the agent can
not e.g. flip the broker, the symbol, or the kill-switch through this
tool. Hard-coded fields like ``broker`` / ``symbol`` / ``account_id``
require a different (yet-to-be-built) higher-privilege tool.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.policy import enforce_tenancy
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


_ALLOWED_FIELDS: frozenset[str] = frozenset({
    "gamma",
    "sigma",
    "kappa",
    "k",
    "gamma_inv",
    "base_spread",
    "order_size",
    "max_position",
})


def _resolve_paper_dir() -> Path:
    """Locate ``<repo>/configs/paper`` regardless of CWD.

    Walks up from this module file until it sees a ``configs/paper``
    directory, then returns it. Falls back to ``./configs/paper``.
    """
    here = Path(__file__).resolve()
    for parent in [*here.parents]:
        candidate = parent / "configs" / "paper"
        if candidate.exists():
            return candidate
    return Path("configs/paper").resolve()


class UpdateStrategyConfigInput(BaseModel):
    """Input schema for ``data.strategy_config.update``."""

    config_path: str = Field(
        ...,
        description=(
            "Relative path under configs/paper/ (e.g. "
            "'avellaneda_stoikov_quotes.yaml')."
        ),
    )
    field_path: str = Field(
        ...,
        description=(
            "Dotted path to the field to update — only the leaf must "
            "be in the allowed whitelist. e.g. 'strategy.gamma'."
        ),
    )
    new_value: float = Field(..., description="Replacement scalar value.")
    reason: str = Field(
        default="",
        description="Human-readable rationale stamped on the lineage event.",
    )


@register_data_mcp_tool
class UpdateStrategyConfigTool(DataMCPTool):
    """Controlled writer that mutates a ``configs/paper/*.yaml`` file."""

    name = "data.strategy_config.update"
    description = (
        "Update a whitelisted scalar field (gamma / sigma / kappa / "
        "order_size / max_position / gamma_inv / base_spread) on a "
        "configs/paper/*.yaml file and emit a lineage event. Reject "
        "any field outside the whitelist. Used by the toxicity-aware "
        "regime adapter to hot-tune a paper-trading session."
    )
    args_schema = UpdateStrategyConfigInput
    category = "strategy_config"
    tags = ("strategy_config", "writer", "regime_adapter")
    mutates = True
    required_scopes = ("data:read", "strategy:write")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        config_path: str,
        field_path: str,
        new_value: float,
        reason: str = "",
    ) -> MCPToolResult:
        # 1. Whitelist check on the leaf field name.
        leaf = field_path.rsplit(".", 1)[-1]
        if leaf not in _ALLOWED_FIELDS:
            return MCPToolResult(
                ok=False,
                error=(
                    f"field {leaf!r} is not in the whitelist "
                    f"({sorted(_ALLOWED_FIELDS)}); reject by design."
                ),
            )
        if not config_path.endswith(".yaml") and not config_path.endswith(".yml"):
            return MCPToolResult(
                ok=False,
                error="config_path must end in .yaml/.yml",
            )

        paper_dir = _resolve_paper_dir()
        target = (paper_dir / config_path).resolve()
        # Ensure the file lives under configs/paper/ — defence against
        # path-traversal abuse via "../" segments.
        try:
            target.relative_to(paper_dir.resolve())
        except ValueError:
            return MCPToolResult(
                ok=False,
                error=(
                    "config_path escapes configs/paper/ — refusing to "
                    "write outside the paper directory."
                ),
            )
        if not target.exists():
            return MCPToolResult(
                ok=False, error=f"config not found: {target}"
            )

        # 2. Load YAML, apply update, write back.
        try:
            content = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False, error=f"failed to parse {target}: {exc}"
            )
        old_value = self._get_dotted(content, field_path)
        if old_value is not None:
            try:
                old_value = float(old_value)
            except Exception:  # noqa: BLE001
                pass
        self._set_dotted(content, field_path, float(new_value))
        try:
            target.write_text(
                yaml.safe_dump(content, sort_keys=False, default_flow_style=False),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False, error=f"failed to write {target}: {exc}"
            )

        # 3. Emit a lineage event so the change is auditable.
        try:
            from aqp.data.catalog.lineage import LineageEvent, get_lineage_bus

            get_lineage_bus().emit(
                LineageEvent(
                    transform_kind="strategy.parameter_update",
                    actor=ctx.actor or "regime_adapter",
                    actor_kind=ctx.actor_kind or "agent",
                    service_name="data_mcp",
                    summary=f"updated {field_path} on {config_path}",
                    workspace_id=ctx.workspace_id,
                    project_id=ctx.project_id,
                    details={
                        "config_path": str(config_path),
                        "field_path": field_path,
                        "old_value": old_value,
                        "new_value": float(new_value),
                        "reason": str(reason),
                        "session_id": ctx.session_id,
                    },
                )
            )
        except Exception:  # noqa: BLE001
            logger.debug("lineage emit failed for strategy update", exc_info=True)

        return MCPToolResult(
            ok=True,
            data={
                "config_path": str(target),
                "field_path": field_path,
                "old_value": old_value,
                "new_value": float(new_value),
                "reason": reason,
            },
            summary=f"{config_path}: {field_path} {old_value} -> {new_value}",
        )

    @staticmethod
    def _get_dotted(d: dict[str, Any], path: str) -> Any:
        cur: Any = d
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return None
        return cur

    @staticmethod
    def _set_dotted(d: dict[str, Any], path: str, value: Any) -> None:
        parts = path.split(".")
        cur = d
        for part in parts[:-1]:
            if part not in cur or not isinstance(cur[part], dict):
                cur[part] = {}
            cur = cur[part]
        cur[parts[-1]] = value


__all__ = ["UpdateStrategyConfigTool"]
