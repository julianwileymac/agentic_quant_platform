# Regulatory Data Sources (CFPB / FDA / USPTO)

Phase 2 of the agentic-RAG expansion adds first-class adapters for the
three regulatory bodies feeding the **third-order** RAG layer:

| Source | Adapter | Iceberg namespace.table | Postgres table | Domain enum |
| --- | --- | --- | --- | --- |
| CFPB Consumer Complaint Database | [aqp/data/sources/cfpb/complaints.py](../aqp/data/sources/cfpb/complaints.py) | `aqp_cfpb.complaints` | `cfpb_complaints` | `regulatory.cfpb.complaint` |
| FDA drug + device applications | [aqp/data/sources/fda/applications.py](../aqp/data/sources/fda/applications.py) | `aqp_fda.applications` | `fda_applications` | `regulatory.fda.application` |
| FDA adverse events (FAERS / MAUDE) | [aqp/data/sources/fda/adverse_events.py](../aqp/data/sources/fda/adverse_events.py) | `aqp_fda.adverse_events` | `fda_adverse_events` | `regulatory.fda.adverse_event` |
| FDA enforcement recalls | [aqp/data/sources/fda/recalls.py](../aqp/data/sources/fda/recalls.py) | `aqp_fda.recalls` | `fda_recalls` | `regulatory.fda.recall` |
| USPTO granted patents (PatentsView) | [aqp/data/sources/uspto/patents.py](../aqp/data/sources/uspto/patents.py) | `aqp_uspto.patents` | `uspto_patents` | `regulatory.uspto.patent` |
| USPTO trademarks (TSDR) | [aqp/data/sources/uspto/trademarks.py](../aqp/data/sources/uspto/trademarks.py) | `aqp_uspto.trademarks` | `uspto_trademarks` | `regulatory.uspto.trademark` |
| USPTO patent assignments (PEDS) | [aqp/data/sources/uspto/assignments.py](../aqp/data/sources/uspto/assignments.py) | `aqp_uspto.assignments` | `uspto_assignments` | `regulatory.uspto.assignment` |

Each adapter implements [DataSourceAdapter](../aqp/data/sources/base.py)
and writes through `iceberg_catalog.append_arrow`,
`register_dataset_version`, and the per-source Postgres upsert helper.

## API surface

```
GET  /cfpb/probe                      → CfpbProbeResponse
GET  /cfpb/search?company=&product=…  → raw search hits
POST /cfpb/ingest                     → 202 + task_id
GET  /cfpb/complaints?company=…       → curated rows from Postgres

GET  /fda/probe                       → FdaProbeResponse
GET  /fda/search/{endpoint:path}      → raw openFDA results
POST /fda/ingest/applications         → 202 + task_id
POST /fda/ingest/adverse-events       → 202 + task_id
POST /fda/ingest/recalls              → 202 + task_id
GET  /fda/applications | /fda/recalls → curated Postgres rows

GET  /uspto/probe                     → UsptoProbeResponse
POST /uspto/ingest/patents            → 202 + task_id
POST /uspto/ingest/trademarks         → 202 + task_id
POST /uspto/ingest/assignments        → 202 + task_id
GET  /uspto/patents | /uspto/trademarks | /uspto/assignments
```

## Celery tasks

All ingest tasks live in
[aqp/tasks/regulatory_tasks.py](../aqp/tasks/regulatory_tasks.py) and
route through the `ingestion` queue. Each emits progress on the shared
`_progress` bus so the existing webui WebSocket consumers pick them up
unchanged.

## Identifier linkage

Adapters that can identify the issuer behind a row emit
:class:`IdentifierSpec` records (`scheme="cfpb_company_name"`,
`scheme="fda_sponsor_name"`, `scheme="uspto_assignee"`) into the shared
[IdentifierResolver](../aqp/data/sources/resolvers/identifiers.py)
graph. The RAG indexers under
[aqp/rag/indexers/](../aqp/rag/indexers/) consult that graph to attach
a `vt_symbol` tag to every chunk so the trader and analysis agents can
scope retrievals by instrument.

## Configuration

```
AQP_CFPB_USER_AGENT      = aqp-research/0.1 (+https://github.com/...)
AQP_CFPB_API_URL         = https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1
AQP_FDA_API_KEY          = (optional, raises rate limits)
AQP_FDA_BASE_URL         = https://api.fda.gov
AQP_USPTO_API_KEY        = (required for PatentsView)
AQP_USPTO_PATENTSVIEW_URL= https://search.patentsview.org/api/v1
AQP_USPTO_PEDS_URL       = https://ped.uspto.gov/api
AQP_USPTO_TSDR_URL       = https://tsdrapi.uspto.gov/ts/cd/casestatus
```
