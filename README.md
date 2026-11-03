# Conviction Dial — Milestone 2

**AD 49F · Group 9 · Term Project**  
**Milestone due: November 3, 2026**  
**Deliverable:** reproducible data pipeline + first causally timed ETF backtest with an S&P 500 buy-and-hold benchmark.

> **Important evidence note:** The project tests use clearly synthetic fixtures, not performance claims. The GitHub Actions workflow downloads real Yahoo Finance adjusted-price data and runs the empirical backtest. Until that workflow succeeds, do not claim that a fresh empirical run has completed.

## What this implements

1. At each month's last trading close, classify the regime by whether SPY is above its 200-day SMA.
2. Rank 20 sector, style, size, real-estate and international ETFs by 126-trading-day momentum.
3. If risk-on, equally weight the top five eligible ETFs; if risk-off, hold AGG.
4. Execute trades at the following session's close, applying new weights only to subsequent returns.
5. Compare with SPY buy-and-hold, a monthly rebalanced 60% SPY / 40% AGG portfolio, and a simple SPY-or-AGG trend filter.

Prices are adjusted for splits and dividends. The pipeline saves raw ticker data, an aligned price snapshot, a SHA-256 manifest, auditable CSVs and charts. The strategy is intentionally gross of transaction costs and slippage; those are deferred to Milestone 3.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\Activate.ps1
python -m pip install -e . pytest
python -m pytest -q
python -m conviction_dial.cli all
```

## GitHub Actions reproduction

The workflow is `.github/workflows/reproduce.yml`. It runs offline unit tests, downloads real Yahoo Finance data, executes the backtest and uploads the `conviction-dial-milestone2-real-market-data` artifact. Open **Actions → Test and reproduce Milestone 2** to inspect a run and download the artifact. The artifact contains raw/processed data and generated reports/results.

Yahoo's public chart endpoint can rate-limit automated runners. If a download fails, rerun later; never substitute synthetic fixtures for empirical results.

## Scope and limitations

This is the v0.1 baseline: monthly SPY trend regime, ETF momentum ranking and risk-on/risk-off allocation. VIX regimes, fundamentals, K-means, factor scoring, transaction costs, slippage and position limits are not implemented in this milestone. The fixed present-day ETF universe introduces selection/survivorship bias, and Yahoo may revise adjusted histories. The chronological holdout begins 2024-01-01 and must not be tuned against observed results.

This is educational research, not financial advice or evidence of guaranteed returns.
