"""Reproducible CSV/PNG/Markdown deliverables with explicit evidence boundaries."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .backtest import BacktestResult, metrics_table


def _md_table(frame: pd.DataFrame, digits: int = 2) -> str:
    cols = frame.columns.tolist()
    head = "| " + " | ".join(str(s) for s in cols) + " |"
    rule = "| " + " | ".join("---" for _ in cols) + " |"
    lines = []
    for row in frame.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(
            f"{v:,.{digits}f}" if isinstance(v, float) and pd.notna(v)
            else ("N/A" if pd.isna(v) else str(v))
            for v in row
        ) + " |")
    return "\n".join([head, rule] + lines)


def save_results(result: BacktestResult, config: dict, manifest: dict, root: Path) -> None:
    out = root / "results"
    out.mkdir(exist_ok=True, parents=True)
    for frame, fname, index in (
        (result.daily_returns, "daily_returns.csv", True),
        (result.equity_curve * config["initial_capital"], "portfolio_value.csv", True),
        (result.signals.drop(columns=["strategy_targets", "trend_targets"]), "monthly_signals.csv", False),
        (result.allocations, "allocations.csv", False),
        (result.trades, "turnover_diagnostics.csv", False),
    ):
        frame.to_csv(out / fname, index=index, index_label="date" if index else None, float_format="%.10f")
    summary = metrics_table(result, config)
    summary.to_csv(out / "metrics.csv", index=False, float_format="%.8f")

    fig, ax = plt.subplots(figsize=(11, 6.2))
    for name in result.equity_curve.columns:
        ax.plot(result.equity_curve.index, result.equity_curve[name] * config["initial_capital"], label=name, linewidth=2 if name == "Conviction Dial" else 1.3)
    ax.axvline(pd.Timestamp(config["out_of_sample_start"]), color="#999", linestyle="--", alpha=.75, label="Holdout begins")
    ax.set(title="Growth of $10,000 • gross of trading costs", ylabel="Portfolio value (USD)", xlabel="Date")
    ax.legend(loc="best", fontsize=9)
    ax.grid(alpha=.18)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out / "equity_curves.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5.7))
    for name in result.equity_curve.columns:
        eq = result.equity_curve[name]
        dd = eq / eq.cummax() - 1.0
        ax.plot(eq.index, dd * 100, label=name, linewidth=2 if name == "Conviction Dial" else 1.3)
    ax.axvline(pd.Timestamp(config["out_of_sample_start"]), color="#999", linestyle="--", alpha=.75)
    ax.set(title="Drawdown from running peak • full history", ylabel="Drawdown (%)", xlabel="Date")
    ax.legend(loc="lower left", fontsize=9)
    ax.grid(alpha=.18)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out / "drawdowns.png", dpi=160)
    plt.close(fig)

    compact = summary[["window", "portfolio", "trading_days", "total_return_pct", "cagr_pct", "volatility_pct", "sharpe_rf0", "max_drawdown_pct"]].copy()
    compact.columns = ["Window", "Portfolio", "Days", "Return %", "CAGR %", "Vol %", "Sharpe (rf=0)", "Max DD %"]
    recent = result.signals.tail(8)[["signal_date", "execution_date", "regime", "top_picks"]].copy()
    recent["signal_date"] = recent["signal_date"].dt.strftime("%Y-%m-%d")
    recent["execution_date"] = recent["execution_date"].dt.strftime("%Y-%m-%d")
    recent.columns = ["Signal date", "Execution date", "Regime", "Selected ETFs"]
    oos = summary[(summary["window"] == "Out of sample") & (summary["portfolio"].isin(["Conviction Dial", "SPY buy-and-hold"]))]
    if len(oos) == 2 and oos["sharpe_rf0"].notna().all() and oos["max_drawdown_pct"].notna().all():
        a = oos.set_index("portfolio")
        passes_sharpe = a.loc["Conviction Dial", "sharpe_rf0"] > a.loc["SPY buy-and-hold", "sharpe_rf0"]
        passes_dd = a.loc["Conviction Dial", "max_drawdown_pct"] > a.loc["SPY buy-and-hold", "max_drawdown_pct"]
        evaluation = (f"Higher holdout Sharpe than SPY: **{'YES' if passes_sharpe else 'NO'}**. "
                      f"Smaller holdout maximum drawdown than SPY: **{'YES' if passes_dd else 'NO'}**. "
                      "Both requirements must be met; these figures are **before**, not after, trading costs.")
    else:
        evaluation = "Not enough valid holdout observations to evaluate success criteria."

    report = f"""# Conviction Dial — Milestone 2: Data Pipeline and First Backtest

**AD 49F | Group 9 | Due 3 November 2026**  
**Status:** Executed from downloaded Yahoo Finance daily adjusted close data, not synthetic demo inputs.  
**Data retrieved:** {manifest['retrieved_at_utc']}  
**Price window:** {manifest['requested_start_inclusive']} through {manifest['observed_end']} (requested end is exclusive).  
**Data snapshot SHA-256:** `{manifest['data_sha256']}`

## 1. Objective and scope

This is the **v0.1 baseline** defined in the Milestone 1 proposal. It deliberately implements *only* (a) monthly S&P 500 trend regimes, (b) momentum ranking, and (c) risk-on / risk-off portfolio switching. The planned value and quality scores, VIX/drawdown regimes, K-means, regime-adaptive factor trust, slippage, trading costs, and risk position limits are **not claimed to exist** in this milestone.

## 2. Reproducible data pipeline

- **Source:** Yahoo Finance, chart endpoint, daily **adjusted close** (dividend/split adjusted), with raw ticker CSVs, a wide aligned CSV, per-file SHA-256 hashes, and a machine-readable download manifest.
- **Universe:** {len(config['equity_universe'])} liquid sector/style/international ETFs: {', '.join(config['equity_universe'])}. **SPY** proxies S&P 500 and **AGG** is the bond proxy. The 60/40 benchmark uses these same assets.
- **Calendar:** SPY trading sessions. No filling missing historical prices prior to launch. A held security missing either daily close causes an explicit error, not a fabricated zero return.
- **Observation count:** {len(result.equity_curve)} sessions from {result.first_execution.date()} to {result.equity_curve.index.max().date()} inclusive (first session is an initial capital-deployment point with zero return).
- **Data reliability:** The downloaded sample uses today's known ETF universe (selection/survivorship bias), and adjusted price histories may be revised by the provider. See `data/processed/manifest.json` for symbol-by-symbol diagnostics and the saved data checksums.

## 3. Predefined, causal trading rules

At each completed month-end close (date **t**):

1. Calculate the **{config['trend_ma_days']}-trading-day simple moving average** of SPY, using data through t only. If SPY(t) is strictly above this average, the regime is **risk-on**. Otherwise it is **risk-off**.
2. Rank eligible ETFs by **{config['lookback_momentum_days']}-trading-day adjusted-price momentum**: `P(t)/P(t-{config['lookback_momentum_days']}) - 1`. Exclude assets with missing prices in the last five trading sessions.
3. In risk-on, choose the **top {config['top_n_assets']} ETFs** and allocate equally; in risk-off, allocate **100% to AGG**.
4. Execute portfolio changes at the **following trading day's close (t+1)**; the new holdings receive returns **only from the close at t+1 to t+2 and onward**. The execution day itself accrues returns at the old holdings. This deliberately avoids trading at a price that was only known *after* the month-end signal was calculated.

All portfolios start with **${config['initial_capital']:,.0f}**. The baseline SPY buy-and-hold is never rebalanced; the fixed **60% SPY / 40% AGG** baseline is reset monthly at the same execution closes; the simple trend-only baseline rotates SPY/AGG based on the identical trend signal. Daily weights drift naturally between rebalances rather than being magically equal-weighted every day.

## 4. Backtest output and benchmark results

**Performance is gross of transaction costs/slippage**. This is an intentional Milestone 2 limitation; the Milestone 1 proposal assigns both cost modeling and sensitivity testing to Milestone 3 (24 November). Reported Sharpe uses a **0% annual risk-free rate** and 252 trading sessions/year; max drawdown is measured against the running peak within each evaluation window. The holdout is the fixed interval beginning **{config['out_of_sample_start']}** and is never used to choose the 200-day/126-day/top-five model rules.

{_md_table(compact)}

**Original proposal success tests (provisional, pre-cost):** {evaluation}

![Cumulative portfolio values](equity_curves.png)

![Portfolio drawdowns](drawdowns.png)

## 5. Auditable recent monthly decisions

{_md_table(recent)}

The complete dated allocations and observed execution schedule are in `allocations.csv` and `monthly_signals.csv`; daily returns and equity curves are also exported as CSV. A separate turnover diagnostic is provided for preparing Milestone 3, **without applying a trading-cost charge now**.

## 6. Integrity checks and limitations

The code includes tests for delayed execution, correct momentum/regime signals, absence of future-price dependence, chronological splits, data-hash verification, and the choice to raise an error for missing prices held in a portfolio. See `tests/` and the CI workflow. This is an historical simulation, not live trading or a forecast.

Key limitations are the **present-day ETF universe**, provider restatements, tracking differences between ETFs and their indices, dependence on a single momentum horizon, and the **absence of actual commissions, bid-ask spreads, slippage and position limits**. The label 'out of sample' describes a chronological holdout; actual independence additionally requires that the team did not tune the rules by looking at holdout performance. The results do **not** demonstrate performance *net of costs* and should not be represented as such.

## 7. How to reproduce

With Python 3.10+ at the project root: `pip install -e . pytest`, then `python -m conviction_dial.cli fetch`, `python -m conviction_dial.cli backtest`, and `pytest`. The exact raw observations, normalized prices, SHA-256 manifest and output charts can be downloaded together from the **GitHub Actions** artifact. For offline reruns, restore `data/raw/`, `data/processed/` and rerun only `backtest` to use the same snapshot.

**Next milestone (24 November):** Add modeled commissions/slippage, turnover-linked costs, realistic exposure caps or volatility-scaled weights, and re-evaluate all results net of costs. The expanded factor/regime version remains the final-term goal.
"""
    (out / "milestone2_report.md").write_text(report, encoding="utf-8")
    (out / "run_summary.json").write_text(json.dumps({
        "data_sha256": manifest["data_sha256"],
        "out_of_sample_start": config["out_of_sample_start"],
        "first_execution": str(result.first_execution.date()),
        "last_observation": str(result.equity_curve.index.max().date()),
        "costs_included": False,
        "completed_on_synthetic_data": False,
        "metrics": summary.to_dict(orient="records"),
    }, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Wrote {out / 'milestone2_report.md'} and companion tables/figures")
