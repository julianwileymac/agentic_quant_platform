{# Corporate actions SCD2 — splits, dividends, mergers, spin-offs.

Strategy 'timestamp' rather than 'check' because the vendor feed
exposes a reliable `updated_at` field; per dbt docs the timestamp
strategy is "recommended … because it handles column additions
and deletions more efficiently than the check strategy".
#}

{% snapshot snap_corporate_actions %}
{{
  config(
    target_schema='snapshots',
    unique_key='action_id',
    strategy='timestamp',
    updated_at='updated_at',
    invalidate_hard_deletes=True,
    tags=['snapshot:serial']
  )
}}
select
  action_id,
  symbol,
  action_type,
  announcement_date,
  ex_date,
  record_date,
  pay_date,
  split_factor,
  dividend_amount,
  currency,
  updated_at
from {{ source('vendor', 'corporate_actions_latest') }}
{% endsnapshot %}
