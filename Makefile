.PHONY: help install install-full up down logs bootstrap ingest index train backtest \
	api worker beat ui dash paper paper-dry otel test lint format clean \
	webui-install webui-dev webui-build webui-start webui-lint webui-typecheck \
	webui-test webui-gen-api webui-export-openapi

help:
	@echo "Agentic Quant Platform — Makefile targets"
	@echo ""
	@echo "  install       Install python package in editable mode with dev extras"
	@echo "  install-full  Install package with every optional extra (alpaca, ibkr, tradier, otel, cli, paper)"
	@echo "  up            docker compose up -d (redis, postgres, mlflow, chromadb, otel, jaeger, api, worker, webui, paper)"
	@echo "  down          docker compose down"
	@echo "  logs          Tail container logs"
	@echo "  bootstrap     Create data dirs and apply DB migrations"
	@echo "  ingest        Download default universe via yfinance"
	@echo "  index         Index local data metadata into ChromaDB"
	@echo "  train         Train a DRL agent with the default config"
	@echo "  backtest      Run the reference mean-reversion backtest"
	@echo "  api           Run FastAPI locally via \`aqp api\` (Dash mounted at /dash)"
	@echo "  worker        Run Celery worker locally (all queues incl. paper)"
	@echo "  beat          Run Celery beat locally"
	@echo "  ui            Run Solara UI locally (legacy)"
	@echo "  webui-install Install pnpm deps for the Next.js webui"
	@echo "  webui-dev     Run the Next.js webui locally on :3000"
	@echo "  webui-build   Production build of the Next.js webui"
	@echo "  webui-gen-api Dump openapi.json + regenerate the typed TS client"
	@echo "  dash          Run the standalone Dash monitor (useful when API is down)"
	@echo "  paper         Run the reference paper session (requires broker creds)"
	@echo "  paper-dry     Run the reference paper session in dry-run mode"
	@echo "  otel          Tail the Jaeger UI URL hint"
	@echo "  test          Run the smoke test suite"
	@echo "  lint          ruff + mypy"
	@echo "  format        ruff --fix"
	@echo "  clean         Remove pycache and build artefacts"

install:
	pip install -e ".[dev]"

install-full:
	pip install -e ".[dev,alpaca,ibkr,tradier,otel,cli,paper]"

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

bootstrap:
	python -m scripts.bootstrap

ingest:
	python -m scripts.download_data

index:
	python -m scripts.index_metadata

train:
	python -m scripts.train_agent --config configs/rl/ppo_portfolio.yaml

backtest:
	python -m scripts.run_backtest --config configs/strategies/mean_reversion.yaml

api:
	aqp api

worker:
	aqp worker --queues default,backtest,agents,ingestion,training,paper --concurrency 2

beat:
	aqp beat

ui:
	@echo "[deprecated] 'make ui' starts the legacy Solara UI."
	@echo "             Use 'make webui-dev' for the new Next.js frontend (:3000)."
	@echo "             To run Solara explicitly: 'aqp ui' or 'make ui-solara'"
	aqp ui

ui-solara:
	aqp ui

dash:
	aqp dash --standalone --port 8050

paper:
	aqp paper run --config configs/paper/alpaca_mean_rev.yaml

paper-dry:
	aqp paper run --config configs/paper/alpaca_mean_rev.yaml --dry-run

otel:
	@echo "Jaeger UI: http://localhost:16686"
	@echo "OTEL Collector: localhost:4317 (gRPC) / 4318 (HTTP)"

test:
	pytest tests/ -v

lint:
	ruff check aqp tests scripts
	mypy aqp

format:
	ruff check --fix aqp tests scripts
	ruff format aqp tests scripts

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true

# ---------------------------------------------------------------------------
# Next.js webui targets
# ---------------------------------------------------------------------------
webui-install:
	pnpm --dir webui install

webui-dev:
	pnpm --dir webui dev

webui-build:
	pnpm --dir webui build

webui-start:
	pnpm --dir webui start

webui-lint:
	pnpm --dir webui lint

webui-typecheck:
	pnpm --dir webui typecheck

webui-test:
	pnpm --dir webui test

webui-export-openapi:
	python -m scripts.export_openapi --out data/openapi.json

webui-gen-api: webui-export-openapi
	pnpm --dir webui exec openapi-typescript ../data/openapi.json -o lib/api/generated/schema.d.ts
