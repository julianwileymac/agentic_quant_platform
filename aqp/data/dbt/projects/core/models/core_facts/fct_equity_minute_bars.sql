{{ config(
    materialized='questdb_incremental',
    partition_by='DAY',
    wal=true,
    dedup_keys=['ts', 'symbol'],
    on_schema_change='append_new_columns',
    access='public'
) }}

-- Canonical minute OHLCV bars adjusted for corporate actions.
-- Source-of-truth for every downstream team's signals + backtest.
with raw as (
    select * from {{ source('vendor', 'polygon_aggregates_minute') }}
    {% if is_incremental() %}
      where ingestion_ts > (select max(ingestion_ts) from {{ this }})
    {% endif %}
),
adjusted as (
    select
      r.t::timestamp                              as ts,
      r.ticker                                     as symbol,
      r.o  * coalesce(ca.split_factor, 1.0)        as open,
      r.h  * coalesce(ca.split_factor, 1.0)        as high,
      r.l  * coalesce(ca.split_factor, 1.0)        as low,
      r.c  * coalesce(ca.split_factor, 1.0)        as close,
      r.v::double precision
        / nullif(coalesce(ca.split_factor, 1.0), 0) as volume,
      r.vw                                         as vwap,
      r.ingestion_ts
    from raw r
    left join {{ ref('snap_corporate_actions') }} ca
      on  r.ticker = ca.symbol
      and ca.dbt_valid_from <= r.t::timestamp
      and (ca.dbt_valid_to >  r.t::timestamp or ca.dbt_valid_to is null)
)
select * from adjusted
