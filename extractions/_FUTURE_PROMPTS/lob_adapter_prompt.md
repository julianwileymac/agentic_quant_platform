# Future-Run Prompt — hftbacktest LOB Adapter

> **Audience:** A future Cursor agent run that will deepen the hftbacktest integration beyond the stubs shipped in the initial rehydration.
>
> **Status as of this prompt:** AQP has the analytics (HFT metrics in `aqp/backtest/hft_metrics.py`, microstructure features in `aqp/data/microstructure.py`, the `LobStrategy` ABC stub in `aqp/strategies/lob.py`, and 5 stub strategies under `aqp/strategies/hft/` that subclass it). What's missing: the actual LOB backtest engine that drives those strategies.

## Goal

Implement an optional LOB backtest engine in AQP that wraps `nkaz001/hftbacktest` (`pip install hftbacktest` — needs Maturin + Rust toolchain at install time) so the 5 stub HFT strategies become runnable.

## Itemized work

1. **Optional dep** — Add `aqp[hft]` extras in `pyproject.toml`:
   ```toml
   [project.optional-dependencies]
   hft = ["hftbacktest>=2.0.0", "numba>=0.61", "polars>=1.0"]
   ```
   Document the Rust+Maturin install requirement in `docs/installation.md`.

2. **Engine wrapper** — `aqp/backtest/hft.py`:
   - `class LobBacktestEngine`: takes a `LobStrategy` instance + a `BacktestAsset` config (paths to gz feeds, tick/lot sizes, fee model, queue model, latency model).
   - Internally constructs `hftbacktest.HashMapMarketDepthBacktest(...)` and runs an `@numba.njit` driver loop that calls `strategy.on_event(...)`.
   - Returns `BacktestResult` (existing dataclass) with `equity_curve`, `trades`, `summary`. Add HFT-specific fields to `summary` from `hft_metrics.py` (`max_position`, `mean_leverage`, `return_over_trade`, `fill_ratio`, `sample_aware_sharpe`).

3. **Strategy ABC concretization** — `aqp/strategies/lob.py`:
   - The stub already defines `on_event(state) -> list[OrderIntent]`. Add concrete helper methods that wrap `hbt.submit_buy_order(...)`, `hbt.cancel(...)`, `hbt.elapse(...)` so strategy bodies stay pure Python (the runtime will JIT-compile a thin shim).
   - Add `OrderIntent` dataclass with fields matching `hftbacktest`'s order surface (price, qty, side, time-in-force, post-only flag).

4. **Concrete strategies** — Update `aqp/strategies/hft/{glft_mm,grid_mm,imbalance_alpha_mm,basis_alpha_mm,queue_aware_mm}.py`:
   - Remove the `NotImplementedError` from the engine integration point.
   - Wire each strategy's `on_event` to use `aqp/data/microstructure.py` features (OBI, microprice, depth slope) on the live `hbt.depth(asset_no)` accessor.

5. **Celery task** — `aqp/tasks/hft_tasks.py`:
   - `run_lob_backtest(strategy_alias: str, dataset_preset: str, latency_profile: str, queue_model: str)` — long-running task; emits progress every N seconds via `_progress.emit`.
   - Route to a new `hft` queue in `celery_app.py::task_routes`.

6. **REST route** — `aqp/api/routes/lob_backtest.py`:
   - `POST /backtest/lob` — body: `{strategy: ..., dataset: ..., latency: ..., queue: ...}`; returns task ID.
   - `GET /backtest/lob/{task_id}` — status + summary.

7. **UI surfaces**:
   - `webui/app/(shell)/backtest/lob/page.tsx` — wizard for picking strategy + dataset + latency profile.
   - `webui/components/backtest/LobReplayChart.tsx` — visualizes book depth + bid/ask quotes + position over time using `lightweight-charts`.
   - Detail page extension for HFT-aware metric tiles (already added in initial rehydration; gate them on result presence).
   - Replace the "Engine pending" banner on `/data/microstructure` once this lands.

8. **Migration** — None. The `BacktestResult.summary` is a JSON dict; HFT metrics slot in without schema changes.

9. **Tests** — `tests/backtest/test_lob_engine.py`:
   - Hermetic test using the bundled `lob_btcusdt_sample` preset (small gz file from `inspiration/hftbacktest-master/examples/usdm/`).
   - Marker `@pytest.mark.requires_hft` so it skips when `hftbacktest` is not installed.

10. **Docs** — Add `docs/hft-backtest.md` covering install, the `LobStrategy` API, latency/queue model knobs, and how to interpret HFT-aware metrics.

## Context the future agent will need

- `aqp/strategies/lob.py` — the existing ABC.
- `aqp/strategies/hft/` — the 5 stub strategies.
- `aqp/backtest/hft_metrics.py` — already has the metric implementations.
- `aqp/data/microstructure.py` — already has OBI, microprice, depth slope.
- `extractions/hftbacktest/REFERENCE.md` — extraction notes for the engine, latency model, queue model, and metric definitions.
- Upstream reference: `inspiration/hftbacktest-master/py-hftbacktest/hftbacktest/__init__.py` for `BacktestAsset`, `HashMapMarketDepthBacktest`, `binding.py` for the event schema.

## Success criteria

- `pip install -e ".[hft]"` succeeds on a Linux/macOS machine with Rust toolchain.
- `pytest tests/backtest/test_lob_engine.py -m requires_hft` passes.
- `POST /backtest/lob` with `strategy=GLFTMM`, `dataset=lob_btcusdt_sample` returns a task that completes within 5 minutes on a modern laptop.
- The webui `/backtest/lob` page renders the equity curve + book replay.

## Out of scope (next iteration)

- Live trading via `hftbacktest`'s Rust live-bot path.
- Multi-asset LOB strategies (`Making Multiple Markets` notebooks).
- L3 backtesting (per-order book event semantics).
- Custom latency models beyond the bundled `intp_order_latency`.
