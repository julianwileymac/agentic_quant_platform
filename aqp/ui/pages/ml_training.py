"""ML Training — launch & monitor aqp.ml model training runs.

Pairs ``POST /ml/train`` with a small form (pick Alpha158/Alpha360 handler,
a model class, and date segments). Streams progress via the existing
``/chat/stream/{task_id}`` WebSocket that every Celery task publishes to.
"""
from __future__ import annotations

import json

import pandas as pd
import solara
import yaml

from aqp.ui.api_client import get, post

_DEFAULT_DATASET = {
    "class": "DatasetH",
    "module_path": "aqp.ml.dataset",
    "kwargs": {
        "handler": {
            "class": "Alpha158",
            "module_path": "aqp.ml.features.alpha158",
            "kwargs": {
                "instruments": ["SPY", "AAPL", "MSFT", "GOOGL", "AMZN"],
                "start_time": "2019-01-01",
                "end_time": "2024-12-31",
                "fit_start_time": "2019-01-01",
                "fit_end_time": "2022-12-31",
            },
        },
        "segments": {
            "train": ["2019-01-01", "2022-12-31"],
            "valid": ["2023-01-01", "2023-12-31"],
            "test": ["2024-01-01", "2024-12-31"],
        },
    },
}

_DEFAULT_MODEL = {
    "class": "LGBModel",
    "module_path": "aqp.ml.models.tree",
    "kwargs": {
        "num_leaves": 63,
        "learning_rate": 0.05,
        "n_estimators": 500,
    },
}

_DEFAULT_SPLIT_CONFIG = {
    "segments": {
        "train": ["2019-01-01", "2022-12-31"],
        "valid": ["2023-01-01", "2023-12-31"],
        "test": ["2024-01-01", "2024-12-31"],
    }
}

_DEFAULT_PIPELINE = {
    "shared_processors": [],
    "infer_processors": [
        {
            "class": "Fillna",
            "module_path": "aqp.ml.processors",
            "kwargs": {"fields_group": "feature", "fill_value": 0.0},
        }
    ],
    "learn_processors": [
        {
            "class": "DropnaLabel",
            "module_path": "aqp.ml.processors",
            "kwargs": {"fields_group": "label"},
        }
    ],
    "fit_window": {"fit_start_time": "2019-01-01", "fit_end_time": "2022-12-31"},
}


@solara.component
def Page() -> None:
    registered = solara.use_reactive({})
    model_class = solara.use_reactive("LGBModel")
    handler = solara.use_reactive("Alpha158")
    dataset_yaml = solara.use_reactive(yaml.safe_dump(_DEFAULT_DATASET, sort_keys=False))
    model_yaml = solara.use_reactive(yaml.safe_dump(_DEFAULT_MODEL, sort_keys=False))
    split_config_yaml = solara.use_reactive(yaml.safe_dump(_DEFAULT_SPLIT_CONFIG, sort_keys=False))
    pipeline_yaml = solara.use_reactive(yaml.safe_dump(_DEFAULT_PIPELINE, sort_keys=False))
    strategy_id = solara.use_reactive("")
    run_name = solara.use_reactive("ml-train")
    split_name = solara.use_reactive("default-fixed-split")
    split_method = solara.use_reactive("fixed")
    split_symbols = solara.use_reactive("SPY,AAPL,MSFT,GOOGL,AMZN")
    split_start = solara.use_reactive("2019-01-01")
    split_end = solara.use_reactive("2024-12-31")
    selected_dataset_version = solara.use_reactive("")
    pipeline_name = solara.use_reactive("default-pipeline")
    pipeline_description = solara.use_reactive("")
    experiment_name = solara.use_reactive("default-experiment")
    experiment_notes = solara.use_reactive("")
    selected_split_plan = solara.use_reactive("")
    selected_pipeline = solara.use_reactive("")
    selected_experiment = solara.use_reactive("")
    launched = solara.use_reactive(None)
    models = solara.use_reactive([])
    split_plans = solara.use_reactive([])
    pipelines = solara.use_reactive([])
    experiments = solara.use_reactive([])
    dataset_versions = solara.use_reactive([])
    planning_message = solara.use_reactive("")

    def refresh_registered() -> None:
        try:
            registered.set(get("/ml/registered") or {})
        except Exception:
            registered.set({})

    def refresh_models() -> None:
        try:
            models.set(get("/ml/models?limit=50") or [])
        except Exception:
            models.set([])

    def refresh_plans() -> None:
        try:
            raw = get("/ml/split-plans?limit=50") or []
            split_plans.set(raw if isinstance(raw, list) else [])
        except Exception:
            split_plans.set([])
        try:
            raw = get("/ml/pipelines?limit=50") or []
            pipelines.set(raw if isinstance(raw, list) else [])
        except Exception:
            pipelines.set([])
        try:
            raw = get("/ml/experiments?limit=50") or []
            experiments.set(raw if isinstance(raw, list) else [])
        except Exception:
            experiments.set([])
        try:
            catalogs = get("/data/catalog?limit=50") or []
            if not isinstance(catalogs, list):
                catalogs = []
            versions: list[dict] = []
            for row in catalogs:
                cid = row.get("id")
                if not cid:
                    continue
                v_rows = get(f"/data/catalog/{cid}/versions?limit=5") or []
                if isinstance(v_rows, list):
                    versions.extend(v_rows)
            dataset_versions.set(versions)
        except Exception:
            dataset_versions.set([])

    solara.use_effect(refresh_registered, [])
    solara.use_effect(refresh_models, [])
    solara.use_effect(refresh_plans, [])

    def create_split_plan() -> None:
        planning_message.set("")
        try:
            cfg = yaml.safe_load(split_config_yaml.value) or {}
            body = {
                "name": split_name.value,
                "method": split_method.value,
                "config": cfg,
                "vt_symbols": [s.strip() for s in split_symbols.value.split(",") if s.strip()],
                "start": split_start.value or None,
                "end": split_end.value or None,
                "dataset_version_id": selected_dataset_version.value or None,
            }
            created = post("/ml/split-plans", json=body)
            selected_split_plan.set(created.get("id") or "")
            planning_message.set(f"Split plan created: {created.get('id')}")
            refresh_plans()
        except Exception as e:
            planning_message.set(f"Split plan failed: {e}")

    def create_pipeline() -> None:
        planning_message.set("")
        try:
            cfg = yaml.safe_load(pipeline_yaml.value) or {}
            body = {
                "name": pipeline_name.value,
                "description": pipeline_description.value or None,
                "shared_processors": cfg.get("shared_processors") or [],
                "infer_processors": cfg.get("infer_processors") or [],
                "learn_processors": cfg.get("learn_processors") or [],
                "fit_window": cfg.get("fit_window") or {},
            }
            created = post("/ml/pipelines", json=body)
            selected_pipeline.set(created.get("id") or "")
            planning_message.set(f"Pipeline saved: {created.get('id')}")
            refresh_plans()
        except Exception as e:
            planning_message.set(f"Pipeline save failed: {e}")

    def create_experiment_plan() -> None:
        planning_message.set("")
        try:
            dataset_cfg = yaml.safe_load(dataset_yaml.value) or {}
            model_cfg = yaml.safe_load(model_yaml.value) or {}
            body = {
                "name": experiment_name.value,
                "dataset_version_id": selected_dataset_version.value or None,
                "split_plan_id": selected_split_plan.value or None,
                "pipeline_recipe_id": selected_pipeline.value or None,
                "dataset_cfg": dataset_cfg,
                "model_cfg": model_cfg,
                "notes": experiment_notes.value or None,
            }
            created = post("/ml/experiments", json=body)
            selected_experiment.set(created.get("id") or "")
            planning_message.set(f"Experiment plan created: {created.get('id')}")
            refresh_plans()
        except Exception as e:
            planning_message.set(f"Experiment create failed: {e}")

    def launch_training() -> None:
        try:
            dataset_cfg = yaml.safe_load(dataset_yaml.value) or {}
            model_cfg = yaml.safe_load(model_yaml.value) or {}
            body = {
                "dataset_cfg": dataset_cfg,
                "model_cfg": model_cfg,
                "run_name": run_name.value,
                "strategy_id": strategy_id.value or None,
                "register_alpha": True,
                "experiment_plan_id": selected_experiment.value or None,
                "split_plan_id": selected_split_plan.value or None,
                "pipeline_recipe_id": selected_pipeline.value or None,
                "dataset_version_id": selected_dataset_version.value or None,
            }
            launched.set(post("/ml/train", json=body))
        except Exception as e:
            launched.set({"error": str(e)})

    def apply_preset() -> None:
        dataset = json.loads(json.dumps(_DEFAULT_DATASET))
        model = json.loads(json.dumps(_DEFAULT_MODEL))
        dataset["kwargs"]["handler"]["class"] = handler.value
        dataset["kwargs"]["handler"]["module_path"] = (
            "aqp.ml.features.alpha158" if handler.value == "Alpha158" else "aqp.ml.features.alpha360"
        )
        model["class"] = model_class.value
        if model_class.value in {"LGBModel", "XGBModel", "CatBoostModel", "DEnsembleModel"}:
            model["module_path"] = "aqp.ml.models.tree" if model_class.value != "DEnsembleModel" else "aqp.ml.models.ensemble"
            if model_class.value == "XGBModel":
                model["module_path"] = "aqp.ml.models.tree"
            model["kwargs"] = {"n_estimators": 500, "learning_rate": 0.05}
        elif model_class.value == "LinearModel":
            model["module_path"] = "aqp.ml.models.linear"
            model["kwargs"] = {"estimator": "ridge", "alpha": 1.0}
        else:
            # Torch models.
            slug = model_class.value.replace("Model", "").lower()
            if slug.endswith("seq2seq") or slug == "transformerforecaster" or slug == "dilatedcnnseq2seq":
                model["module_path"] = "aqp.ml.models.torch.seq2seq"
            else:
                model["module_path"] = f"aqp.ml.models.torch.{slug}"
            model["kwargs"] = {"lr": 0.001, "batch_size": 128, "n_epochs": 10}
            # Swap DatasetH -> TSDatasetH for sequence models.
            dataset["class"] = "TSDatasetH"
            dataset["kwargs"]["step_len"] = 20
        dataset_yaml.set(yaml.safe_dump(dataset, sort_keys=False))
        model_yaml.set(yaml.safe_dump(model, sort_keys=False))

    with solara.Column(gap="16px", style={"padding": "18px"}):
        solara.Markdown("# ML Training")
        solara.Markdown(
            "Plan reproducible split/pipeline/experiment artifacts, then launch "
            "native AQP model training onto the ``ml`` Celery queue."
        )

        with solara.Row(gap="12px"):
            handler_choices = registered.value.get("handlers", ["Alpha158", "Alpha360"])
            solara.Select(label="Feature handler", value=handler, values=handler_choices or ["Alpha158", "Alpha360"])
            torch_choices = registered.value.get("torch", [])
            tree_choices = registered.value.get("tree", ["LGBModel"])
            linear = registered.value.get("linear", [])
            model_choices = [*tree_choices, *linear, *torch_choices] or [
                "LGBModel",
                "XGBModel",
                "LSTMModel",
                "TransformerModel",
            ]
            solara.Select(label="Model class", value=model_class, values=model_choices)
            solara.Button("Apply preset", on_click=apply_preset)
            solara.Button("Refresh registry", on_click=refresh_registered)

        with solara.Row(gap="12px"):
            solara.InputText("Run name", value=run_name)
            solara.InputText("Strategy id (optional)", value=strategy_id)
            solara.Button("Launch training", on_click=launch_training, color="primary")

        with solara.Card("Split planning"):
            with solara.Row(gap="12px"):
                solara.InputText("Split plan name", value=split_name)
                solara.Select(
                    label="Method",
                    value=split_method,
                    values=["fixed", "purged_kfold", "walk_forward"],
                )
                solara.InputText("vt_symbols (comma-separated)", value=split_symbols)
            with solara.Row(gap="12px"):
                solara.InputText("start", value=split_start)
                solara.InputText("end", value=split_end)
                version_choices = [""] + [str(v.get("id")) for v in dataset_versions.value if v.get("id")]
                solara.Select(
                    label="Dataset version id (optional)",
                    value=selected_dataset_version,
                    values=version_choices or [""],
                )
            solara.InputTextArea("split config YAML", value=split_config_yaml, rows=8)
            solara.Button("Create split plan", on_click=create_split_plan, color="primary")

        with solara.Card("Preprocessing pipeline"):
            with solara.Row(gap="12px"):
                solara.InputText("Pipeline name", value=pipeline_name)
                solara.InputText("Description", value=pipeline_description)
            solara.InputTextArea("pipeline recipe YAML", value=pipeline_yaml, rows=10)
            solara.Button("Save pipeline recipe", on_click=create_pipeline, color="primary")

        with solara.Card("Experiment planning"):
            with solara.Row(gap="12px"):
                solara.InputText("Experiment name", value=experiment_name)
                split_choices = [""] + [str(p.get("id")) for p in split_plans.value if p.get("id")]
                pipe_choices = [""] + [str(p.get("id")) for p in pipelines.value if p.get("id")]
                solara.Select(label="Split plan id", value=selected_split_plan, values=split_choices or [""])
                solara.Select(label="Pipeline id", value=selected_pipeline, values=pipe_choices or [""])
            solara.InputText("Notes", value=experiment_notes)
            solara.Button("Create experiment plan", on_click=create_experiment_plan, color="primary")

        solara.Markdown("### Dataset config (YAML)")
        solara.InputTextArea("dataset_cfg", value=dataset_yaml, rows=18)
        solara.Markdown("### Model config (YAML)")
        solara.InputTextArea("model_cfg", value=model_yaml, rows=12)

        if planning_message.value:
            solara.Info(planning_message.value)

        if launched.value:
            if "error" in launched.value:
                solara.Error(launched.value["error"])
            else:
                solara.Info(f"Task queued: {launched.value.get('task_id')}")
                solara.Markdown(
                    f"[Stream progress]({launched.value.get('stream_url', '')})"
                )

        solara.Markdown("### Registered models")
        if models.value:
            solara.DataFrame(pd.DataFrame(models.value), items_per_page=25)
        else:
            solara.Markdown("_No runs yet._")

        solara.Markdown("### Split plans")
        if split_plans.value:
            solara.DataFrame(pd.DataFrame(split_plans.value), items_per_page=10)
        else:
            solara.Markdown("_No split plans yet._")

        solara.Markdown("### Pipeline recipes")
        if pipelines.value:
            solara.DataFrame(pd.DataFrame(pipelines.value), items_per_page=10)
        else:
            solara.Markdown("_No pipeline recipes yet._")

        solara.Markdown("### Experiment plans")
        if experiments.value:
            solara.DataFrame(pd.DataFrame(experiments.value), items_per_page=10)
        else:
            solara.Markdown("_No experiment plans yet._")
