{# Symbol master SCD2 — captures ticker changes, delistings, exchange
   migrations. Used by every backtest that needs to resolve a
   historical ticker accurately.
#}

{% snapshot snap_symbol_master %}
{{
  config(
    target_schema='snapshots',
    unique_key='symbol_id',
    strategy='check',
    check_cols=['symbol', 'exchange', 'is_active', 'security_type'],
    invalidate_hard_deletes=True,
    tags=['snapshot:serial']
  )
}}
select
  symbol_id,
  symbol,
  exchange,
  security_type,
  is_active,
  cusip,
  isin,
  figi
from {{ source('vendor', 'symbol_master_latest') }}
{% endsnapshot %}
