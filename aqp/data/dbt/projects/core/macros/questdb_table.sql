{# QuestDB custom materialization: 'questdb_table'.

Emits the canonical PARTITION BY + WAL + DEDUP UPSERT KEYS DDL
that QuestDB requires for concurrent writers. The standard
dbt-postgres materializations do not include these clauses; without
them, the QuestDB docs warn:

  "Non-partitioned tables cannot use WAL"
  "QuestDB won't enforce uniqueness for individual columns…
   Data integrity must be managed at the application level."

This macro forces every materialised table to be partitioned and
WAL-enabled, with deduplication keys derived from the model
config block:

  {{ config(
       materialized='questdb_table',
       partition_by='DAY',
       wal=true,
       dedup_keys=['ts','symbol']
  ) }}
#}

{% materialization questdb_table, adapter='postgres' %}
  {%- set partition_by = config.get('partition_by', 'DAY') -%}
  {%- set wal_enabled = config.get('wal', true) -%}
  {%- set dedup_keys = config.get('dedup_keys', ['ts']) -%}
  {%- set target_relation = this.incorporate(type='table') -%}

  {{ run_hooks(pre_hooks) }}

  {%- set sql_to_create -%}
    CREATE TABLE IF NOT EXISTS {{ target_relation }} AS (
      {{ sql }}
    )
    TIMESTAMP({{ dedup_keys[0] }})
    PARTITION BY {{ partition_by }}
    {% if wal_enabled %}WAL{% endif %}
    DEDUP UPSERT KEYS({{ dedup_keys | join(', ') }})
  {%- endset -%}

  {%- call statement('main') -%}
    {{ sql_to_create }}
  {%- endcall -%}

  {{ run_hooks(post_hooks) }}

  {{ return({'relations': [target_relation]}) }}
{% endmaterialization %}
