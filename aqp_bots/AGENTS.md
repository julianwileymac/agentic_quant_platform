# AGENTS.md

Agent contract for `aqp_bots`.

## Purpose

This boundary owns bot runtime primitives, templates, samples, validation
notes, and agent-readable guidance.

## Hard Boundaries

1. Runtime execution goes through `BotRuntime`; do not bypass it from a bot
   template or route.
2. Bot specs are immutable once snapshotted. Changes create new
   `bot_versions` rows.
3. Bots compose strategy, engine, agent, RAG, paper, and deployment
   references. Do not reimplement those subsystems in a bot.
4. Templates should use real registry aliases and paths that exist today.
5. Keep credentials out of sample specs. Use placeholders and documented
   credential references.

## Where Changes Go

- New sample spec: `templates/trading/` or `templates/research/`.
- Bot runtime behavior: this package.
- Bot API behavior: `../aqp/api/routes/bots.py`.
- Bot task behavior: `../aqp/tasks/bot_tasks.py`.
- Template documentation and checklists: this folder.

## Validation

```bash
python -m pytest tests/bots
```

