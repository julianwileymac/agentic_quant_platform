# Installation

This page documents the install-time requirements for AQP and its
optional extras. The base install is pure Python and runs on
Linux / macOS / Windows. Two extras ship with native build steps that
need attention:

| Extra | Native build | Notes |
| --- | --- | --- |
| `optimal-control` | None (pure Python) | Ships the JAX HJB / Lucic-Tse stack. CPU-only by default. |
| `hft` | Rust + Maturin | Ships the [hftbacktest](https://github.com/nkaz001/hftbacktest) LOB engine. |

## Base install

```bash
pip install -e .
```

That gives the FastAPI app, Celery worker, default config, agents,
analysis flows, and the in-memory backtest fallbacks. No GPU, no native
toolchains.

## `[optimal-control]` — JAX + HJB + Lucic-Tse

```bash
pip install -e ".[optimal-control]"
```

This pulls:

- `jax>=0.4.30` and `jaxlib>=0.4.30` (CPU build, manylinux / win / macOS
  wheels available on PyPI).
- `finhjb>=0.1.6` — JAX HJB solver framework.
- `fast-vollib>=0.1.4` — vectorised IV + Greeks (auto-detects the JAX
  backend; falls back to NumPy when JAX is missing).
- `mbt-gym` — pulled directly from
  [JJJerome/mbt_gym](https://github.com/JJJerome/mbt_gym) `main` because
  the package is not on PyPI.

### GPU / Metal acceleration (opt-in)

After installing the extra, swap the CPU `jaxlib` wheel for the CUDA or
Metal variant. JAX's docs are the canonical source; the short form:

```bash
# NVIDIA CUDA 12 (Linux only)
pip install -U "jax[cuda12_pip]" -f https://storage.googleapis.com/jax-releases/jax_cuda_releases.html

# Apple Silicon (macOS)
pip install -U "jax-metal"
```

The `aqp.optimal_control` and `aqp.options.greeks_jax` modules pick up
the accelerated backend automatically — no AQP code changes needed.

## `[hft]` — hftbacktest LOB engine

```bash
pip install -e ".[hft]"
```

This pulls `hftbacktest>=2.0.0`, `numba>=0.61`, and `polars>=1.0`.
Most `hftbacktest` releases ship as source distributions and need a Rust
toolchain plus Maturin at install time:

```bash
# 1. Install Rust + Cargo (https://rustup.rs)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# 2. Restart your shell so `cargo` is on PATH, then verify
cargo --version

# 3. Install Maturin (build backend hftbacktest uses)
pip install maturin

# 4. Now install the AQP extra
pip install -e ".[hft]"
```

On Windows the equivalent is the rustup-init.exe installer plus the
"Microsoft Visual C++ Build Tools" (MSVC linker is required by the
hftbacktest crate). On macOS Apple Silicon, the standard rustup install
works; no extra steps.

### Verifying the install

```bash
python -c "from aqp.backtest.hft import LobBacktestEngine; print('OK')"
```

If that succeeds, the engine is ready to drive any `LobStrategy`
subclass under `aqp/strategies/hft/`.

## `[full]`

`pip install -e ".[full]"` chains every optional extra including
`optimal-control` and `hft`, so it requires the Rust toolchain. Most
contributors install `[full]` minus `[hft]`:

```bash
pip install -e ".[auth,alpaca,ibkr,otel,paper,vectorbt,ml,ml-torch,ml-forecast,portfolio,fred,sec,iceberg,agents-rag,optimal-control]"
```

## See also

- [aqp_docs/optimal-control.md](optimal-control.md) — HJB primer + AvSt + CJ.
- [aqp_docs/portfolio-options-mm.md](portfolio-options-mm.md) — Lucic-Tse.
- [aqp_docs/hft-backtest.md](hft-backtest.md) — `LobBacktestEngine` walk-through.
- [aqp_docs/local-platform.md](local-platform.md) — single-machine deployment.
