"""``model.torch`` — train a PyTorch MLP / sequence model on the upstream panel.

Phase 2 ships a thin MLP wrapper (Linear -> ReLU -> Linear -> Linear)
that's portable enough to demo the GraphSpec without forcing the user
to author a custom architecture. ``params.snippet_id`` is reserved
for Phase 4 (user-authored architectures via the Tier-2 sandbox); it
returns a structured error today rather than silently degrading to
the placeholder MLP.

Params:

- ``target_column`` (str, required).
- ``task`` (Literal['regression','classification'], default 'regression').
- ``hidden_dims`` (list[int], default ``[64, 32]``).
- ``epochs`` (int, default 25).
- ``batch_size`` (int, default 256).
- ``lr`` (float, default 1e-3).
- ``test_size`` (float, default 0.25).
- ``random_state`` (int, default 42).
- ``snippet_id`` (str, optional) — Phase 4 escape hatch for custom
  architectures.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.lab.executors._helpers import (
    base_locator,
    numeric_columns,
    resolve_upstream_frame,
    stash_arrow_output,
)
from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def execute(node: Any, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    target_column = params.get("target_column")
    if not target_column:
        return NodeResult(
            status="error",
            error="model.torch requires params.target_column",
            log_label="model.torch:missing_target",
        )
    if params.get("snippet_id"):
        return NodeResult(
            status="error",
            error=(
                "model.torch params.snippet_id requires the Tier-2 gVisor "
                "sandbox (Phase 4). For now author the architecture inline."
            ),
            log_label="model.torch:snippet_phase4",
        )
    task = str(params.get("task") or "regression").lower()
    if task not in {"regression", "classification"}:
        return NodeResult(
            status="error",
            error=f"model.torch: unknown task {task!r}",
            log_label="model.torch:bad_task",
        )
    hidden_dims = list(params.get("hidden_dims") or [64, 32])
    epochs = int(params.get("epochs") or 25)
    batch_size = int(params.get("batch_size") or 256)
    lr = float(params.get("lr") or 1e-3)
    test_size = float(params.get("test_size") or 0.25)
    random_state = int(params.get("random_state") or 42)

    df = resolve_upstream_frame(ctx)
    if df is None or target_column not in df.columns:
        return NodeResult(
            status="error",
            error=f"model.torch: upstream frame missing target {target_column!r}",
            log_label="model.torch:missing_target_column",
        )

    feature_cols = numeric_columns(
        df.drop(columns=[target_column], errors="ignore"),
        params.get("feature_columns")
        if isinstance(params.get("feature_columns"), list)
        else None,
    )
    if not feature_cols:
        return NodeResult(
            status="error",
            error="model.torch: no numeric feature columns",
            log_label="model.torch:no_features",
        )

    try:
        import torch
        import torch.nn as nn
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"PyTorch not installed: {exc}",
            log_label="model.torch:no_torch",
        )
    try:
        from sklearn.model_selection import train_test_split
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"sklearn not installed: {exc}",
            log_label="model.torch:no_sklearn",
        )

    torch.manual_seed(random_state)
    X = df[feature_cols].astype(float).to_numpy()
    if task == "classification":
        y = df[target_column].astype(int).to_numpy()
        n_classes = int(np.max(y)) + 1 if len(y) else 2
    else:
        y = df[target_column].astype(float).to_numpy()
        n_classes = 1

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state
    )
    X_train_t = torch.tensor(X_train, dtype=torch.float32)
    X_test_t = torch.tensor(X_test, dtype=torch.float32)
    if task == "classification":
        y_train_t = torch.tensor(y_train, dtype=torch.long)
        y_test_t = torch.tensor(y_test, dtype=torch.long)
        loss_fn = nn.CrossEntropyLoss()
    else:
        y_train_t = torch.tensor(y_train, dtype=torch.float32).unsqueeze(1)
        y_test_t = torch.tensor(y_test, dtype=torch.float32).unsqueeze(1)
        loss_fn = nn.MSELoss()

    layers: list[nn.Module] = []
    in_dim = len(feature_cols)
    for h in hidden_dims:
        layers.extend([nn.Linear(in_dim, int(h)), nn.ReLU()])
        in_dim = int(h)
    layers.append(nn.Linear(in_dim, max(1, n_classes)))
    net = nn.Sequential(*layers)
    optim = torch.optim.Adam(net.parameters(), lr=lr)

    n = X_train_t.shape[0]
    losses: list[float] = []
    for _epoch in range(epochs):
        perm = torch.randperm(n)
        epoch_loss = 0.0
        for start in range(0, n, batch_size):
            idx = perm[start : start + batch_size]
            optim.zero_grad()
            preds = net(X_train_t[idx])
            loss = loss_fn(preds, y_train_t[idx])
            loss.backward()
            optim.step()
            epoch_loss += float(loss.item()) * len(idx)
        losses.append(epoch_loss / max(1, n))

    with torch.no_grad():
        test_preds = net(X_test_t)
        if task == "classification":
            preds_arr = test_preds.argmax(dim=1).cpu().numpy()
        else:
            preds_arr = test_preds.squeeze(1).cpu().numpy()

    metrics = _score(task, y_test, preds_arr)
    metrics["final_train_loss"] = float(losses[-1]) if losses else 0.0
    ctx.extras.setdefault("models", {})[node.id] = {
        "framework": "torch",
        "task": task,
        "model": net,
        "feature_columns": feature_cols,
        "target_column": target_column,
    }
    pred_df = pd.DataFrame({"y_true": y_test, "y_pred": preds_arr})
    stash_arrow_output(ctx, node.id, pred_df)
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, pred_df, kind="model_predictions"),
            "framework": "torch",
            "task": task,
            "epochs": epochs,
            "hidden_dims": hidden_dims,
            "model_in_extras": True,
        },
        metrics={
            **metrics,
            "n_train": int(len(X_train)),
            "n_test": int(len(X_test)),
        },
        log_label=f"model.torch:{task}",
    )


def _score(task: str, y_true: Any, y_pred: Any) -> dict[str, float]:
    y_true_arr = np.asarray(y_true).ravel()
    y_pred_arr = np.asarray(y_pred).ravel()
    if task == "classification":
        accuracy = float((y_true_arr == y_pred_arr).mean()) if y_true_arr.size else 0.0
        return {"accuracy": accuracy}
    mse = float(((y_true_arr - y_pred_arr) ** 2).mean())
    return {"mse": mse, "rmse": float(np.sqrt(mse))}


__all__ = ["execute"]
