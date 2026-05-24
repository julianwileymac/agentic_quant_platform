"""Celery tasks triggered by Auth0 log-stream session-revocation events.

AGENTS hard rule 53: when Auth0 fires a session-revoke / user-delete /
suspicious-API event, the AQP backend halts every in-flight runtime
acting on the affected user's behalf and revokes their externally
issued OAuth tokens. This task module is the cleanup engine — it is
intentionally narrow so it can be safely retried by Celery on
transient failures.

Mutating operations:

- :class:`aqp.persistence.models_agents.AgentRunV2` — flip
  ``status="halted"`` for every ``running`` / ``pending`` row owned
  by the user; revoke the Celery task.
- :class:`aqp.persistence.models.PaperTradingRun` — publish a stop
  signal via :func:`aqp.tasks.paper_tasks.publish_stop_signal`.
- :class:`aqp.persistence.models_bots.BotDeployment` — flip the
  ``active`` rows to ``halted`` and stop the underlying paper sessions.
- :class:`aqp.persistence.models_rl.RLRun` — revoke + halt.
- :class:`aqp.persistence.models_workflows.WorkflowRun` — revoke + halt.
- :class:`aqp.persistence.models_terraform.TerraformRun` — revoke +
  halt, but ONLY for non-destructive ``plan`` / ``refresh`` runs;
  in-flight ``apply`` / ``destroy`` runs are left alone (and audited
  as a warning) because mid-apply halts leave Terraform state in an
  inconsistent place.
- :class:`aqp.persistence.models_oauth_tokens.UserOAuthToken` — set
  ``revoked_at`` so :class:`UserOAuthTokenStore` returns ``None``
  on the next resolution.
- :func:`aqp.auth.token_exchange.get_token_exchange_broker().invalidate`
  — drop cached delegated agent tokens for this user (so any
  in-flight agent that's mid-run can't mint another one).

The task is idempotent by construction: re-running it after a partial
failure halts only the rows that are still ``running`` / ``pending``.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="aqp.tasks.session_revocation_tasks.cleanup_for_user",
    autoretry_for=(),
    max_retries=0,
)
def cleanup_for_user(
    self,
    *,
    internal_user_id: str | None,
    auth0_user_id: str | None,
    reason: str,
) -> dict[str, Any]:
    """Halt every runtime + revoke OAuth tokens for one user.

    Either ``internal_user_id`` or ``auth0_user_id`` MUST be set.
    When both are present, the internal id wins for the SQL filters;
    the auth0 id is forwarded to the delegated-token broker's
    invalidation path so it can drop cached tokens minted against
    that subject.

    ``reason`` is the Auth0 event-type code (e.g. ``"sdu"`` /
    ``"sapi"``) and is stamped onto every halted row + every audit
    event so post-mortem queries can correlate the halt with the
    triggering event.
    """
    task_id = self.request.id or "local"
    emit(
        task_id,
        "start",
        f"session-revocation cleanup user={internal_user_id or auth0_user_id} reason={reason}",
    )

    summary: dict[str, Any] = {
        "internal_user_id": internal_user_id,
        "auth0_user_id": auth0_user_id,
        "reason": reason,
        "halted": {
            "agent_runs_v2": 0,
            "paper_trading_runs": 0,
            "bot_deployments": 0,
            "rl_runs": 0,
            "workflow_runs": 0,
            "terraform_runs": 0,
            "terraform_runs_skipped_destructive": 0,
        },
        "oauth_tokens_revoked": 0,
        "delegated_tokens_invalidated": 0,
        "errors": [],
    }

    try:
        if internal_user_id:
            _halt_agent_runs(internal_user_id, reason, summary)
            _halt_paper_runs(internal_user_id, reason, summary)
            _halt_bot_deployments(internal_user_id, reason, summary)
            _halt_rl_runs(internal_user_id, reason, summary)
            _halt_workflow_runs(internal_user_id, reason, summary)
            _halt_terraform_runs(internal_user_id, reason, summary)
            _revoke_oauth_tokens(internal_user_id, reason, summary)
        if auth0_user_id:
            _invalidate_delegated_tokens(auth0_user_id, summary)
        _audit_cleanup(summary)
        emit_done(task_id, summary)
        return summary
    except Exception as exc:  # pragma: no cover
        emit_error(task_id, str(exc))
        logger.exception("session-revocation cleanup failed")
        summary["errors"].append(str(exc))
        return summary


# ---------------------------------------------------------------------------
# Per-runtime halt helpers
# ---------------------------------------------------------------------------


def _halt_agent_runs(user_id: str, reason: str, summary: dict[str, Any]) -> None:
    """Halt every running / pending AgentRunV2 owned by the user."""
    try:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models_agents import AgentRunV2
    except Exception:
        summary["errors"].append("agent_runs_v2 import failed")
        return

    try:
        from aqp.tasks.celery_app import celery_app as _celery
    except Exception:
        _celery = None

    halted = 0
    with get_session() as session:
        rows = (
            session.execute(
                select(AgentRunV2).where(
                    AgentRunV2.status.in_(["running", "pending"]),
                    AgentRunV2.owner_user_id == user_id,
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            tid = (row.task_id or "").strip()
            if tid and _celery is not None:
                try:
                    _celery.control.revoke(tid, terminate=True, signal="SIGTERM")
                except Exception as exc:
                    summary["errors"].append(f"agent revoke {tid}: {exc}")
            row.status = "halted"
            row.error = (row.error or "") + f"\nhalted by session-revocation ({reason})"
            halted += 1
    summary["halted"]["agent_runs_v2"] = halted


def _halt_paper_runs(user_id: str, reason: str, summary: dict[str, Any]) -> None:
    try:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models import PaperTradingRun
        from aqp.tasks.paper_tasks import publish_stop_signal
    except Exception:
        summary["errors"].append("paper_trading_runs import failed")
        return

    halted = 0
    with get_session() as session:
        rows = (
            session.execute(
                select(PaperTradingRun).where(
                    PaperTradingRun.status.in_(["pending", "starting", "running"]),
                    PaperTradingRun.owner_user_id == user_id,
                )
            )
            .scalars()
            .all()
        )
    for row in rows:
        tid = (row.task_id or "").strip()
        if not tid:
            continue
        try:
            publish_stop_signal(tid, reason=f"session-revocation:{reason}")
            halted += 1
        except Exception as exc:
            summary["errors"].append(f"paper stop {tid}: {exc}")
    summary["halted"]["paper_trading_runs"] = halted


def _halt_bot_deployments(user_id: str, reason: str, summary: dict[str, Any]) -> None:
    try:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models_bots import BotDeployment
    except Exception:
        summary["errors"].append("bot_deployments import failed")
        return

    try:
        from aqp.tasks.celery_app import celery_app as _celery
    except Exception:
        _celery = None

    halted = 0
    with get_session() as session:
        rows = (
            session.execute(
                select(BotDeployment).where(
                    BotDeployment.status.in_(["pending", "starting", "running", "active"]),
                    BotDeployment.owner_user_id == user_id,
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            tid = (row.task_id or "").strip()
            if tid and _celery is not None:
                try:
                    _celery.control.revoke(tid, terminate=True, signal="SIGTERM")
                except Exception as exc:
                    summary["errors"].append(f"bot revoke {tid}: {exc}")
            row.status = "halted"
            row.error = (row.error or "") + f"\nhalted by session-revocation ({reason})"
            halted += 1
    summary["halted"]["bot_deployments"] = halted


def _halt_rl_runs(user_id: str, reason: str, summary: dict[str, Any]) -> None:
    try:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models_rl import RLRun
    except Exception:
        summary["errors"].append("rl_runs import failed")
        return

    try:
        from aqp.tasks.celery_app import celery_app as _celery
    except Exception:
        _celery = None

    halted = 0
    with get_session() as session:
        rows = (
            session.execute(
                select(RLRun).where(
                    RLRun.status.in_(["pending", "running"]),
                    RLRun.owner_user_id == user_id,
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            tid = (row.task_id or "").strip()
            if tid and _celery is not None:
                try:
                    _celery.control.revoke(tid, terminate=True, signal="SIGTERM")
                except Exception as exc:
                    summary["errors"].append(f"rl revoke {tid}: {exc}")
            row.status = "halted"
            row.error = (row.error or "") + f"\nhalted by session-revocation ({reason})"
            halted += 1
    summary["halted"]["rl_runs"] = halted


def _halt_workflow_runs(user_id: str, reason: str, summary: dict[str, Any]) -> None:
    try:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models_workflows import WorkflowRun
    except Exception:
        summary["errors"].append("workflow_runs import failed")
        return

    try:
        from aqp.tasks.celery_app import celery_app as _celery
    except Exception:
        _celery = None

    halted = 0
    with get_session() as session:
        rows = (
            session.execute(
                select(WorkflowRun).where(
                    WorkflowRun.status.in_(["pending", "running"]),
                    WorkflowRun.owner_user_id == user_id,
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            tid = (row.task_id or "").strip()
            if tid and _celery is not None:
                try:
                    _celery.control.revoke(tid, terminate=True, signal="SIGTERM")
                except Exception as exc:
                    summary["errors"].append(f"workflow revoke {tid}: {exc}")
            row.status = "halted"
            row.error = (row.error or "") + f"\nhalted by session-revocation ({reason})"
            halted += 1
    summary["halted"]["workflow_runs"] = halted


def _halt_terraform_runs(user_id: str, reason: str, summary: dict[str, Any]) -> None:
    """Halt non-destructive Terraform runs; LEAVE in-flight apply/destroy.

    Mid-apply halts leave Terraform state in an inconsistent place
    (resources created but not in state, or vice versa). The runbook
    is: let the in-flight apply / destroy finish, then the operator
    rolls forward / back manually. We audit the skip as a warning so
    the on-call surface notices the impacted runs.
    """
    try:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models_terraform import TerraformRun
    except Exception:
        summary["errors"].append("terraform_runs import failed")
        return

    try:
        from aqp.tasks.celery_app import celery_app as _celery
    except Exception:
        _celery = None

    halted = 0
    skipped = 0
    with get_session() as session:
        rows = (
            session.execute(
                select(TerraformRun).where(
                    TerraformRun.status.in_(["pending", "running"]),
                    TerraformRun.owner_user_id == user_id,
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            action = str(getattr(row, "action", "") or "").lower()
            if action in {"apply", "destroy"}:
                # Don't halt destructive runs; the state corruption risk
                # outweighs the session-revocation benefit. Audit so the
                # on-call surface sees the impact.
                skipped += 1
                continue
            tid = (row.task_id or "").strip()
            if tid and _celery is not None:
                try:
                    _celery.control.revoke(tid, terminate=True, signal="SIGTERM")
                except Exception as exc:
                    summary["errors"].append(f"terraform revoke {tid}: {exc}")
            row.status = "halted"
            row.error = (row.error or "") + f"\nhalted by session-revocation ({reason})"
            halted += 1
    summary["halted"]["terraform_runs"] = halted
    summary["halted"]["terraform_runs_skipped_destructive"] = skipped


def _revoke_oauth_tokens(user_id: str, reason: str, summary: dict[str, Any]) -> None:
    """Revoke per-user external OAuth tokens (Bloomberg / GitHub / FRED / ...).

    Per AGENTS hard rule 50, :class:`UserOAuthTokenStore` returns
    ``None`` for revoked rows so any subsequent agent call falls
    through to the next resolver tier (or fails closed). This makes
    sure a compromised session can't keep using the user's
    third-party API keys after the human revoked.
    """
    from datetime import datetime

    try:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models_oauth_tokens import UserOAuthToken
    except Exception:
        summary["errors"].append("user_oauth_tokens import failed")
        return

    revoked = 0
    with get_session() as session:
        rows = (
            session.execute(
                select(UserOAuthToken).where(
                    UserOAuthToken.user_id == user_id,
                    UserOAuthToken.revoked_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.revoked_at = datetime.utcnow()
            row.revoked_by_user_id = user_id
            revoked += 1
    summary["oauth_tokens_revoked"] = revoked


def _invalidate_delegated_tokens(auth0_user_id: str, summary: dict[str, Any]) -> None:
    """Drop cached RFC 8693 delegated agent tokens for this user."""
    try:
        from aqp.auth.token_exchange import get_token_exchange_broker
    except Exception:
        return
    try:
        dropped = get_token_exchange_broker().invalidate(user_subject=auth0_user_id)
    except Exception as exc:
        summary["errors"].append(f"delegated invalidation: {exc}")
        return
    summary["delegated_tokens_invalidated"] = int(dropped or 0)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def _audit_cleanup(summary: dict[str, Any]) -> None:
    """Emit a single SecurityAuditEvent summarising what got halted."""
    try:
        from aqp.auth.audit import emit_audit_event

        emit_audit_event(
            "session_revocation_cleanup",
            user_id=summary.get("internal_user_id"),
            event_category="safety",
            severity="critical",
            source="celery",
            details={
                "reason": summary.get("reason"),
                "auth0_user_id": summary.get("auth0_user_id"),
                "halted": summary.get("halted"),
                "oauth_tokens_revoked": summary.get("oauth_tokens_revoked"),
                "delegated_tokens_invalidated": summary.get("delegated_tokens_invalidated"),
                "error_count": len(summary.get("errors") or []),
            },
        )
    except Exception:
        logger.debug("session-revocation audit emit failed", exc_info=True)


__all__ = ["cleanup_for_user"]
