{# QuestDB incremental materialization.

Two-step strategy:

1. First run: emit the CREATE TABLE ... TIMESTAMP() PARTITION BY ...
   WAL DEDUP UPSERT KEYS(...) DDL.
2. Subsequent runs: INSERT the new rows; QuestDB's DEDUP UPSERT
   semantics (per docs: "DEDUP UPSERT KEYS" replaces matching rows
   on the dedup-key set) handle late corrections without
   double-counting.

Config block:

  {{ config(
       materialized='questdb_incremental',
       partition_by='DAY',
       wal=true,
       dedup_keys=['ts','symbol'],
       on_schema_change='append_new_columns'
  ) }}
#}

{% materialization questdb_incremental, adapter='postgres' %}
  {%- set partition_by = config.get('partition_by', 'DAY') -%}
  {%- set wal_enabled = config.get('wal', true) -%}
  {%- set dedup_keys = config.get('dedup_keys', ['ts']) -%}
  {%- set target_relation = this.incorporate(type='table') -%}
  {%- set existing_relation = load_cached_relation(this) -%}

  {{ run_hooks(pre_hooks) }}

  {%- if existing_relation is none -%}
    {%- set sql_create -%}
      CREATE TABLE {{ target_relation }} AS (
        {{ sql }}
      )
      TIMESTAMP({{ dedup_keys[0] }})
      PARTITION BY {{ partition_by }}
      {% if wal_enabled %}WAL{% endif %}
      DEDUP UPSERT KEYS({{ dedup_keys | join(', ') }})
    {%- endset -%}
    {%- call statement('main') -%}
      {{ sql_create }}
    {%- endcall -%}
  {%- else -%}
    {%- set sql_insert -%}
      INSERT INTO {{ target_relation }} (
        {{ sql }}
      )
    {%- endset -%}
    {%- call statement('main') -%}
      {{ sql_insert }}
    {%- endcall -%}
  {%- endif -%}

  {{ run_hooks(post_hooks) }}

  {{ return({'relations': [target_relation]}) }}
{% endmaterialization %}
