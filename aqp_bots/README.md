# aqp_bots

Status: active bot package.

`aqp_bots` owns bot runtime primitives, templates, samples, test evidence,
and bot-specific agent guidance. The legacy `../aqp/bots` package now
contains compatibility shims that re-export this package.

## Owns

- TradingBot and ResearchBot sample specs.
- Template documentation for common bot use cases.
- Bot validation checklists and smoke-test results.
- Agent skills and prompts for creating or reviewing bot templates.

## Current Source Locations

| Responsibility | Current path |
| --- | --- |
| Runtime package | `.` |
| API routes | `../aqp/api/routes/bots.py` |
| Celery tasks | `../aqp/tasks/bot_tasks.py` |
| Persistence models | `../aqp/persistence/models_bots.py` |
| Sample templates | `templates/` |
| Canonical docs | `../aqp_docs/bots.md` |

## Split Rule

Runtime changes happen here and must preserve `BotRuntime`, immutable
`bot_versions`, and the existing task/API wrappers.

