"""Pydantic v2 models for AQP deployment topology.

These models live here so both ``aqp/`` and ``aqp_control_plane/``
agree on the wire format of ``aqp_platform/configs/deployment/topology.yaml``.
The YAML loader (:func:`get_deployment_topology`) stays in
``aqp/deployment/topology.py`` because it depends on
``aqp.config.settings`` for the path lookup.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Base for every topology model — forbid unknown fields."""

    model_config = ConfigDict(extra="forbid")


class TopologyDefaults(StrictModel):
    organization_slug: str = "wiley-tech"
    workspace_slug: str = "main"
    app_version: str = "latest"
    labels: dict[str, str] = Field(default_factory=dict)


class TerraformTooling(StrictModel):
    binary_setting: str = "AQP_TERRAFORM_BINARY"
    min_version: str = "1.10"
    provider_mirror_path: str = "data/terraform/plugin-cache"
    plugin_cache_path: str = "data/terraform/plugin-cache-runtime"
    cli_config_file: str = "data/terraform/terraform.tfrc"


class LocalShellTooling(StrictModel):
    command: str = "bash"
    windows_path_prepend: list[str] = Field(default_factory=list)


class Tooling(StrictModel):
    terraform: TerraformTooling = Field(default_factory=TerraformTooling)
    local_shell: LocalShellTooling = Field(default_factory=LocalShellTooling)


class ServiceDefinition(StrictModel):
    id: str
    aliases: list[str] = Field(default_factory=list)
    label: str
    role: str
    workload: Literal["deployment", "statefulset", "daemonset", "job", "external"]
    # ``app_label`` selects the Kubernetes pods backing this service via
    # ``f"app={app_label}"``. Required for in-cluster workloads; defaults
    # to empty for ``workload: external`` services (Cloudflare-hosted
    # docs / status pages have no pod selector). The model validator
    # below enforces the in-cluster requirement.
    app_label: str = ""
    container: str = ""
    image_key: str = ""
    port: int | None = None
    health_path: str = ""
    storage: str = ""
    restartable: bool = False
    logs_enabled: bool = True
    cluster: str = Field(
        default="",
        description=(
            "Optional logical cluster grouping. Used by the side-by-side "
            "Strimzi/Redpanda streaming topology and the additive "
            "Iceberg/Hudi lakehouse topology. Examples: ``streaming.strimzi``, "
            "``streaming.redpanda``, ``lakehouse.iceberg``, ``lakehouse.hudi``."
        ),
    )
    namespace: str = Field(
        default="",
        description=(
            "Kubernetes namespace this service runs in. Empty falls back to "
            "the active DeploymentTarget's namespace. Allows AQP-owned shared "
            "infrastructure to live in dedicated namespaces (e.g., "
            "``aqp-streaming``, ``aqp-observability``, ``aqp-lakehouse``)."
        ),
    )
    protocols: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Map of protocol name to port. Use when a service exposes more "
            "than one port (e.g., QuestDB ``http: 9000, ilp_tcp: 9009, "
            "pgwire: 8812``; Phoenix ``ui_http: 6006, otlp_grpc: 4317``)."
        ),
    )
    endpoints: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Map of endpoint name to canonical URL. The single source of "
            "truth for service-to-service URLs once topology fallback is "
            "wired into ``aqp.config.settings``. Examples: ``bootstrap``, "
            "``admin``, ``ui``, ``otlp``, ``metrics``, ``ilp``, ``pgwire``."
        ),
    )

    @model_validator(mode="after")
    def _validate_app_label(self) -> ServiceDefinition:
        # External services (Cloudflare-hosted edge properties) don't
        # have pods, so ``app_label`` is optional for them. Every
        # other workload kind MUST carry a selector.
        if self.workload != "external" and not self.app_label:
            raise ValueError(
                f"service {self.id!r}: workload={self.workload!r} requires "
                f"a non-empty app_label (only ``workload: external`` may omit it)"
            )
        return self

    def selector(self) -> str:
        return f"app={self.app_label}"

    def endpoint(self, name: str) -> str | None:
        """Return a named endpoint URL or ``None`` if unset."""
        return self.endpoints.get(name)

    def primary_url(self) -> str | None:
        """Return the canonical URL for this service.

        Resolution order: explicit ``endpoints['bootstrap']`` -> ``ui`` ->
        ``http`` -> first endpoint declared. Used by the
        ``aqp.config.topology_fallback`` resolver to back-fill URL-typed
        ``Settings`` fields without changing their hardcoded defaults.
        """
        if not self.endpoints:
            return None
        for preferred in ("bootstrap", "ui", "http", "api", "admin"):
            value = self.endpoints.get(preferred)
            if value:
                return value
        return next(iter(self.endpoints.values()), None)

    def frontend_dict(self) -> dict[str, Any]:
        data = self.model_dump()
        data["selector"] = self.selector()
        return data


class TerraformTarget(StrictModel):
    stack_slug: str
    spec_path: str
    environment_dir: str
    tfvars_path: str = ""
    backend_state_path: str = ""


class ClusterDefinition(StrictModel):
    name: str
    kubeconfig_path: str = ""
    kube_context: str = ""
    k3d_image: str = ""
    registry_name: str = ""
    registry_port: int | None = None
    registry_host: str = ""
    registry_localhost: str = ""
    lb_http_port: int | None = None
    lb_https_port: int | None = None
    ingress_class: str = ""
    ingress_host: str = ""


class ImageDefinition(StrictModel):
    registry: str = ""
    app_version: str = "latest"
    build_locally: bool = False
    services: dict[str, str] = Field(default_factory=dict)


class AuthDefinition(StrictModel):
    provider: str = "local"
    required: bool = False
    oidc_issuer: str = ""
    audience: str = ""
    client_id: str = ""
    scim_enabled: bool = False
    secret_refs: dict[str, str] = Field(default_factory=dict)


class DeploymentTarget(StrictModel):
    id: str
    label: str
    kind: str
    environment: str
    cloud_provider: str
    namespace: str
    adapter_preference: list[str] = Field(default_factory=list)
    terraform: TerraformTarget
    cluster: ClusterDefinition
    endpoints: dict[str, str] = Field(default_factory=dict)
    images: ImageDefinition = Field(default_factory=ImageDefinition)
    auth: AuthDefinition = Field(default_factory=AuthDefinition)
    services: list[str] = Field(default_factory=list)

    def summary_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "namespace": self.namespace,
        }


# =============================================================================
# Phase 3 §6.2 (RESTRUCTURING_PLAN.md) — Cell registry primitives.
#
# A "cell" is the deployment-layer unit that composes with the
# application-layer ``TenancyStrategy``. The mapping (from §6.1):
#
#   shared-std    -> shared_schema_rls         (one ns, many tenants, RLS)
#   shared-prem   -> schema_per_tenant         (one ns, one schema/tenant)
#   silo-reg      -> database_per_enterprise   (one ns, one tenant, own DB)
#   silo-custom   -> hybrid                    (per-contract)
#
# A cell is uniquely identified by (tier, region, az, k8s_namespace).
# The list of cells in ``DeploymentTopology.cells`` is the bootstrap
# seed; live updates flow through the control-plane ``/manage/cells/*``
# routes which mirror to the ``cells`` ORM table (Alembic 0082).
# =============================================================================


_VALID_TIER_TO_STRATEGY: dict[str, str] = {
    "shared-std": "shared_schema_rls",
    "shared-prem": "schema_per_tenant",
    "silo-reg": "database_per_enterprise",
    "silo-custom": "hybrid",
}


CellTier = Literal["shared-std", "shared-prem", "silo-reg", "silo-custom"]
CellTenancyStrategy = Literal[
    "shared_schema_rls",
    "schema_per_tenant",
    "database_per_enterprise",
    "hybrid",
]
CellState = Literal[
    "provisioning",
    "active",
    "draining",
    "suspended",
    "maintenance",
    "decommissioning",
    "archived",
]


class CellRoutes(StrictModel):
    """Canonical inbound URLs the cell-router uses for next-hop routing.

    Both fields are optional so a cell can be declared (e.g. while still
    in ``provisioning``) before its DNS / TLS surfaces exist. Once the
    cell is ``active`` the router rejects routing decisions that
    target a cell with missing routes.
    """

    api: str = ""
    ws: str = ""


class CellDataPlane(StrictModel):
    """Phase 6 §9 — per-cell data plane endpoints.

    A cell's data plane composes Postgres + Redis + MinIO + MLflow +
    Iceberg REST. Each cell publishes the in-cluster service URLs and
    bucket prefixes it owns; the application reads them via
    :class:`aqp.tenancy.runtime_context` (Phase 3 §6.3) keyed by
    ``cell_id``. All fields are optional so existing pre-Phase-6 cells
    continue to validate; ``shared-std-local`` keeps using the shared
    legacy data plane until the operator stamps in a per-cell block.
    """

    postgres_dsn_secret: str = Field(
        default="",
        description=(
            "Vault secret path that materialises the per-cell Postgres "
            "DSN (e.g. ``secret/aqp/cells/<id>/postgres``). Resolution "
            "goes through :class:`CredentialResolver` — never the raw "
            "DSN. Empty falls back to the legacy shared Postgres."
        ),
    )
    redis_url: str = Field(
        default="",
        description=(
            "Per-cell Redis URL, e.g. "
            "``redis://aqp-cell-redis.cell-shared-std-us-east-1a:6379/0``. "
            "Empty falls back to ``settings.redis_url``."
        ),
    )
    minio_endpoint: str = Field(
        default="",
        description=(
            "Per-cell MinIO/S3 endpoint URL. Empty falls back to "
            "``settings.s3_endpoint_url``."
        ),
    )
    minio_bucket_prefix: str = Field(
        default="",
        description=(
            "Per-cell bucket-name prefix, e.g. ``aqp-cell-shared-std-us-east-1a``. "
            "The cell-data-plane Helm chart bootstraps buckets named "
            "``<prefix>-warehouse``, ``<prefix>-mlflow``, ``<prefix>-backups``, "
            "``<prefix>-audit``. Empty falls back to ``aqp-<cell.id>``."
        ),
    )
    mlflow_tracking_uri: str = Field(
        default="",
        description=(
            "Per-cell MLflow tracking server URI, e.g. "
            "``http://aqp-cell-mlflow.cell-shared-std-us-east-1a:5000``. "
            "Empty falls back to ``settings.mlflow_tracking_uri``."
        ),
    )
    iceberg_rest_uri: str = Field(
        default="",
        description=(
            "Per-cell Iceberg REST catalog URI, e.g. "
            "``http://aqp-cell-iceberg-rest.cell-shared-std-us-east-1a:8181``. "
            "Empty falls back to ``settings.iceberg_rest_uri``."
        ),
    )
    iceberg_warehouse_uri: str = Field(
        default="",
        description=(
            "Per-cell Iceberg warehouse URI, e.g. "
            "``s3://aqp-cell-shared-std-us-east-1a-warehouse/``. "
            "Empty falls back to ``settings.iceberg_s3_warehouse``."
        ),
    )
    vault_transit_key: str = Field(
        default="",
        description=(
            "Per-cell Vault Transit key id (Phase 6 §9.7). Empty falls "
            "back to the shared cluster transit key. ``silo-reg`` cells "
            "MUST set this to enforce cryptographic data-plane separation."
        ),
    )


class Cell(StrictModel):
    """One deployment cell — application-layer + data-layer + K8s ns.

    Carries enough metadata for ``aqp-tenant-router`` to resolve a
    JWT ``(sub, workspace_id)`` to ``(cell_id, k8s_namespace, routes)``
    in a single sub-millisecond cache lookup. The fields mirror the
    ``cells`` ORM table 1:1 (RESTRUCTURING_PLAN.md §6.2 + Alembic
    0082) so the YAML seed and the live registry stay in lockstep.
    """

    id: str = Field(
        ...,
        min_length=1,
        max_length=120,
        pattern=r"^cell-[a-z0-9-]+$",
        description=(
            "Globally unique cell id. Convention: "
            "``cell-<tier>-<region>-<az_suffix>[-<tenant_slug>]``."
        ),
    )
    tier: CellTier
    tenancy_strategy: CellTenancyStrategy = Field(
        ...,
        description=(
            "Application-layer ``TenancyStrategy.strategy_kind``. MUST be "
            "consistent with the tier per the §6.1 mapping; the post-init "
            "validator enforces this."
        ),
    )
    region: str = Field(..., min_length=1)
    availability_zone: str = Field(..., min_length=1)
    k8s_namespace: str = Field(
        ...,
        min_length=1,
        max_length=63,
        pattern=r"^[a-z0-9-]+$",
        description="Kubernetes namespace hosting this cell's workloads.",
    )
    capacity_max_tenants: int = Field(
        default=1,
        ge=1,
        description=(
            "Soft cap on tenants that share this cell. silo-reg / "
            "silo-custom cells should be 1; shared cells are typically "
            "1_000 - 5_000."
        ),
    )
    state: CellState = "provisioning"
    pinned_tenants: list[str] = Field(
        default_factory=list,
        description=(
            "When non-empty, only the listed tenant ids may route to this "
            "cell. Used for silo-reg cells (one tenant pinned) and for "
            "controlled migrations in shared cells."
        ),
    )
    routes: CellRoutes = Field(default_factory=CellRoutes)
    data_plane: CellDataPlane = Field(
        default_factory=CellDataPlane,
        description=(
            "Phase 6 §9 — per-cell data plane endpoints. Optional; "
            "cells without a ``data_plane`` block fall back to the "
            "shared cluster-wide Postgres/Redis/MinIO/MLflow/Iceberg."
        ),
    )
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_tier_strategy(self) -> Cell:
        expected = _VALID_TIER_TO_STRATEGY[self.tier]
        if self.tenancy_strategy != expected:
            # silo-custom + hybrid is the documented exception path; allow
            # any non-hybrid strategy under silo-custom for advanced
            # one-off contracts but warn that hybrid is the canonical pick.
            if self.tier == "silo-custom":
                return self
            raise ValueError(
                f"cell {self.id!r}: tier {self.tier!r} requires "
                f"tenancy_strategy={expected!r} (got {self.tenancy_strategy!r}); "
                f"see RESTRUCTURING_PLAN.md §6.1"
            )
        # silo-reg cells MUST have capacity_max_tenants == 1.
        if self.tier == "silo-reg" and self.capacity_max_tenants != 1:
            raise ValueError(
                f"cell {self.id!r}: silo-reg cells must have "
                f"capacity_max_tenants=1 (got {self.capacity_max_tenants})"
            )
        return self

    def is_active(self) -> bool:
        return self.state == "active"

    def can_accept_new_tenant(self) -> bool:
        """True iff state=active AND not at capacity AND tenant not pinned-out."""
        if self.state != "active":
            return False
        # capacity check is a *soft* cap; the real check happens at
        # placement time against the live tenant count from the
        # ``cells`` ORM row. The YAML capacity is the upper bound.
        return True


class DeploymentTopology(StrictModel):
    version: int
    defaults: TopologyDefaults = Field(default_factory=TopologyDefaults)
    tooling: Tooling = Field(default_factory=Tooling)
    services: list[ServiceDefinition]
    targets: dict[str, DeploymentTarget]
    cells: list[Cell] = Field(
        default_factory=list,
        description=(
            "Phase 3 §6.2 — bootstrap seed for the cell registry. Live "
            "updates flow through the control-plane ``/manage/cells/*`` "
            "routes which mirror to the ``cells`` ORM table (Alembic 0082)."
        ),
    )

    @model_validator(mode="after")
    def _validate_references(self) -> DeploymentTopology:
        service_ids = {service.id for service in self.services}
        for target_id, target in self.targets.items():
            if target.id != target_id:
                raise ValueError(
                    f"target key {target_id!r} does not match target id {target.id!r}"
                )
            missing = sorted(set(target.services) - service_ids)
            if missing:
                raise ValueError(
                    f"target {target_id!r} references unknown services: {missing}"
                )
        terraform = self.tooling.terraform
        if terraform.provider_mirror_path == terraform.plugin_cache_path:
            raise ValueError(
                "terraform provider mirror and plugin cache paths must differ"
            )
        # Phase 3 §6.2 — every cell id must be globally unique; every
        # k8s_namespace must be unique across cells (one cell per ns).
        cell_ids: set[str] = set()
        cell_namespaces: set[str] = set()
        for cell in self.cells:
            if cell.id in cell_ids:
                raise ValueError(f"duplicate cell id {cell.id!r}")
            cell_ids.add(cell.id)
            if cell.k8s_namespace in cell_namespaces:
                raise ValueError(
                    f"cell {cell.id!r}: k8s_namespace {cell.k8s_namespace!r} "
                    f"already used by another cell"
                )
            cell_namespaces.add(cell.k8s_namespace)
        return self

    @property
    def service_map(self) -> dict[str, ServiceDefinition]:
        return {service.id: service for service in self.services}

    @property
    def cell_map(self) -> dict[str, Cell]:
        """Cell-id keyed view of the cell registry (Phase 3 §6.2)."""
        return {cell.id: cell for cell in self.cells}

    def target(self, target_id: str) -> DeploymentTarget:
        try:
            return self.targets[target_id]
        except KeyError as exc:
            raise KeyError(f"unknown deployment target {target_id!r}") from exc

    def target_by_stack_slug(self, stack_slug: str) -> DeploymentTarget | None:
        for target in self.targets.values():
            if target.terraform.stack_slug == stack_slug:
                return target
        return None

    def services_for_target(self, target_id: str) -> list[ServiceDefinition]:
        target = self.target(target_id)
        services = self.service_map
        return [services[service_id] for service_id in target.services]

    def cells_for_tier(self, tier: CellTier) -> list[Cell]:
        """Return every cell on the given tier (Phase 3 §6.2)."""
        return [cell for cell in self.cells if cell.tier == tier]

    def active_cells(self) -> list[Cell]:
        """Return every cell with ``state == 'active'``."""
        return [cell for cell in self.cells if cell.is_active()]


__all__ = [
    "AuthDefinition",
    "Cell",
    "CellDataPlane",
    "CellRoutes",
    "CellState",
    "CellTenancyStrategy",
    "CellTier",
    "ClusterDefinition",
    "DeploymentTarget",
    "DeploymentTopology",
    "ImageDefinition",
    "LocalShellTooling",
    "ServiceDefinition",
    "StrictModel",
    "TerraformTarget",
    "TerraformTooling",
    "Tooling",
    "TopologyDefaults",
]
