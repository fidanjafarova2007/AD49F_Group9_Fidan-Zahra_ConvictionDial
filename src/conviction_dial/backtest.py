"""Causal month-end momentum backtest, without transaction cost assumptions in v0.1."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    daily_returns: pd.DataFrame
    equity_curve: pd.DataFrame
    signals: pd.DataFrame
    allocations: pd.DataFrame
    trades: pd.DataFrame
    first_execution: pd.Timestamp


def month_ends(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Last observed trading day of each calendar month."""
    return index.to_series().groupby(index.to_period("M")).last().to_numpy(dtype="datetime64[ns]")


def build_signals(prices: pd.DataFrame, config: dict) -> pd.DataFrame:
    spy, bond = config["market_proxy"], config["bond_proxy"]
    ma = prices[spy].rolling(config["trend_ma_days"], min_periods=config["trend_ma_days"]).mean()
    momentum = prices[config["equity_universe"]].pct_change(periods=config["lookback_momentum_days"], fill_method=None)
    recent = prices[config["equity_universe"]].notna().rolling(5, min_periods=5).sum().eq(5)
    results = []
    for signal_date in pd.to_datetime(month_ends(prices.index)):
        idx = int(prices.index.get_loc(signal_date))
        if idx + 1 >= len(prices) or pd.isna(ma.loc[signal_date]):
            continue
        execution_date = prices.index[idx + 1]
        risk_on = bool(prices.at[signal_date, spy] > ma.loc[signal_date])
        valid = momentum.loc[signal_date].where(recent.loc[signal_date]).dropna().sort_values(ascending=False)
        if risk_on:
            if len(valid) < config["top_n_assets"]:
                raise ValueError(f"Only {len(valid)} eligible ETFs on {signal_date.date()}")
            selected = valid.index[:config["top_n_assets"]].tolist()
            targets = {symbol: 1 / config["top_n_assets"] for symbol in selected}
        else:
            selected, targets = [], {bond: 1.0}
        results.append({
            "signal_date": signal_date, "execution_date": execution_date,
            "regime": "Risk-on" if risk_on else "Risk-off",
            "spy_close": float(prices.at[signal_date, spy]), "sma_200": float(ma.loc[signal_date]),
            "top_picks": ", ".join(selected), "strategy_targets": targets,
            "trend_targets": {spy: 1.0} if risk_on else {bond: 1.0},
            "top_momentum": ", ".join(f"{k}: {valid[k]:+.2%}" for k in selected),
        })
    if not results:
        raise ValueError("No executable monthly signals; check dates and data")
    return pd.DataFrame(results)


def _replay(prices: pd.DataFrame, orders: dict, first_execution: pd.Timestamp) -> tuple[pd.Series, pd.DataFrame]:
    held, daily, all_trades = {}, {}, []
    first_pos = int(prices.index.get_loc(first_execution))
    for i in range(first_pos, len(prices.index)):
        day, r = prices.index[i], 0.0
        if held and i > first_pos:
            asset_ret = {}
            for symbol in held:
                p0, p1 = prices.iloc[i - 1][symbol], prices.iloc[i][symbol]
                if not (np.isfinite(p0) and np.isfinite(p1) and p0 > 0 and p1 > 0):
                    raise ValueError(f"Missing price for held asset {symbol} on {day.date()}; do not assume zero return")
                asset_ret[symbol] = float(p1 / p0 - 1.0)
            r = float(sum(w * asset_ret[s] for s, w in held.items()))
            if 1 + r <= 0:
                raise ValueError("Portfolio lost 100%+ in a day")
            held = {s: (w * (1 + asset_ret[s])) / (1 + r) for s, w in held.items()}
        daily[day] = r
        if day in orders:
            target = orders[day]
            if not np.isclose(sum(target.values()), 1.0):
                raise ValueError(f"Target weights on {day.date()} do not add to one")
            prev = held
            turnover = .5 * sum(abs(target.get(s, 0.0) - prev.get(s, 0.0)) for s in set(target) | set(prev))
            if not prev:
                turnover = 1.0
            all_trades.append({"execution_date": day, "turnover_one_way": turnover})
            held = target.copy()
    return pd.Series(daily, name="daily_return"), pd.DataFrame(all_trades)


def backtest(prices: pd.DataFrame, config: dict) -> BacktestResult:
    if config["trading_cost_bps"] != 0:
        raise ValueError("Milestone 2 is deliberately a gross-of-costs prototype. Add costs only in Milestone 3")
    if config["risk_free_rate_annual"] != 0:
        raise ValueError("This baseline defines the Sharpe ratio using an explicitly zero risk-free return")
    signals = build_signals(prices, config)
    first_execution = signals.iloc[0]["execution_date"]
    spy, bond = config["market_proxy"], config["bond_proxy"]
    strategies = {
        "Conviction Dial": {row.execution_date: row.strategy_targets for row in signals.itertuples()},
        "SPY buy-and-hold": {first_execution: {spy: 1.0}},
        "60/40 SPY/AGG": {row.execution_date: {spy: .6, bond: .4} for row in signals.itertuples()},
        "200-day trend filter": {row.execution_date: row.trend_targets for row in signals.itertuples()},
    }
    frames, trades = [], []
    for name, orders in strategies.items():
        r, ledger = _replay(prices, orders, first_execution)
        frames.append(r.rename(name))
        ledger.insert(0, "portfolio", name)
        trades.append(ledger)
    returns = pd.concat(frames, axis=1)
    equity = (1.0 + returns).cumprod()
    if not (np.isfinite(equity.to_numpy()).all() and (equity.to_numpy() > 0).all()):
        raise ValueError("Invalid equity curve")
    allocations = pd.DataFrame([
        {"signal_date": row.signal_date, "execution_date": row.execution_date, "regime": row.regime,
         "ticker": ticker, "target_weight": weight}
        for row in signals.itertuples() for ticker, weight in row.strategy_targets.items()
    ])
    return BacktestResult(returns, equity, signals, allocations, pd.concat(trades, ignore_index=True), first_execution)


def performance_metrics(daily_returns: pd.Series) -> dict:
    r = daily_returns.dropna().astype(float)
    n = len(r)
    if n < 2:
        return {"trading_days": n, "total_return_pct": np.nan, "cagr_pct": np.nan,
                "volatility_pct": np.nan, "sharpe_rf0": np.nan, "max_drawdown_pct": np.nan}
    curve = (1 + r).cumprod()
    total, vol_daily = float(curve.iloc[-1]), float(r.std(ddof=1))
    with_inception = pd.concat([pd.Series([1.0]), curve.reset_index(drop=True)], ignore_index=True)
    max_dd = float((with_inception / with_inception.cummax() - 1).min())
    return {
        "trading_days": n, "total_return_pct": 100 * (total - 1),
        "cagr_pct": 100 * (total ** (252 / n) - 1),
        "volatility_pct": 100 * vol_daily * np.sqrt(252),
        "sharpe_rf0": (float(r.mean()) / vol_daily * np.sqrt(252)) if vol_daily > 1e-14 else np.nan,
        "max_drawdown_pct": 100 * max_dd,
    }


def metrics_table(result: BacktestResult, config: dict) -> pd.DataFrame:
    r = result.daily_returns.loc[result.daily_returns.index > result.first_execution]
    split = pd.Timestamp(config["out_of_sample_start"])
    records = []
    for label, dataset in (("Full history", r), ("In sample", r.loc[r.index < split]),
                           ("Out of sample", r.loc[r.index >= split])):
        for name in dataset.columns:
            records.append({"window": label, "portfolio": name, **performance_metrics(dataset[name])})
    return pd.DataFrame(records)
