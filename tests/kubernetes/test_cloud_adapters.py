"""Smoke tests for the AwsEks / GcpGke / AzureAks KubernetesAdapter siblings.

Each adapter degrades to `is_available()=False` when its cloud SDK
isn't installed or the matching cluster-name env var is empty.
"""
from __future__ import annotations

import pytest


def test_aws_eks_adapter_disabled_without_cluster_name(monkeypatch):
    monkeypatch.setenv("AQP_AWS_EKS_CLUSTER_NAME", "")
    from aqp.kubernetes.adapters.aws_eks import AwsEksAdapter

    adapter = AwsEksAdapter()
    # Either disabled (missing env) or disabled (missing boto3) — both ok.
    assert adapter.is_available() is False


def test_gcp_gke_adapter_disabled_without_project(monkeypatch):
    monkeypatch.setenv("AQP_GCP_GKE_CLUSTER_NAME", "")
    monkeypatch.setenv("AQP_GCP_PROJECT_ID", "")
    monkeypatch.setenv("AQP_GCP_REGION", "")
    from aqp.kubernetes.adapters.gcp_gke import GcpGkeAdapter

    adapter = GcpGkeAdapter()
    assert adapter.is_available() is False


def test_azure_aks_adapter_disabled_without_resource_group(monkeypatch):
    monkeypatch.setenv("AQP_AZURE_AKS_CLUSTER_NAME", "")
    monkeypatch.setenv("AQP_AZURE_RESOURCE_GROUP", "")
    monkeypatch.setenv("AQP_AZURE_SUBSCRIPTION_ID", "")
    from aqp.kubernetes.adapters.azure_aks import AzureAksAdapter

    adapter = AzureAksAdapter()
    assert adapter.is_available() is False


def test_aws_eks_metaclass_registration():
    """Setting adapter_kind registers the class without manual @register."""
    from aqp.kubernetes import list_adapter_classes
    from aqp.kubernetes.adapters.aws_eks import AwsEksAdapter  # noqa: F401

    classes = list_adapter_classes()
    assert "AwsEksAdapter" in classes


def test_gcp_gke_metaclass_registration():
    from aqp.kubernetes import list_adapter_classes
    from aqp.kubernetes.adapters.gcp_gke import GcpGkeAdapter  # noqa: F401

    classes = list_adapter_classes()
    assert "GcpGkeAdapter" in classes


def test_azure_aks_metaclass_registration():
    from aqp.kubernetes import list_adapter_classes
    from aqp.kubernetes.adapters.azure_aks import AzureAksAdapter  # noqa: F401

    classes = list_adapter_classes()
    assert "AzureAksAdapter" in classes
