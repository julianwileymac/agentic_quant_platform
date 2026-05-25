"""Tenant namespace manifest renderer.

Renders :class:`aqp_platform_core.models.tenancy.TenantNamespaceSpec`
into a list of Kubernetes object dicts (Namespace + ResourceQuota +
LimitRange + NetworkPolicy) ready for server-side-apply by the
:class:`aqp_cp.providers.kubernetes.KubernetesProvider`.

Templating uses Jinja2 with ``PackageLoader`` so the templates ship
inside the wheel. The renderer is deliberately pure / synchronous —
the provider drives the async SSA loop.
"""
from __future__ import annotations

from datetime import datetime, timezone
from importlib.resources import files
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined

from aqp_platform_core.models.tenancy import TenantNamespaceSpec

TENANT_NAMESPACE_TEMPLATE_PATH = (
    "aqp_cp.builders.manifests",
    "tenant_namespace.yaml.j2",
)


def _load_template() -> str:
    package, name = TENANT_NAMESPACE_TEMPLATE_PATH
    return files(package).joinpath(name).read_text(encoding="utf-8")


def render_tenant_namespace_objects(
    spec: TenantNamespaceSpec,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Render ``spec`` into the canonical four / five-object bundle.

    Returns a list of dicts ordered for safe apply (Namespace first,
    then quotas / limits, then NetworkPolicy entries).
    """
    template_text = _load_template()
    env = Environment(
        autoescape=False,
        undefined=StrictUndefined,
        trim_blocks=False,
        lstrip_blocks=False,
        keep_trailing_newline=True,
    )
    template = env.from_string(template_text)
    rendered = template.render(
        tenant_id=spec.tenant_id,
        namespace=spec.namespace(),
        plan=spec.plan.value,
        quotas=spec.quotas.model_dump(),
        limit_range=spec.limit_range.model_dump(),
        network_policy_mode=spec.network_policy_mode.value,
        psa_enforce=spec.psa_enforce,
        psa_audit=spec.psa_audit,
        psa_warn=spec.psa_warn,
        labels=dict(spec.labels),
        annotations=dict(spec.annotations),
        applied_at=(now or datetime.now(timezone.utc)).isoformat(),
    )
    documents: list[dict[str, Any]] = []
    for doc in yaml.safe_load_all(rendered):
        if isinstance(doc, dict) and doc:
            documents.append(doc)
    return documents


__all__ = ["render_tenant_namespace_objects"]
