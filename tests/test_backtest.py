import numpy as np
import pandas as pd
import pytest

from conviction_dial.backtest import backtest, build_signals, metrics_table, performance_metrics
from conviction_dial.data import validate_prices


def test_pipeline_and_four_benchmarks(fictional_prices, cfg):
    quality = validate_prices(fictional_prices, cfg)
    assert len(quality) == len(cfg["equity_universe"]) + 2
    result = backtest(fictional_prices, cfg)
    assert set(result.daily_returns.columns) == {
        "Conviction Dial", "SPY buy-and-hold", "60/40 SPY/AGG", "200-day trend filter"}
    assert result.daily_returns.index.min() == result.first_execution
    assert result.daily_returns.iloc[0].eq(0).all()
    assert (result.equity_curve > 0).all().all()
    assert np.isfinite(metrics_table(result, cfg)["cagr_pct"]).all()
    assert (result.allocations.groupby("execution_date")["target_weight"].sum().round(8) == 1.0).all()
    assert (result.signals["execution_date"] > result.signals["signal_date"]).all()
    assert len(result.signals) > 30


def test_trading_delay_no_same_day_return(fictional_prices, cfg):
    result = backtest(fictional_prices, cfg)
    first = result.first_execution
    assert result.daily_returns.loc[first].eq(0).all()
    following = fictional_prices.index[fictional_prices.index.get_loc(first) + 1]
    assert result.daily_returns.loc[following, "SPY buy-and-hold"] == pytest.approx(
        fictional_prices.loc[following, "SPY"] / fictional_prices.loc[first, "SPY"] - 1)
    selected = result.allocations[result.allocations["execution_date"] == first]
    assert result.daily_returns.loc[following, "Conviction Dial"] == pytest.approx(
        sum(float(row.target_weight) * (fictional_prices.loc[following, row.ticker] /
                                       fictional_prices.loc[first, row.ticker] - 1)
            for row in selected.itertuples()))


def test_no_future_price_lookahead(fictional_prices, cfg):
    original = build_signals(fictional_prices, cfg)
    cut = pd.Timestamp("2023-06-30")
    disturbed = fictional_prices.copy()
    # Changing ALL asset prices after this date may not alter any pre-cut signal.
    later = disturbed.index > cut
    for col in disturbed:
        disturbed.loc[later, col] *= 1.75
    rewritten = build_signals(disturbed, cfg)
    columns = ["signal_date", "execution_date", "regime", "top_picks", "spy_close", "sma_200"]
    pd.testing.assert_frame_equal(
        original.loc[original.signal_date <= cut, columns].reset_index(drop=True),
        rewritten.loc[rewritten.signal_date <= cut, columns].reset_index(drop=True))


def test_buy_and_hold_is_not_monthly_rebalanced(fictional_prices, cfg):
    result = backtest(fictional_prices, cfg)
    assert len(result.trades[result.trades.portfolio == "SPY buy-and-hold"]) == 1
    assert len(result.trades[result.trades.portfolio == "60/40 SPY/AGG"]) == len(result.signals)


def test_chronological_out_of_sample(cfg, fictional_prices):
    r = backtest(fictional_prices, cfg)
    table = metrics_table(r, cfg)
    assert len(table) == 12
    assert table[table.window == "Out of sample"]["trading_days"].min() > 200


def test_missing_held_price_raises(fictional_prices, cfg):
    result = backtest(fictional_prices, cfg)
    first_day = result.first_execution
    held = result.allocations.loc[result.allocations.execution_date == first_day, "ticker"].iloc[0]
    next_day = fictional_prices.index[fictional_prices.index.get_loc(first_day) + 1]
    faulty = fictional_prices.copy()
    faulty.loc[next_day, held] = np.nan
    with pytest.raises(ValueError, match="Missing price for held asset"):
        backtest(faulty, cfg)


def test_metric_calculations():
    r = pd.Series([.1, -.05, .02])
    m = performance_metrics(r)
    assert m["total_return_pct"] == pytest.approx((1.1 * .95 * 1.02 - 1) * 100)
    assert m["max_drawdown_pct"] == pytest.approx(-5.0)
    assert performance_metrics(pd.Series([0.0, 0.0]))["sharpe_rf0"] != performance_metrics(r)["sharpe_rf0"]


def test_reject_costs_at_milestone2(cfg, fictional_prices):
    cfg["trading_cost_bps"] = 10
    with pytest.raises(ValueError, match="Milestone 2"):
        backtest(fictional_prices, cfg)
