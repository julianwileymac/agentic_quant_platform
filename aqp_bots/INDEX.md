# aqp_bots Index

## Live Implementation

- Runtime package: `.`
- API routes: `../aqp/api/routes/bots.py`
- Celery tasks: `../aqp/tasks/bot_tasks.py`
- Persistence: `../aqp/persistence/models_bots.py`
- Sample specs: `templates/trading/` and `templates/research/`
- Canonical docs: `../docs/bots.md`

## Template Categories

| Category | Current examples | Notes |
| --- | --- | --- |
| Trading bot | `templates/trading/dual_ma_aapl.yaml` | Strategy/backtest/paper oriented |
| Research bot | `templates/research/equity_research_bot.yaml` | Agent/RAG/chat oriented |

## Future Extraction Gates

1. Define interfaces for backtest, paper trading, agent runtime, task
   dispatch, and persistence.
2. Keep registry lookup for templates under this boundary.
3. Keep backwards-compatible config lookup for `configs/bots/`.
4. Verify `BotRuntime` remains the only execution path.

