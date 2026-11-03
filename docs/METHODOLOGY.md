# Milestone 2 methodology

## Strategy rules

At each completed month-end close, the strategy classifies the market using SPY relative to its 200-trading-day simple moving average. It ranks a fixed universe of 20 sector, style, size, real-estate and international ETFs by 126-session adjusted-price momentum. In a risk-on regime it equally weights the top five eligible ETFs; in risk-off it holds AGG.

Signals are calculated with data available through month-end and executed at the following trading session's close. New positions earn returns only after that execution close. The engine accrues returns using prior-close holdings and allows weights to drift naturally between rebalances.

## Benchmarks and metrics

The four portfolios are Conviction Dial, SPY buy-and-hold, monthly rebalanced 60% SPY / 40% AGG, and a trend-only filter that switches between SPY and AGG using the same 200-day regime signal.

For identical dates, the report calculates total return, CAGR, annualized volatility, Sharpe using a 0% annual risk-free rate and 252 sessions per year, and maximum drawdown. Metrics are reported for the full history, the pre-2024 in-sample period, and the chronological holdout beginning 2024-01-01.

## Controls and limitations

- The next-session execution convention is designed to avoid same-close look-ahead.
- Tests deliberately perturb future prices and verify earlier signals do not change.
- Unit tests use seeded synthetic fixtures only to test software; they are not empirical results.
- Raw and aligned price snapshots are accompanied by SHA-256 hashes and a retrieval manifest.
- The ETF universe is fixed using currently known funds, creating selection/survivorship bias.
- Yahoo Finance may revise historical adjusted closes and may rate-limit automated requests.
- Commissions, bid-ask spreads, slippage, market impact, taxes and position limits are not modeled in Milestone 2.

Milestone 3 is intended to add cost modeling and risk controls. This prototype is educational research, not financial advice or a live-trading record.
