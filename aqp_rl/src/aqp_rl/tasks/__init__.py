"""Celery task wrappers for ``aqp_rl``.

Public surface (registered Celery task names — call via ``.delay(...)``):

- ``aqp.tasks.rl_tasks.train_rl_experiment``
- ``aqp.tasks.rl_tasks.evaluate_rl_experiment``
- ``aqp.tasks.rl_tasks.replay_trajectories``
- ``aqp.tasks.rl_tasks.walk_forward_ensemble``
- ``aqp.tasks.rl_tasks.best_of_n_search``
- ``aqp.tasks.rl_tasks.paper_trade_rl``

Task names retain the legacy ``aqp.tasks.rl_tasks.*`` prefix so
in-flight Celery messages keep routing to the same handler. Import-time
registration happens when ``aqp/tasks/celery_app.py`` includes
``aqp_rl.tasks.rl_tasks`` (per the strangler migration in
``aqp_docs/docs/concepts/platform/repository-split.md``).
"""
from __future__ import annotations
