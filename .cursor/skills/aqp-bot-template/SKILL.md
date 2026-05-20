# AQP Bot Template

Use this skill when creating or reviewing a TradingBot or ResearchBot
template.

## Workflow

1. Read `aqp_bots/AGENTS.md` and `docs/bots.md`.
2. Choose `aqp_bots/templates/trading/` for deployable trading bots or
   `aqp_bots/templates/research/` for research/chat bots.
3. Use existing registry aliases and module paths.
4. Keep secrets out of specs; reference credential IDs or placeholders.
5. Verify the template composes existing strategy, engine, ML, RAG, and
   agent primitives instead of reimplementing them.

## Checks

```bash
python -m pytest tests/test_bot*.py tests/bots
```

Use the closest existing bot tests in the checkout. Runtime behavior must
continue to flow through `BotRuntime`.

