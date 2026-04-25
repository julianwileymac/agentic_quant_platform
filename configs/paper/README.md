# Paper trading recipes

Each YAML file in this directory is a self-contained recipe for the paper
trading engine. Run locally with::

    aqp paper run --config configs/paper/alpaca_mean_rev.yaml
    aqp paper run --config configs/paper/ibkr_mean_rev.yaml
    aqp paper run --config configs/paper/tradier_rest.yaml

Or kick off via Celery (so the session survives SIGHUP)::

    aqp paper run --config configs/paper/alpaca_mean_rev.yaml --celery

## Credential flow

Broker creds come from ``.env`` (see `.env.example` for the canonical
list of ``AQP_*`` variables). The broker adapters call
``aqp.config.settings`` at construction time, so you can leave the
``kwargs`` block empty in a YAML and rely on env vars — exactly like the
backtest configs work today.

## Dry-run mode

`session.dry_run: true` forces the engine to swap in the simulated
brokerage and a ``DeterministicReplayFeed`` over the local Parquet lake
so you can smoke-test strategy logic without a live subscription.

## Kill-switch

All paper sessions respect the global kill-switch
(`POST /portfolio/kill_switch`). On engagement the current bar is
processed to completion, open orders are cancelled, and the session
exits with `status=completed`.
