"""Billing / payment / external integrations.

Each provider must respect AQP rule 26: never read secret fields from
``settings.*`` directly. Resolve through the platform-core
``CredentialResolver`` chain.
"""
from __future__ import annotations

__all__: list[str] = []
