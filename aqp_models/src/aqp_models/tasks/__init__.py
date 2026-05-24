"""Celery task wrappers for ``aqp_models``.

Public surface (registered Celery task names — call via ``.delay(...)``):

ML training + evaluation:

- ``aqp.tasks.ml_tasks.train_ml_model``
- ``aqp.tasks.ml_tasks.evaluate_ml_model``
- ``aqp.tasks.ml_tasks.run_ml_experiment``
- ``aqp.tasks.ml_tasks.run_alpha_backtest_experiment``
- ``aqp.tasks.ml_tasks.preview_ml_flow``
- ``aqp.tasks.ml_tasks.test_ml_deployment``

ML test workbench:

- ``aqp.tasks.ml_test_tasks.run_ml_test``
- ``aqp.tasks.ml_test_tasks.predict_single``
- ``aqp.tasks.ml_test_tasks.predict_batch``
- ``aqp.tasks.ml_test_tasks.compare_models``
- ``aqp.tasks.ml_test_tasks.scenario_perturbation``

Finetune trainer:

- ``aqp.tasks.finetune_tasks.train_finetune``

Legacy training (kept for back-compat):

- ``aqp.tasks.training_tasks.train_rl``
- ``aqp.tasks.training_tasks.evaluate_rl``
- ``aqp.tasks.training_tasks.run_rl_application``

Task names retain the legacy ``aqp.tasks.<file>.*`` prefix so in-flight
Celery messages keep routing to the same handler. Import-time
registration happens when ``aqp/tasks/celery_app.py`` includes
``aqp_models.tasks.<file>`` (per the strangler migration in
``aqp_docs/repository-split.md``).
"""
from __future__ import annotations
