"""Canonical k8s label set for QuantBot bot resources.

Matches the patterns used elsewhere in the cluster (e.g.
:mod:`aqp_bots.deploy._bot_labels`).
"""
from __future__ import annotations

from typing import Any


def bot_labels(
    *,
    bot_slug: str,
    bot_kind: str = "trading",
    fleet: str | None = None,
    strategy: str | None = None,
    variant: str = "stable",
    include_app: bool = False,
    project_id: str | None = None,
) -> dict[str, str]:
    """Build the canonical label set for a Bot resource."""
    labels = {
        "app.kubernetes.io/name": "quantbot",
        "app.kubernetes.io/instance": bot_slug,
        "app.kubernetes.io/managed-by": "quantbot-operator",
        "app.kubernetes.io/part-of": "quantbot-platform",
        "quantbot.io/bot-slug": bot_slug,
        "quantbot.io/bot-kind": bot_kind,
        "quantbot.io/variant": variant,
    }
    if fleet:
        labels["quantbot.io/fleet"] = fleet
    if strategy:
        labels["quantbot.io/strategy"] = strategy
    if include_app:
        labels["app"] = f"bot-{bot_slug}"
    if project_id:
        labels["aqp.io/project-id"] = project_id
    return labels


def selector_labels(bot_slug: str) -> dict[str, str]:
    return {"app": f"bot-{bot_slug}"}


__all__ = ["bot_labels", "selector_labels"]
