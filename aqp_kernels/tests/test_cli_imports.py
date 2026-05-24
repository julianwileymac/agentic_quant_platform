"""Smoke tests: the CLI module imports + exposes the expected verbs."""
from __future__ import annotations


def test_cli_module_imports():
    from aqp_kernels.cli.kernel_cmd import app

    assert app.info.name == "kernel"


def test_pipes_module_imports():
    from aqp_kernels.pipes import cloud_run_with_pipes, local_pipes_context

    assert callable(cloud_run_with_pipes)
    assert callable(local_pipes_context)


def test_secret_broker_module_imports():
    from aqp_kernels.secret_broker import SecretBrokerClient, SecretBrokerServer

    assert SecretBrokerClient is not None
    assert SecretBrokerServer is not None
