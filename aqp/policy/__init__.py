"""OPA policy bundle for the ingestion plane (Phase 6, plan section 10)."""
from __future__ import annotations

from aqp.policy.opa import OPAClient, evaluate_policy

__all__ = ["OPAClient", "evaluate_policy"]
