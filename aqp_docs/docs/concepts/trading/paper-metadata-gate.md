---
title: 'Paper Metadata Gate (Strict-Only)'
summary: 'After this rollout, paper-trading sessions **require** both `session.model_urn` and `session.pipeline_urn` to be present and valid at startup'
owner: trading-team
last_reviewed: 2026-05-25
audience: both
---

# Paper Metadata Gate (Strict-Only)

## Breaking change

After this rollout, paper-trading sessions **require** both `session.model_urn`
and `session.pipeline_urn` to be present and valid at startup.

If either URN is missing, malformed, unresolved in `entity_aspects`, or (for
the model URN) resolves to a non-`Production`/non-`Staging` model status, the
session raises `MetadataValidationError` and refuses to start.

There is no warn-only fallback mode.

## How strict gate validation works

The paper gate performs these checks in order:

1. Parse `model_urn` and `pipeline_urn` with AQP URN validation.
2. Resolve `mlModelMetadata` for `model_urn` and `pipelineMetadata` for
   `pipeline_urn`.
3. Enforce model lifecycle status (`Production` or `Staging` only).
4. Emit a `metadata_gate` progress frame and raise on any validation error.

Startup is blocked until all checks pass.

## Seeded URNs from migration 0049

Alembic revision `0049_paper_metadata_seed_aspects` seeds these baseline URNs:

- `configs/paper/alpaca_mean_rev.yaml`
  - `urn:aqp:mlmodel:prod:alpaca_mean_reversion_v1`
  - `urn:aqp:pipeline:prod:alpaca_mean_reversion_loop`
- `configs/paper/ibkr_mean_rev.yaml`
  - `urn:aqp:mlmodel:prod:ibkr_mean_reversion_v1`
  - `urn:aqp:pipeline:prod:ibkr_mean_reversion_loop`
- `configs/paper/avellaneda_stoikov_quotes.yaml`
  - `urn:aqp:mlmodel:prod:avellaneda_stoikov_v1`
  - `urn:aqp:pipeline:prod:avellaneda_stoikov_quotes_loop`
- `configs/paper/lucic_tse_options.yaml`
  - `urn:aqp:mlmodel:prod:lucic_tse_options_v1`
  - `urn:aqp:pipeline:prod:lucic_tse_options_loop`
- `configs/paper/tradier_rest.yaml`
  - `urn:aqp:mlmodel:prod:tradier_rest_baseline_v1`
  - `urn:aqp:pipeline:prod:tradier_rest_loop`

To add a new paper config, seed matching `MlModel` + `Pipeline` aspects first,
then point YAML `session.model_urn` / `session.pipeline_urn` at those URNs.

## Operator runbook (custom paper YAMLs)

1. Run migrations through `0049_paper_metadata_seed_aspects`.
2. For each custom paper model, register an `MlModel` aspect (status must be
   `Production` or `Staging`) using the `aspect.register_model` MCP tool.
3. Register a matching `Pipeline` aspect for each paper pipeline URN.
4. Update custom YAML files so `session.model_urn` and `session.pipeline_urn`
   match the newly seeded aspects.
5. Start paper sessions and confirm metadata-gate startup checks pass.

## Rollback

If you must revert this rollout:

1. `alembic downgrade 0048`
2. `git revert <this-pr-commit>`

After rollback, redeploy and re-run paper sessions with the reverted code/docs.
