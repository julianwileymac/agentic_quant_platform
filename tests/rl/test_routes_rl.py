"""API route smoke tests for the new RL surface."""
from __future__ import annotations

import pytest


def test_components_endpoint_returns_kinds(monkeypatch):
    pytest.importorskip("fastapi.testclient")
    from fastapi.testclient import TestClient

    from aqp.api.main import app

    with TestClient(app) as client:
        resp = client.get("/rl/components")
        assert resp.status_code == 200
        data = resp.json()
        assert "kinds" in data
        # Every canonical RL kind is present (counts may be zero in test env).
        assert "rl_env" in data["kinds"]
        assert "rl_reward" in data["kinds"]


def test_lab_preview_reward_default_response():
    pytest.importorskip("fastapi.testclient")
    from fastapi.testclient import TestClient

    from aqp.api.main import app

    payload = {
        "reward": {
            "class": "CompositeReward",
            "module_path": "aqp.rl.core.reward",
            "kwargs": {
                "terms": [
                    {
                        "class": "PnLTerm",
                        "module_path": "aqp.rl.rewards.pnl",
                        "kwargs": {"weight": 1.0, "scale": 1.0},
                    }
                ]
            },
        },
        "trajectory": [
            {"step": 0, "state": {"portfolio_value": 100}, "next_state": {"portfolio_value": 110}, "info": {}},
        ],
    }
    with TestClient(app) as client:
        resp = client.post("/rl/lab/preview-reward", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["steps"]
        assert body["steps"][0]["reward"] == pytest.approx(10.0)
