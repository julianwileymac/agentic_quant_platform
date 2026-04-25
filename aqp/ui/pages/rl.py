"""RL Dashboard — kick off training runs and read MLflow."""
from __future__ import annotations

from pathlib import Path

import solara
import yaml

from aqp.ui.api_client import post

_RL_DIR = Path("configs/rl")


@solara.component
def Page() -> None:
    available = solara.use_reactive(_list_configs())
    selected = solara.use_reactive(available.value[0] if available.value else "")
    editor = solara.use_reactive(_load(selected.value))
    run_name = solara.use_reactive("")

    def reload() -> None:
        available.set(_list_configs())

    def change(name: str) -> None:
        selected.set(name)
        editor.set(_load(name))

    def train() -> None:
        try:
            cfg = yaml.safe_load(editor.value)
            r = post("/rl/train", json={"config": cfg, "run_name": run_name.value or None})
            solara.Info(f"Training kicked off: {r.get('task_id')}")
        except Exception as e:
            solara.Error(str(e))

    with solara.Column(gap="16px", style={"padding": "16px"}):
        solara.Markdown("# Reinforcement Learning Dashboard")
        solara.Markdown(
            "Train a DRL policy on a FinRL-style gym env. All runs are autologged to MLflow at "
            "[http://localhost:5000](http://localhost:5000)."
        )
        with solara.Row():
            solara.Select(label="RL recipe", value=selected, values=available.value, on_value=change)
            solara.Button("Reload", on_click=reload)
            solara.InputText("run_name (optional)", value=run_name)
        solara.InputTextArea("Config", value=editor, rows=22)
        solara.Button("Train", on_click=train, color="primary")


def _list_configs() -> list[str]:
    if not _RL_DIR.exists():
        return []
    return sorted(p.name for p in _RL_DIR.glob("*.yaml"))


def _load(name: str) -> str:
    if not name:
        return ""
    p = _RL_DIR / name
    return p.read_text(encoding="utf-8") if p.exists() else ""
