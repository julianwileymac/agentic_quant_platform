{# Survivorship-bias-free SP500 / Russell 3000 reconstruction.

Strategy 'check' with `invalidate_hard_deletes=True` so a symbol
that drops out of the index gets its `dbt_valid_to` set to the
snapshot timestamp instead of being deleted. The Phase 2
backtest pattern from the blueprint:

  SELECT symbol FROM {{ ref('snap_index_constituents') }}
  WHERE index = 'SP500'
    AND dbt_valid_from <= '2018-06-15'
    AND (dbt_valid_to > '2018-06-15' OR dbt_valid_to IS NULL)
    AND is_active = true

routes all snapshot writes through the `dbt_snapshots` Dagster
concurrency pool (limit=1) — the Phase 2 dagster.yaml entry plus
the `tags: ['snapshot:serial']` config below pins it.
#}

{% snapshot snap_index_constituents %}
{{
  config(
    target_schema='snapshots',
    unique_key="index || '_' || symbol",
    strategy='check',
    check_cols=['weight', 'is_active'],
    invalidate_hard_deletes=True,
    tags=['snapshot:serial']
  )
}}
select
  index,
  symbol,
  weight,
  is_active
from {{ source('vendor', 'index_constituents_latest') }}
{% endsnapshot %}
