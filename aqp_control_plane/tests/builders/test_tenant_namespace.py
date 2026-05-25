"""Tenant namespace Jinja renderer tests."""
from __future__ import annotations

from aqp_platform_core.models.tenancy import (
    NetworkPolicyMode,
    TenantNamespaceSpec,
    TenantPlan,
    TenantQuotas,
)

from aqp_cp.builders.tenant import render_tenant_namespace_objects


def test_default_render_emits_five_objects() -> None:
    objects = render_tenant_namespace_objects(
        TenantNamespaceSpec(tenant_id="acme", plan=TenantPlan.B2B)
    )
    kinds = [o["kind"] for o in objects]
    names = [o["metadata"]["name"] for o in objects]
    assert kinds == ["Namespace", "ResourceQuota", "LimitRange", "NetworkPolicy", "NetworkPolicy"]
    assert names == [
        "tenant-acme",
        "tenant-quota",
        "tenant-defaults",
        "default-deny",
        "allow-intra-tenant",
    ]


def test_psa_labels_applied_to_namespace() -> None:
    objects = render_tenant_namespace_objects(
        TenantNamespaceSpec(tenant_id="acme", psa_enforce="baseline")
    )
    ns_labels = objects[0]["metadata"]["labels"]
    assert ns_labels["pod-security.kubernetes.io/enforce"] == "baseline"
    assert ns_labels["aqp.io/tenant"] == "acme"
    assert ns_labels["aqp.io/plan"] == "b2b"


def test_quotas_emit_resource_quota_keys() -> None:
    objects = render_tenant_namespace_objects(
        TenantNamespaceSpec(
            tenant_id="acme",
            quotas=TenantQuotas(cpu="16", memory="32Gi", gpus=2, pvcs=12, pods=80),
        )
    )
    quota = objects[1]
    assert quota["spec"]["hard"]["requests.cpu"] == "16"
    assert quota["spec"]["hard"]["requests.memory"] == "32Gi"
    assert quota["spec"]["hard"]["requests.nvidia.com/gpu"] == 2
    assert quota["spec"]["hard"]["count/pods"] == 80


def test_strict_mode_drops_intra_tenant_allow() -> None:
    objects = render_tenant_namespace_objects(
        TenantNamespaceSpec(
            tenant_id="acme", network_policy_mode=NetworkPolicyMode.STRICT
        )
    )
    np_names = [o["metadata"]["name"] for o in objects if o["kind"] == "NetworkPolicy"]
    assert np_names == ["default-deny"]


def test_open_mode_drops_all_network_policies() -> None:
    objects = render_tenant_namespace_objects(
        TenantNamespaceSpec(
            tenant_id="acme", network_policy_mode=NetworkPolicyMode.OPEN
        )
    )
    np_names = [o["metadata"]["name"] for o in objects if o["kind"] == "NetworkPolicy"]
    assert np_names == []


def test_namespace_prefix_honoured() -> None:
    objects = render_tenant_namespace_objects(
        TenantNamespaceSpec(tenant_id="acme", namespace_prefix="org")
    )
    assert objects[0]["metadata"]["name"] == "org-acme"


def test_intra_tenant_allow_has_namespace_selector() -> None:
    objects = render_tenant_namespace_objects(
        TenantNamespaceSpec(tenant_id="acme")
    )
    intra = next(
        o for o in objects if o["metadata"].get("name") == "allow-intra-tenant"
    )
    ingress_from = intra["spec"]["ingress"][0]["from"]
    found_label = False
    for selector in ingress_from:
        if "namespaceSelector" in selector:
            assert selector["namespaceSelector"]["matchLabels"]["aqp.io/tenant"] == "acme"
            found_label = True
    assert found_label
