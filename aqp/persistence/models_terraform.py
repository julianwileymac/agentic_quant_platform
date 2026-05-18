"""Terraform IaC control plane ORM models + EntraTenantLink.

Seven new tables, all tenant-scoped via :class:`ProjectScopedMixin`:

- :class:`TerraformProvider` — provider connection profile (per cloud
  account / per tenant). One organization can register many providers;
  every :class:`TerraformWorkspace` pins one provider.
- :class:`TerraformStackSpecRow` — logical stack (latest active
  version). ``module_kind`` picks from :data:`TERRAFORM_MODULE_KINDS`.
- :class:`TerraformStackSpecVersion` — immutable, hash-locked
  snapshot of a :class:`aqp.terraform.spec.TerraformStackSpec`
  payload. Re-snapshotting a changed spec creates a NEW row
  (mirrors ``agent_spec_versions`` / ``bot_versions`` / ``workflow_spec_versions``
  — AGENTS rule 43).
- :class:`TerraformWorkspace` — one row per (stack, environment,
  tenant). Carries the canonical workspace dir + state backend.
- :class:`TerraformRun` — ledger row for one plan/apply/destroy/refresh
  invocation. Carries ``experiment_id`` + ``test_id`` FKs (rule 34).
- :class:`TerraformStateVersion` — snapshot of state after every
  successful ``terraform apply``.
- :class:`TerraformPolicyAttachment` — OPA / Sentinel policy gate
  binding to a workspace; ``hard_mandatory`` blocks apply on
  violation.

Plus the multi-tenant Entra ID index:

- :class:`EntraTenantLink` — multi-tenant Entra ID ``tid`` -> AQP
  :class:`Organization` mapping. New ``tid`` claims land in a
  ``pending`` row when ``settings.auth_msal_b2b_enabled`` is True;
  an AQP super-admin promotes via the onboarding wizard.

Schema migrations live at
:mod:`alembic.versions.0050_terraform_iac_plus_entra`.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from aqp.persistence._tenancy_mixins import ProjectScopedMixin, TenantOwnedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# Canonical stack module kinds. Mirrors the 9 native HCL modules under
# ``terraform/modules/``. ``composite`` covers a root composition that
# wires several module kinds together (e.g. ``terraform/environments/wiley-tech``).
TERRAFORM_MODULE_KINDS: tuple[str, ...] = (
    "storage",
    "pipeline",
    "faas",
    "agents",
    "database",
    "kubernetes",
    "registry",
    "networking",
    "secrets",
    "terraform_runner",
    "composite",
)


# Provider kinds the matching ``aqp.terraform.codegen`` emitters know
# how to render HCL for. ``hcp`` here is the HCP remote backend
# (Terraform Cloud) — not a resource provider but a state backend.
TERRAFORM_PROVIDER_KINDS: tuple[str, ...] = (
    "local",
    "docker",
    "baremetal",
    "rpi_cluster",
    "aws",
    "gcp",
    "azure",
    "hcp",
)


TERRAFORM_STATE_BACKENDS: tuple[str, ...] = (
    "local",
    "s3",
    "azurerm",
    "gcs",
    "hcp",
)


TERRAFORM_ENVIRONMENTS: tuple[str, ...] = (
    "local",
    "paper",
    "live",
    "sandbox",
)


TERRAFORM_RUN_KINDS: tuple[str, ...] = (
    "plan",
    "apply",
    "destroy",
    "refresh",
    "import",
    "state_pull",
    "validate",
    "unlock",
)


TERRAFORM_RUN_STATUSES: tuple[str, ...] = (
    "queued",
    "running",
    "errored",
    "completed",
    "cancelled",
    "awaiting_approval",
    "policy_failed",
)


ENTRA_TENANT_STATUSES: tuple[str, ...] = (
    "pending",
    "active",
    "revoked",
    "suspended",
)


# ---------------------------------------------------------------------------
# EntraTenantLink — multi-tenant Entra ID -> Organization index
# ---------------------------------------------------------------------------


class EntraTenantLink(Base):
    """Multi-tenant Entra ID ``tid`` -> AQP :class:`Organization` mapping.

    AGENTS rule 44: organization provisioning from Entra ID claims
    goes through this index. Don't auto-create Organization rows from
    raw ``tid`` claims; the ``link_org_to_entra_tenant`` admin step
    (frontend EntraTenantLinkWizard / data.tenancy.link_org_to_entra_tenant
    MCP tool) is the only sanctioned ingress.

    Lifecycle (status column):

    - ``pending``: first-seen ``tid`` from a B2B login. The matching
      user's :class:`Membership` chain is left empty; the user can
      sign in but lands on a "waiting for org admin" screen until an
      AQP super-admin promotes the link.
    - ``active``: link confirmed; new logins from this tenant auto-
      provision into the linked org.
    - ``revoked`` / ``suspended``: link refused; sign-ins are blocked
      at :func:`aqp.auth.user.provision_user_from_claims`.

    Not tenant-scoped (sits ABOVE the organization tree).
    """

    __tablename__ = "entra_tenant_links"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entra_tenant_id = Column(String(80), nullable=False, unique=True, index=True)
    primary_domain = Column(String(240), nullable=True, index=True)
    display_name = Column(String(240), nullable=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    # CSV of email domains permitted to auto-provision under this org.
    # Empty -> any email from the tenant qualifies (the tid match is
    # already restrictive enough for most deployments).
    allowed_email_domains = Column(Text, nullable=True)
    # Optional app-role mapping override: ``{"aqp.admin": "owner", ...}``
    # When unset the canonical mapping in
    # :func:`aqp.auth.user._apply_custom_claims_memberships` applies.
    role_mapping = Column(JSON, default=dict)
    requested_by_email = Column(String(320), nullable=True)
    approved_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    approved_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Index(
    "ix_entra_tenant_links_org_status",
    EntraTenantLink.organization_id,
    EntraTenantLink.status,
)


# ---------------------------------------------------------------------------
# TerraformProvider — provider connection profile
# ---------------------------------------------------------------------------


class TerraformProvider(Base, TenantOwnedMixin):
    """Tenant-scoped Terraform provider connection profile.

    ``kind`` picks from :data:`TERRAFORM_PROVIDER_KINDS`. ``config_json``
    holds the per-provider attributes the matching codegen emitter
    consumes (region, project_id, subscription_id, etc) — secrets
    never live here; resolve them through
    :class:`aqp.credentials.CredentialResolver` at apply time.
    """

    __tablename__ = "terraform_providers"

    id = Column(String(36), primary_key=True, default=_uuid)
    slug = Column(String(80), nullable=False, index=True)
    name = Column(String(240), nullable=False)
    kind = Column(String(32), nullable=False, index=True)
    default_region = Column(String(64), nullable=True)
    config_json = Column(JSON, default=dict)
    # Slug of the matching ``CredentialKey.service``. The runtime calls
    # :meth:`CredentialResolver.resolve` with ``service=credential_key``
    # at plan/apply time to pull the right kubeconfig / cloud creds.
    credential_key = Column(String(120), nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "slug", name="uq_terraform_providers_workspace_slug"
        ),
    )


Index(
    "ix_terraform_providers_kind_status",
    TerraformProvider.kind,
    TerraformProvider.status,
)


# ---------------------------------------------------------------------------
# Stack spec + version
# ---------------------------------------------------------------------------


class TerraformStackSpecRow(Base, ProjectScopedMixin):
    """Logical stack — the latest active version of a named spec."""

    __tablename__ = "terraform_stack_specs"

    id = Column(String(36), primary_key=True, default=_uuid)
    slug = Column(String(120), nullable=False, index=True)
    name = Column(String(240), nullable=False)
    module_kind = Column(String(32), nullable=False, index=True)
    description = Column(Text, nullable=True)
    current_version = Column(Integer, nullable=False, default=1)
    annotations = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "slug", name="uq_terraform_stack_specs_project_slug"
        ),
    )


class TerraformStackSpecVersion(Base, ProjectScopedMixin):
    """Immutable, hash-locked snapshot of a :class:`TerraformStackSpec`.

    AGENTS rule 43 — re-snapshotting via
    :func:`aqp.terraform.registry.persist_spec` inserts a new version
    row when the SHA-256 hash changes; existing rows are append-only.
    """

    __tablename__ = "terraform_stack_spec_versions"

    id = Column(String(36), primary_key=True, default=_uuid)
    spec_id = Column(
        String(36),
        ForeignKey("terraform_stack_specs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)
    spec_hash = Column(String(64), nullable=False, unique=True, index=True)
    payload_json = Column(JSON, nullable=False)
    # Optional rendered HCL snapshot — populated by the Jinja2 codegen
    # so the UI can diff between versions without re-rendering.
    payload_hcl = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Index(
    "ix_terraform_stack_spec_versions_spec_version",
    TerraformStackSpecVersion.spec_id,
    TerraformStackSpecVersion.version,
)


# ---------------------------------------------------------------------------
# Workspace + run + state version
# ---------------------------------------------------------------------------


class TerraformWorkspace(Base, ProjectScopedMixin):
    """One (stack, environment, tenant) workspace."""

    __tablename__ = "terraform_workspaces"

    id = Column(String(36), primary_key=True, default=_uuid)
    slug = Column(String(120), nullable=False, index=True)
    name = Column(String(240), nullable=False)
    stack_spec_id = Column(
        String(36),
        ForeignKey("terraform_stack_specs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider_id = Column(
        String(36),
        ForeignKey("terraform_providers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    environment = Column(String(32), nullable=False, default="local", index=True)
    state_backend = Column(String(32), nullable=False, default="local")
    # URI of the state file (local path, ``s3://...``, ``gs://...``,
    # ``azurerm://...``, or an HCP workspace path).
    state_uri = Column(String(1024), nullable=True)
    hcp_workspace_id = Column(String(120), nullable=True, index=True)
    # The organization that owns the cloud account this workspace
    # provisions into. Pinned for the lifetime of the workspace so
    # cost-allocation + ownership-graph stay consistent.
    tenant_org_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    experiment_id = Column(
        String(36),
        ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    archived = Column(Boolean, nullable=False, default=False, index=True)
    settings = Column(JSON, default=dict)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "slug", name="uq_terraform_workspaces_project_slug"
        ),
    )


Index(
    "ix_terraform_workspaces_env_archived",
    TerraformWorkspace.environment,
    TerraformWorkspace.archived,
)


class TerraformRun(Base, ProjectScopedMixin):
    """One execution of a :class:`TerraformRuntime` lifecycle method.

    Ledger row written by
    :meth:`aqp.terraform.runtime.TerraformRuntime.plan` / ``.apply`` /
    ``.destroy`` / ``.refresh``. Carries the canonical
    ``experiment_id`` + ``test_id`` FKs (AGENTS rule 34).

    Note: the FK to ``terraform_workspaces.id`` is named
    ``terraform_workspace_id`` (not ``workspace_id``) so it does not
    collide with the tenancy ``workspace_id`` column emitted by
    :class:`ProjectScopedMixin`.
    """

    __tablename__ = "terraform_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    terraform_workspace_id = Column(
        String(36),
        ForeignKey("terraform_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    spec_version_id = Column(
        String(36),
        ForeignKey("terraform_stack_spec_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_kind = Column(String(32), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    started_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    approved_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)
    # Artefact URIs (S3 / MinIO / local). Populated by the runner pod.
    plan_artifact_uri = Column(String(1024), nullable=True)
    plan_summary_json = Column(JSON, default=dict)
    apply_artifact_uri = Column(String(1024), nullable=True)
    stdout_log_uri = Column(String(1024), nullable=True)
    stderr_log_uri = Column(String(1024), nullable=True)
    exit_code = Column(Integer, nullable=True)
    lock_id = Column(String(120), nullable=True)
    parent_run_id = Column(
        String(36),
        ForeignKey("terraform_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    celery_task_id = Column(String(120), nullable=True, index=True)
    policy_check_result = Column(JSON, default=dict)
    halted = Column(Boolean, nullable=False, default=False, index=True)
    error = Column(Text, nullable=True)
    meta = Column(JSON, default=dict)
    # Rule 34 — every new *_runs row gets these.
    experiment_id = Column(
        String(36),
        ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    test_id = Column(
        String(36),
        ForeignKey("aqp_tests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


Index(
    "ix_terraform_runs_status_started",
    TerraformRun.status,
    TerraformRun.started_at,
)
Index(
    "ix_terraform_runs_workspace_kind",
    TerraformRun.terraform_workspace_id,
    TerraformRun.run_kind,
)


class TerraformStateVersion(Base, ProjectScopedMixin):
    """Snapshot of Terraform state after a successful apply.

    One row per successful ``apply`` (and per successful state pull).
    The frontend uses these to render a "state history" view + diff
    consecutive serials. State payloads are not stored inline (can be
    multi-MB); instead a URI to a versioned S3 / MinIO object.

    Note: FK to ``terraform_workspaces`` is named
    ``terraform_workspace_id`` to avoid collision with the tenancy
    ``workspace_id`` column from :class:`ProjectScopedMixin`.
    """

    __tablename__ = "terraform_state_versions"

    id = Column(String(36), primary_key=True, default=_uuid)
    terraform_workspace_id = Column(
        String(36),
        ForeignKey("terraform_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    serial = Column(Integer, nullable=False)
    lineage = Column(String(64), nullable=True)
    state_json_uri = Column(String(1024), nullable=False)
    state_size_bytes = Column(Integer, nullable=True)
    # Filtered, sensitive-redacted outputs map for the UI.
    outputs_redacted = Column(JSON, default=dict)
    resource_count = Column(Integer, nullable=True)
    created_by_run_id = Column(
        String(36),
        ForeignKey("terraform_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "terraform_workspace_id",
            "serial",
            name="uq_terraform_state_workspace_serial",
        ),
    )


class TerraformPolicyAttachment(Base, ProjectScopedMixin):
    """OPA / Sentinel policy attachment for a workspace.

    When ``hard_mandatory`` is True a failed policy check blocks
    ``apply``. Soft attachments emit a warning but allow the apply to
    proceed.

    Note: FK to ``terraform_workspaces`` is named
    ``terraform_workspace_id`` to avoid collision with the tenancy
    ``workspace_id`` column from :class:`ProjectScopedMixin`.
    """

    __tablename__ = "terraform_policy_attachments"

    id = Column(String(36), primary_key=True, default=_uuid)
    terraform_workspace_id = Column(
        String(36),
        ForeignKey("terraform_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_set_uri = Column(String(1024), nullable=False)
    policy_engine = Column(String(32), nullable=False, default="opa", index=True)
    hard_mandatory = Column(Boolean, nullable=False, default=True)
    last_check_run_id = Column(
        String(36),
        ForeignKey("terraform_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    last_check_passed = Column(Boolean, nullable=True)
    last_check_at = Column(DateTime, nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


__all__ = [
    "ENTRA_TENANT_STATUSES",
    "EntraTenantLink",
    "TERRAFORM_ENVIRONMENTS",
    "TERRAFORM_MODULE_KINDS",
    "TERRAFORM_PROVIDER_KINDS",
    "TERRAFORM_RUN_KINDS",
    "TERRAFORM_RUN_STATUSES",
    "TERRAFORM_STATE_BACKENDS",
    "TerraformPolicyAttachment",
    "TerraformProvider",
    "TerraformRun",
    "TerraformStackSpecRow",
    "TerraformStackSpecVersion",
    "TerraformStateVersion",
    "TerraformWorkspace",
]
