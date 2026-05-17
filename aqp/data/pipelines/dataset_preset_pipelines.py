"""Ingestion pipelines for the dataset presets in
:mod:`aqp.data.dataset_presets`.

Each function:
- Fetches data from the relevant source.
- Normalizes to AQP's bar schema (``vt_symbol``, ``timestamp``, OHLCV).
- Writes to the configured Iceberg table via :func:`append_arrow`.
- Returns a small dict summary (rows written, namespace.table, etc.).

Network-bound preset pipelines (akshare, kucoin, yfinance, fred,
finviz) gracefully degrade when the dependency or API key is missing
and emit an explanatory dict.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from aqp.data.dataset_presets import get_preset

logger = logging.getLogger(__name__)


def _to_arrow(df: pd.DataFrame):
    import pyarrow as pa
    return pa.Table.from_pandas(df, preserve_index=False)


def _write_to_iceberg(identifier: str, df: pd.DataFrame) -> dict[str, Any]:
    if df is None or df.empty:
        return {"rows": 0, "iceberg_identifier": identifier, "status": "no_data"}
    try:
        from aqp.data.iceberg_catalog import append_arrow
        tbl = _to_arrow(df)
        append_arrow(identifier, tbl, create_if_missing=True)
        return {"rows": int(len(df)), "iceberg_identifier": identifier, "status": "ok"}
    except Exception as exc:  # noqa: BLE001
        logger.exception("iceberg write failed for %s", identifier)
        return {"rows": int(len(df)), "iceberg_identifier": identifier, "status": "iceberg_error", "error": str(exc)}


_DATE_COL_CANDIDATES: tuple[str, ...] = (
    "timestamp",
    "date",
    "datetime",
    "datadate",
    "trade_date",
    "as_of_date",
    "effective_date",
)
_SYMBOL_COL_CANDIDATES: tuple[str, ...] = (
    "vt_symbol",
    "symbol",
    "ticker",
    "tic",
    "asset",
    "constituent",
)


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().lower().replace(" ", "_") for c in out.columns]
    return out


def _coerce_timestamp_column(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in _DATE_COL_CANDIDATES:
        if col not in out.columns:
            continue
        ts = pd.to_datetime(out[col], errors="coerce")
        if ts.notna().any():
            out["timestamp"] = ts
            return out
    return out


def _ensure_vt_symbol_column(df: pd.DataFrame, *, default_exchange: str = "NYSE") -> pd.DataFrame:
    out = df.copy()
    if "vt_symbol" in out.columns:
        out["vt_symbol"] = out["vt_symbol"].map(
            lambda v: str(v).strip().upper() if pd.notna(v) else None
        )
        return out
    for col in _SYMBOL_COL_CANDIDATES:
        if col not in out.columns:
            continue
        raw = out[col].map(lambda v: str(v).strip().upper() if pd.notna(v) else None)

        def _to_vt(token: str | None) -> str | None:
            if not token:
                return None
            return token if "." in token else f"{token}.{default_exchange}"

        out["vt_symbol"] = raw.map(_to_vt)
        return out
    return out


def _coerce_numeric_columns(df: pd.DataFrame, *, skip: set[str] | None = None) -> pd.DataFrame:
    out = df.copy()
    skip_cols = skip or set()
    for col in out.columns:
        if col in skip_cols:
            continue
        if pd.api.types.is_numeric_dtype(out[col]):
            continue
        converted = pd.to_numeric(out[col], errors="coerce")
        if converted.notna().mean() >= 0.8:
            out[col] = converted
    return out


def _clean_tabular_frame(df: pd.DataFrame, *, default_exchange: str = "NYSE") -> pd.DataFrame:
    out = _normalize_columns(df)
    out = out.drop_duplicates().reset_index(drop=True)
    out = out.dropna(axis=1, how="all")
    for col in out.columns:
        if pd.api.types.is_object_dtype(out[col]):
            out[col] = out[col].map(lambda v: v.strip() if isinstance(v, str) else v)
    out = _coerce_timestamp_column(out)
    out = _ensure_vt_symbol_column(out, default_exchange=default_exchange)
    out = _coerce_numeric_columns(out, skip={"timestamp", "vt_symbol"})
    return out


def _wide_numeric_to_bar_like(df: pd.DataFrame) -> pd.DataFrame:
    if "timestamp" not in df.columns or "vt_symbol" in df.columns:
        return df
    numeric_cols = [
        c
        for c in df.columns
        if c != "timestamp" and pd.api.types.is_numeric_dtype(df[c])
    ]
    if len(numeric_cols) < 2:
        return df
    melted = (
        df[["timestamp", *numeric_cols]]
        .melt(
            id_vars=["timestamp"],
            value_vars=numeric_cols,
            var_name="vt_symbol",
            value_name="close",
        )
        .dropna(subset=["close"])
    )
    melted["vt_symbol"] = melted["vt_symbol"].map(
        lambda v: str(v).strip().upper() if "." in str(v) else f"{str(v).strip().upper()}.GEN"
    )
    melted["open"] = melted["close"]
    melted["high"] = melted["close"]
    melted["low"] = melted["close"]
    melted["volume"] = 0.0
    return melted[["vt_symbol", "timestamp", "open", "high", "low", "close", "volume"]]


# ---------------------------------------------------------------------------
# ETF intraday panel (Gao 2018)
# ---------------------------------------------------------------------------


def ingest_etf_intraday_panel(symbols: list[str] | None = None, days: int = 60) -> dict[str, Any]:
    preset = get_preset("intraday_momentum_etf")
    syms = symbols or preset.default_symbols
    try:
        import yfinance as yf
    except ImportError:
        return {"status": "missing_dependency", "package": "yfinance"}
    end = datetime.utcnow()
    start = end - timedelta(days=min(days, 60))  # yfinance intraday cap
    rows = []
    for vt in syms:
        ticker = vt.split(".")[0]
        try:
            df = yf.download(ticker, start=start, end=end, interval="30m", progress=False, auto_adjust=False)
        except Exception:  # noqa: BLE001
            logger.exception("yfinance fetch failed for %s", ticker)
            continue
        if df is None or df.empty:
            continue
        df = df.reset_index()
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df["vt_symbol"] = vt
        df = df.rename(columns={"Datetime": "timestamp", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        rows.append(df[["vt_symbol", "timestamp", "open", "high", "low", "close", "volume"]])
    if not rows:
        return {"status": "no_data", "iceberg_identifier": preset.iceberg_identifier}
    out = pd.concat(rows, ignore_index=True)
    return _write_to_iceberg(preset.iceberg_identifier, out)


# ---------------------------------------------------------------------------
# Commodity futures panel (sample CSV)
# ---------------------------------------------------------------------------


def ingest_commodity_futures_panel(csv_path: str | None = None) -> dict[str, Any]:
    preset = get_preset("commodity_futures_panel")
    if csv_path is None:
        return {
            "status": "missing_input",
            "message": "Pass csv_path or wire a continuous-futures provider; sample data not bundled here.",
            "iceberg_identifier": preset.iceberg_identifier,
        }
    df = pd.read_csv(csv_path)
    if "vt_symbol" not in df.columns or "timestamp" not in df.columns:
        return {"status": "schema_error", "expected": ["vt_symbol", "timestamp", "open", "high", "low", "close", "volume"]}
    return _write_to_iceberg(preset.iceberg_identifier, df)


# ---------------------------------------------------------------------------
# China A-shares panel (akshare)
# ---------------------------------------------------------------------------


def ingest_akshare_china_panel(symbols: list[str] | None = None) -> dict[str, Any]:
    preset = get_preset("china_a_shares_top200")
    try:
        import akshare as ak
    except ImportError:
        return {"status": "missing_dependency", "package": "akshare"}
    syms = symbols or []
    if not syms:
        try:
            spot = ak.stock_zh_a_spot()
            if spot is not None and not spot.empty:
                spot_sorted = spot.sort_values("总市值", ascending=False) if "总市值" in spot.columns else spot
                syms = [f"{c}.SHE" if c.startswith("0") or c.startswith("3") else f"{c}.SSE" for c in spot_sorted["代码"].head(50).tolist()]
        except Exception:  # noqa: BLE001
            logger.exception("akshare top symbols fetch failed")
            return {"status": "akshare_fetch_error"}
    rows: list[pd.DataFrame] = []
    for vt in syms:
        ticker = vt.split(".")[0]
        try:
            df = ak.stock_zh_a_hist(symbol=ticker, period="daily", adjust="qfq")
        except Exception:  # noqa: BLE001
            continue
        if df is None or df.empty:
            continue
        df = df.rename(columns={"日期": "timestamp", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量": "volume"})
        df["vt_symbol"] = vt
        rows.append(df[["vt_symbol", "timestamp", "open", "high", "low", "close", "volume"]])
    if not rows:
        return {"status": "no_data", "iceberg_identifier": preset.iceberg_identifier}
    return _write_to_iceberg(preset.iceberg_identifier, pd.concat(rows, ignore_index=True))


# ---------------------------------------------------------------------------
# Crypto majors intraday (KuCoin)
# ---------------------------------------------------------------------------


def ingest_crypto_kucoin_intraday(symbols: list[str] | None = None) -> dict[str, Any]:
    preset = get_preset("crypto_majors_intraday")
    try:
        from kucoin.client import Market
    except ImportError:
        return {"status": "missing_dependency", "package": "python-kucoin"}
    client = Market()
    syms = symbols or preset.default_symbols
    rows: list[pd.DataFrame] = []
    for vt in syms:
        ticker = vt.split(".")[0] + "-USDT"
        try:
            klines = client.get_kline(ticker, "5min")
        except Exception:  # noqa: BLE001
            continue
        if not klines:
            continue
        df = pd.DataFrame(klines, columns=["timestamp", "open", "close", "high", "low", "volume", "amount"])
        df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit="s")
        df["vt_symbol"] = vt
        for col in ("open", "close", "high", "low", "volume"):
            df[col] = df[col].astype(float)
        rows.append(df[["vt_symbol", "timestamp", "open", "high", "low", "close", "volume"]])
    if not rows:
        return {"status": "no_data", "iceberg_identifier": preset.iceberg_identifier}
    return _write_to_iceberg(preset.iceberg_identifier, pd.concat(rows, ignore_index=True))


# ---------------------------------------------------------------------------
# S&P 500 daily (yfinance)
# ---------------------------------------------------------------------------


def ingest_sp500_daily(symbols: list[str] | None = None, start: str = "2020-01-01") -> dict[str, Any]:
    preset = get_preset("equity_universe_sp500_daily")
    try:
        import yfinance as yf
    except ImportError:
        return {"status": "missing_dependency", "package": "yfinance"}
    syms = symbols or ["SPY.NASDAQ"]  # caller can pass a real S&P list
    rows: list[pd.DataFrame] = []
    end = datetime.utcnow()
    for vt in syms:
        ticker = vt.split(".")[0]
        try:
            df = yf.download(ticker, start=start, end=end, interval="1d", progress=False, auto_adjust=False)
        except Exception:  # noqa: BLE001
            continue
        if df is None or df.empty:
            continue
        df = df.reset_index()
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df["vt_symbol"] = vt
        df = df.rename(columns={"Date": "timestamp", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        rows.append(df[["vt_symbol", "timestamp", "open", "high", "low", "close", "volume"]])
    if not rows:
        return {"status": "no_data", "iceberg_identifier": preset.iceberg_identifier}
    return _write_to_iceberg(preset.iceberg_identifier, pd.concat(rows, ignore_index=True))


# ---------------------------------------------------------------------------
# FRED macro basket
# ---------------------------------------------------------------------------


def ingest_fred_macro_basket(api_key: str | None = None) -> dict[str, Any]:
    preset = get_preset("fred_macro_basket")
    try:
        from fredapi import Fred
    except ImportError:
        return {"status": "missing_dependency", "package": "fredapi"}
    import os
    key = api_key or os.environ.get("AQP_FRED_API_KEY")
    if not key:
        return {"status": "missing_api_key", "env_var": "AQP_FRED_API_KEY"}
    fred = Fred(api_key=key)
    series_codes = {
        "UNRATE.FRED": "UNRATE",
        "CPIAUCSL.FRED": "CPIAUCSL",
        "PMSPCE.FRED": "PMSPCE",
        "DGS10.FRED": "DGS10",
        "VIXCLS.FRED": "VIXCLS",
    }
    rows: list[pd.DataFrame] = []
    for vt, code in series_codes.items():
        try:
            s = fred.get_series(code)
        except Exception:  # noqa: BLE001
            continue
        df = s.reset_index()
        df.columns = ["timestamp", "close"]
        df["vt_symbol"] = vt
        df["open"] = df["close"]
        df["high"] = df["close"]
        df["low"] = df["close"]
        df["volume"] = 0.0
        rows.append(df[["vt_symbol", "timestamp", "open", "high", "low", "close", "volume"]])
    if not rows:
        return {"status": "no_data", "iceberg_identifier": preset.iceberg_identifier}
    return _write_to_iceberg(preset.iceberg_identifier, pd.concat(rows, ignore_index=True))


# ---------------------------------------------------------------------------
# EOD options sample
# ---------------------------------------------------------------------------


def ingest_eod_options_sample(csv_path: str | None = None) -> dict[str, Any]:
    preset = get_preset("eod_options_chain_sample")
    if csv_path is None:
        return {
            "status": "missing_input",
            "message": "Pass csv_path; small SPY chain sample not bundled here.",
            "iceberg_identifier": preset.iceberg_identifier,
        }
    df = pd.read_csv(csv_path)
    return _write_to_iceberg(preset.iceberg_identifier, df)


# ---------------------------------------------------------------------------
# Finviz screener
# ---------------------------------------------------------------------------


def ingest_finviz_screener(screener_url: str = "https://finviz.com/screener.ashx?v=111") -> dict[str, Any]:
    preset = get_preset("finviz_screener")
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return {"status": "missing_dependency", "package": "requests + beautifulsoup4"}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AQPBot/1.0)"}
    try:
        resp = requests.get(screener_url, headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return {"status": "http_error", "error": str(exc)}
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", attrs={"class": "screener_table"}) or soup.find("table", attrs={"class": "table-light"})
    if table is None:
        return {"status": "parse_error", "message": "No screener table found"}
    rows: list[dict[str, Any]] = []
    headers_row = [th.get_text(strip=True) for th in table.find_all("th")]
    for tr in table.find_all("tr")[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if not cells:
            continue
        rows.append(dict(zip(headers_row, cells, strict=False)))
    if not rows:
        return {"status": "no_rows"}
    df = pd.DataFrame(rows)
    df["snapshot_at"] = pd.Timestamp.utcnow()
    return _write_to_iceberg(preset.iceberg_identifier, df)


# ---------------------------------------------------------------------------
# FinRL / Quant-Trading local CSV samples
# ---------------------------------------------------------------------------


def ingest_finrl_fundamentals_panel_sample(csv_path: str | None = None) -> dict[str, Any]:
    preset = get_preset("finrl_fundamentals_panel_sample")
    if csv_path is None:
        return {
            "status": "missing_input",
            "message": "Pass csv_path to a FinRL-style fundamentals panel CSV.",
            "iceberg_identifier": preset.iceberg_identifier,
        }
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:  # noqa: BLE001
        return {"status": "read_error", "error": str(exc), "iceberg_identifier": preset.iceberg_identifier}
    clean = _clean_tabular_frame(df, default_exchange="NYSE")
    if "trade_return" in clean.columns and "y_return" not in clean.columns:
        clean = clean.rename(columns={"trade_return": "y_return"})
    if "y_return" in clean.columns:
        clean["y_return"] = pd.to_numeric(clean["y_return"], errors="coerce")
    if "timestamp" not in clean.columns or "vt_symbol" not in clean.columns:
        return {
            "status": "schema_error",
            "expected_any_of_date_columns": list(_DATE_COL_CANDIDATES),
            "expected_any_of_symbol_columns": list(_SYMBOL_COL_CANDIDATES),
            "iceberg_identifier": preset.iceberg_identifier,
        }
    clean = clean.dropna(subset=["timestamp", "vt_symbol"])
    clean = clean.drop_duplicates(subset=["timestamp", "vt_symbol"])
    return _write_to_iceberg(preset.iceberg_identifier, clean)


def ingest_finrl_sp500_membership_pit_sample(csv_path: str | None = None) -> dict[str, Any]:
    preset = get_preset("finrl_sp500_membership_pit_sample")
    if csv_path is None:
        return {
            "status": "missing_input",
            "message": "Pass csv_path to a point-in-time membership CSV.",
            "iceberg_identifier": preset.iceberg_identifier,
        }
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:  # noqa: BLE001
        return {"status": "read_error", "error": str(exc), "iceberg_identifier": preset.iceberg_identifier}
    clean = _clean_tabular_frame(df, default_exchange="NYSE")

    if "vt_symbol" not in clean.columns:
        members_col = next(
            (c for c in ("members", "constituents", "tickers", "symbols") if c in clean.columns),
            None,
        )
        if members_col:
            clean[members_col] = clean[members_col].fillna("").astype(str)
            clean = clean.assign(**{members_col: clean[members_col].str.split(",")})
            clean = clean.explode(members_col)
            clean[members_col] = clean[members_col].map(
                lambda v: v.strip() if isinstance(v, str) else v
            )
            clean = clean[clean[members_col].notna() & (clean[members_col] != "")]
            clean = clean.rename(columns={members_col: "symbol"})
            clean = _ensure_vt_symbol_column(clean, default_exchange="NYSE")

    if "timestamp" not in clean.columns or "vt_symbol" not in clean.columns:
        return {
            "status": "schema_error",
            "message": "membership dataset must include date + symbol information",
            "iceberg_identifier": preset.iceberg_identifier,
        }
    if "is_member" not in clean.columns:
        clean["is_member"] = 1
    clean = clean.dropna(subset=["timestamp", "vt_symbol"])
    clean = clean.drop_duplicates(subset=["timestamp", "vt_symbol"])
    return _write_to_iceberg(preset.iceberg_identifier, clean)


def ingest_quant_oil_money_sample(csv_path: str | None = None) -> dict[str, Any]:
    preset = get_preset("quant_trading_oil_money_sample")
    if csv_path is None:
        return {
            "status": "missing_input",
            "message": "Pass csv_path to an Oil Money sample CSV.",
            "iceberg_identifier": preset.iceberg_identifier,
        }
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:  # noqa: BLE001
        return {"status": "read_error", "error": str(exc), "iceberg_identifier": preset.iceberg_identifier}
    clean = _clean_tabular_frame(df, default_exchange="GEN")
    if "timestamp" not in clean.columns:
        return {
            "status": "schema_error",
            "message": "oil-money sample needs a date/timestamp column",
            "iceberg_identifier": preset.iceberg_identifier,
        }
    if "vt_symbol" not in clean.columns:
        clean = _wide_numeric_to_bar_like(clean)
    if "vt_symbol" not in clean.columns:
        return {
            "status": "schema_error",
            "message": "oil-money sample needs symbol columns or vt_symbol",
            "iceberg_identifier": preset.iceberg_identifier,
        }
    if "close" not in clean.columns:
        numeric_cols = [c for c in clean.columns if c not in {"timestamp", "vt_symbol"} and pd.api.types.is_numeric_dtype(clean[c])]
        if not numeric_cols:
            return {
                "status": "schema_error",
                "message": "oil-money sample needs at least one numeric price-like column",
                "iceberg_identifier": preset.iceberg_identifier,
            }
        clean["close"] = clean[numeric_cols[0]]
    for col in ("open", "high", "low"):
        if col not in clean.columns:
            clean[col] = clean["close"]
    if "volume" not in clean.columns:
        clean["volume"] = 0.0
    clean = clean[["vt_symbol", "timestamp", "open", "high", "low", "close", "volume"]]
    clean = clean.dropna(subset=["vt_symbol", "timestamp", "close"])
    return _write_to_iceberg(preset.iceberg_identifier, clean)


def ingest_quant_smart_farmers_cleaned_sample(csv_path: str | None = None) -> dict[str, Any]:
    preset = get_preset("quant_trading_smart_farmers_cleaned_sample")
    if csv_path is None:
        return {
            "status": "missing_input",
            "message": "Pass csv_path to a Smart Farmers sample CSV.",
            "iceberg_identifier": preset.iceberg_identifier,
        }
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:  # noqa: BLE001
        return {"status": "read_error", "error": str(exc), "iceberg_identifier": preset.iceberg_identifier}
    clean = _clean_tabular_frame(df, default_exchange="GEN")
    numeric_cols = list(clean.select_dtypes(include=["number"]).columns)
    for col in numeric_cols:
        if clean[col].isna().any():
            clean[col] = clean[col].fillna(clean[col].median())
    return _write_to_iceberg(preset.iceberg_identifier, clean)


# ---------------------------------------------------------------------------
# LOB sample loader
# ---------------------------------------------------------------------------


def ingest_lob_sample(gz_path: str | None = None) -> dict[str, Any]:
    preset = get_preset("lob_btcusdt_sample")
    if gz_path is None:
        return {
            "status": "missing_input",
            "message": "Pass gz_path to a Binance Futures depth dump (e.g. inspiration/hftbacktest-master/examples/usdm/btcusdt_*.gz).",
            "iceberg_identifier": preset.iceberg_identifier,
        }
    import gzip
    import json as _json
    rows: list[dict[str, Any]] = []
    try:
        with gzip.open(gz_path, "rt") as f:
            for line in f:
                try:
                    rec = _json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                rows.append({
                    "vt_symbol": "BTCUSDT.BINANCE",
                    "timestamp": rec.get("E") or rec.get("T"),
                    "best_bid": float((rec.get("b") or [[None, None]])[0][0]) if rec.get("b") else None,
                    "best_ask": float((rec.get("a") or [[None, None]])[0][0]) if rec.get("a") else None,
                    "bid_qty": float((rec.get("b") or [[None, None]])[0][1]) if rec.get("b") else None,
                    "ask_qty": float((rec.get("a") or [[None, None]])[0][1]) if rec.get("a") else None,
                })
    except Exception as exc:  # noqa: BLE001
        logger.exception("LOB gz parse failed")
        return {"status": "parse_error", "error": str(exc)}
    if not rows:
        return {"status": "no_rows"}
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", errors="coerce")
    return _write_to_iceberg(preset.iceberg_identifier, df)


__all__ = [
    "ingest_akshare_china_panel",
    "ingest_commodity_futures_panel",
    "ingest_crypto_kucoin_intraday",
    "ingest_eod_options_sample",
    "ingest_etf_intraday_panel",
    "ingest_finrl_fundamentals_panel_sample",
    "ingest_finrl_sp500_membership_pit_sample",
    "ingest_finviz_screener",
    "ingest_fred_macro_basket",
    "ingest_lob_sample",
    "ingest_quant_oil_money_sample",
    "ingest_quant_smart_farmers_cleaned_sample",
    "ingest_sp500_daily",
]
