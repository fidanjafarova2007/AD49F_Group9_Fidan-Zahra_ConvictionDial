"""Provider ingestion, frozen source files, and transparent data-quality checks."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

ET = ZoneInfo("America/New_York")
HOSTS = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")


def symbols(config: dict) -> list[str]:
    values = list(dict.fromkeys(config["equity_universe"] + [config["market_proxy"], config["bond_proxy"]]))
    assert len(config["equity_universe"]) >= config["top_n_assets"]
    return values


def _to_epoch(d: str) -> int:
    return int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp())


def parse_yahoo_chart(payload: dict, symbol: str) -> pd.Series:
    """Fail closed if Yahoo does not send a dividend/split-adjusted price series."""
    try:
        root = payload["chart"]
        if root.get("error"):
            raise ValueError(str(root["error"]))
        item = root["result"][0]
        timestamps = item["timestamp"]
        adjusted = item["indicators"]["adjclose"][0]["adjclose"]
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError(f"{symbol}: missing *adjusted* closes in Yahoo response") from exc
    if len(timestamps) != len(adjusted):
        raise ValueError(f"{symbol}: mismatched daily data")
    dates = [datetime.fromtimestamp(ts, timezone.utc).astimezone(ET).date() for ts in timestamps]
    result = pd.Series(adjusted, index=pd.to_datetime(dates), name=symbol, dtype="float64").sort_index()
    if result.index.has_duplicates:
        raise ValueError(f"{symbol}: duplicate price dates")
    if (result.dropna() <= 0).any() or result.dropna().empty:
        raise ValueError(f"{symbol}: invalid or missing adjusted prices")
    return result.dropna()


def download_symbol(symbol: str, start: str, end: str, session: requests.Session | None = None) -> pd.Series:
    client = session or requests.Session()
    params = {"period1": _to_epoch(start), "period2": _to_epoch(end), "interval": "1d", "events": "div,splits"}
    last_error = None
    for attempt in range(4):
        for host in HOSTS:
            try:
                response = client.get(
                    f"{host}/v8/finance/chart/{symbol}", params=params,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; student-research/1.0)", "Accept": "application/json"},
                    timeout=35,
                )
                response.raise_for_status()
                series = parse_yahoo_chart(response.json(), symbol)
                series = series.loc[(series.index >= pd.Timestamp(start)) & (series.index < pd.Timestamp(end))]
                if len(series) < 200:
                    raise ValueError(f"{symbol}: only {len(series)} observations; at least 200 required")
                return series
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
        if attempt < 3:
            time.sleep(2 ** attempt)
    raise RuntimeError(
        f"Could not download {symbol} from Yahoo after retries: {last_error}. "
        "Retry later, or use an already-saved data/processed/adjusted_close.csv snapshot. "
        "Never replace missing market prices with invented numbers."
    )


def validate_prices(prices: pd.DataFrame, config: dict) -> dict:
    """Do not backfill pre-inception ETFs or silently forward-fill missing quotes."""
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("Price index must contain real dates")
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("Dates must be unique and sorted")
    required = symbols(config)
    missing_symbols = sorted(set(required).difference(prices.columns))
    if missing_symbols:
        raise ValueError(f"Missing instruments: {missing_symbols}")
    if (prices[required].dropna(how="all") <= 0).any().any():
        raise ValueError("All available prices must be strictly positive")
    if len(prices) < config["trend_ma_days"] + 2:
        raise ValueError("Insufficient warmup for the moving average")
    for col in [config["market_proxy"], config["bond_proxy"]]:
        if prices[col].isna().any():
            raise ValueError(f"{col} has missing daily observations on the SPY calendar")
    if prices.index.max() >= pd.Timestamp(config["data_end_exclusive"]):
        raise ValueError("Data contain dates beyond configured exclusive end")
    quality = {}
    for s in required:
        col = prices[s]
        valid = col.dropna()
        if valid.empty:
            raise ValueError(f"No observations for {s}")
        within_life = col.loc[valid.index[0]:valid.index[-1]]
        daily = valid.pct_change(fill_method=None).dropna()
        quality[s] = {
            "first_date": str(valid.index.min().date()),
            "last_date": str(valid.index.max().date()),
            "observations": int(valid.size),
            "missing_sessions_during_observed_life": int(within_life.isna().sum()),
            "large_one_day_adjusted_returns_over_60pct": int((daily.abs() > .6).sum()),
        }
    return quality


def download_dataset(config: dict, root: Path) -> pd.DataFrame:
    raw = root / "data" / "raw"
    processed = root / "data" / "processed"
    raw.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    series, metadata = {}, {}
    for symbol in symbols(config):
        print(f"Fetching {symbol} from Yahoo Finance (adjusted daily closes)...", flush=True)
        s = download_symbol(symbol, config["data_start"], config["data_end_exclusive"], session=session)
        csv_path = raw / f"{symbol}.csv"
        s.to_frame(name="adjusted_close").to_csv(csv_path, index_label="date", float_format="%.10f")
        metadata[symbol] = {"file": str(csv_path.relative_to(root)), "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest()}
        series[symbol] = s
    spy = config["market_proxy"]
    index = series[spy].index
    prices = pd.DataFrame({s: values.reindex(index) for s, values in series.items()}, index=index)
    quality = validate_prices(prices, config)
    price_path = processed / "adjusted_close.csv"
    prices.to_csv(price_path, index_label="date", float_format="%.10f")
    manifest = {
        "provider": "Yahoo Finance public chart endpoint; daily adjusted close (split/dividend adjusted)",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_start_inclusive": config["data_start"],
        "requested_end_exclusive": config["data_end_exclusive"],
        "observed_end": str(prices.index.max().date()),
        "calendar": f"{spy} exchange sessions, America/New_York",
        "symbols": symbols(config),
        "data_sha256": hashlib.sha256(price_path.read_bytes()).hexdigest(),
        "raw_files": metadata,
        "quality": quality,
        "known_limits": [
            "Yahoo may revise historic adjusted closes after new corporate actions or corrections.",
            "ETF selection is a fixed present-day universe (survivorship/selection bias).",
            "No missing price is backfilled before an ETF's inception.",
        ],
    }
    (processed / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {price_path} ({len(prices)} sessions; through {prices.index.max().date()}).")
    return prices


def load_dataset(config: dict, root: Path) -> tuple[pd.DataFrame, dict]:
    path = root / "data" / "processed" / "adjusted_close.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}; run 'python -m conviction_dial.cli fetch' first")
    prices = pd.read_csv(path, index_col="date", parse_dates=["date"])
    prices.index.name = "date"
    manifest_path = root / "data" / "processed" / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing {manifest_path}; download the complete snapshot, not just the CSV")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["data_sha256"]:
        raise ValueError("Data CSV hash differs from the download manifest")
    validate_prices(prices, config)
    if manifest.get("requested_start_inclusive") != config["data_start"] or manifest.get("requested_end_exclusive") != config["data_end_exclusive"]:
        raise ValueError("Stored snapshot window differs from config; rerun fetch")
    return prices, manifest
