"""Dagster proxy route tests."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from aqp.api.routes import dagster


def test_list_schedules_uses_discovered_repository_selector(monkeypatch):
    calls: list[tuple[str, dict[str, Any] | None]] = []

    def fake_post(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        calls.append((query, variables))
        if "workspaceOrError" in query:
            return {
                "data": {
                    "workspaceOrError": {
                        "locationEntries": [
                            {
                                "name": "aqp.dagster.definitions",
                                "locationOrLoadError": {
                                    "repositories": [{"name": "__repository__"}]
                                },
                            }
                        ]
                    }
                }
            }
        return {
            "data": {
                "schedulesOrError": {
                    "results": [
                        {
                            "name": "daily_full_refresh",
                            "scheduleState": {"status": "STOPPED"},
                        }
                    ]
                }
            }
        }

    monkeypatch.setattr(dagster, "_post_graphql", fake_post)
    dagster._repository_selector.cache_clear()

    result = dagster.list_schedules()

    assert result["schedules"][0]["name"] == "daily_full_refresh"
    assert calls[-1][1] == {
        "selector": {
            "repositoryLocationName": "aqp.dagster.definitions",
            "repositoryName": "__repository__",
        }
    }


def test_start_sensor_uses_real_selector(monkeypatch):
    calls: list[tuple[str, dict[str, Any] | None]] = []

    def fake_post(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        calls.append((query, variables))
        if "workspaceOrError" in query:
            return {
                "data": {
                    "workspaceOrError": {
                        "locationEntries": [
                            {
                                "name": "aqp.dagster.definitions",
                                "locationOrLoadError": {
                                    "repositories": [{"name": "__repository__"}]
                                },
                            }
                        ]
                    }
                }
            }
        return {"data": {"startSensor": {"__typename": "SensorStateResult"}}}

    monkeypatch.setattr(dagster, "_post_graphql", fake_post)
    dagster._repository_selector.cache_clear()

    dagster.start_sensor("pipeline_manifests_changed")

    assert calls[-1][1] == {
        "selector": {
            "repositoryLocationName": "aqp.dagster.definitions",
            "repositoryName": "__repository__",
            "sensorName": "pipeline_manifests_changed",
        }
    }


def test_trigger_assets_uses_asset_job_selector(monkeypatch):
    calls: list[tuple[str, dict[str, Any] | None]] = []

    def fake_post(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        calls.append((query, variables))
        if "workspaceOrError" in query:
            return {
                "data": {
                    "workspaceOrError": {
                        "locationEntries": [
                            {
                                "name": "aqp.dagster.definitions",
                                "locationOrLoadError": {
                                    "repositories": [{"name": "__repository__"}]
                                },
                            }
                        ]
                    }
                }
            }
        return {"data": {"launchPipelineExecution": {"__typename": "LaunchRunSuccess"}}}

    monkeypatch.setattr(dagster, "_post_graphql", fake_post)
    dagster._repository_selector.cache_clear()

    dagster.trigger_assets(dagster.TriggerRequest(asset_keys=[["airbyte_health"]]))

    assert "JobOrPipelineSelector" in calls[-1][0]
    assert calls[-1][1] == {
        "selector": {
            "repositoryLocationName": "aqp.dagster.definitions",
            "repositoryName": "__repository__",
            "jobName": "__ASSET_JOB",
            "assetSelection": [{"path": ["airbyte_health"]}],
        },
        "runConfig": {},
    }


def test_trigger_assets_refreshes_selector_when_stale(monkeypatch):
    calls: list[tuple[str, dict[str, Any] | None]] = []
    workspace_queries = 0
    launch_attempts = 0

    def fake_post(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        nonlocal workspace_queries, launch_attempts
        calls.append((query, variables))
        if "workspaceOrError" in query:
            workspace_queries += 1
            location_name = "stale.location" if workspace_queries == 1 else "fresh.location"
            return {
                "data": {
                    "workspaceOrError": {
                        "locationEntries": [
                            {
                                "name": location_name,
                                "locationOrLoadError": {
                                    "repositories": [{"name": "__repository__"}]
                                },
                            }
                        ]
                    }
                }
            }
        if "launchPipelineExecution" in query:
            launch_attempts += 1
            if launch_attempts == 1:
                raise HTTPException(
                    status_code=502,
                    detail="Dagster repository selector not found",
                )
            return {"data": {"launchPipelineExecution": {"__typename": "LaunchRunSuccess"}}}
        return {"data": {}}

    monkeypatch.setattr(dagster, "_post_graphql", fake_post)
    dagster._repository_selector.cache_clear()

    dagster.trigger_assets(dagster.TriggerRequest(asset_keys=[["airbyte_health"]]))

    assert workspace_queries == 2
    assert launch_attempts == 2
    assert calls[-1][1] == {
        "selector": {
            "repositoryLocationName": "fresh.location",
            "repositoryName": "__repository__",
            "jobName": "__ASSET_JOB",
            "assetSelection": [{"path": ["airbyte_health"]}],
        },
        "runConfig": {},
    }


def test_list_assets_raises_without_graphql_fallback(monkeypatch):
    def fake_post(_query: str, _variables: dict[str, Any] | None = None) -> dict[str, Any]:
        raise HTTPException(status_code=503, detail="Dagster GraphQL endpoint not configured.")

    monkeypatch.setattr(dagster, "_post_graphql", fake_post)
    dagster._repository_selector.cache_clear()

    with pytest.raises(HTTPException):
        dagster.list_assets()


def test_trigger_assets_validates_asset_key_segments():
    with pytest.raises(HTTPException):
        dagster.trigger_assets(dagster.TriggerRequest(asset_keys=[[""]]))
