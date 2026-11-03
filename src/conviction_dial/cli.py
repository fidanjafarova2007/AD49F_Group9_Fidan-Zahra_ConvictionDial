"""Command line interface: fetch data once, then reproduce backtests offline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backtest import backtest
from .data import download_dataset, load_dataset
from .reporting import save_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Conviction Dial: Milestone 2 research prototype")
    parser.add_argument("command", choices=["fetch", "backtest", "all"], help="Download snapshot, rerun saved data, or both")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2], help="Project repository directory")
    args = parser.parse_args()
    root = args.root.resolve()
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    if args.command in ("fetch", "all"):
        download_dataset(config, root)
    if args.command in ("backtest", "all"):
        prices, manifest = load_dataset(config, root)
        result = backtest(prices, config)
        save_results(result, config, manifest, root)
        print("Reproduction complete. Open results/milestone2_report.md")


if __name__ == "__main__":
    main()
