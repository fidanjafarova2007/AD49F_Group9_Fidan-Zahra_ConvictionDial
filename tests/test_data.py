import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import pytest

from conviction_dial.data import parse_yahoo_chart, load_dataset


def test_yahoo_adjusted_close_not_unadjusted_fallback():
    ts = [int(datetime(2020, 6, 2, 16, tzinfo=timezone.utc).timestamp()),
          int(datetime(2020, 6, 3, 16, tzinfo=timezone.utc).timestamp())]
    payload = {"chart": {"result": [{"timestamp": ts, "indicators": {
        "quote": [{"close": [200, 205]}], "adjclose": [{"adjclose": [190, 194]}]}}], "error": None}}
    s = parse_yahoo_chart(payload, "SPY")
    assert list(s.values) == [190, 194]
    del payload["chart"]["result"][0]["indicators"]["adjclose"]
    with pytest.raises(ValueError, match="adjusted"):
        parse_yahoo_chart(payload, "SPY")


def test_snapshot_checksum_rejects_tampering(tmp_path: Path, cfg, fictional_prices):
    out = tmp_path / "data" / "processed"
    out.mkdir(parents=True)
    path = out / "adjusted_close.csv"
    fictional_prices.to_csv(path, index_label="date")
    manifest = {"data_sha256": "definitely_not_the_actual_hash"}
    (out / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="hash"):
        load_dataset(cfg, tmp_path)


def test_end_to_end_snapshot_and_report_without_network(tmp_path: Path, cfg, fictional_prices, monkeypatch):
    """Test orchestration on TEST-ONLY fictional prices; not an empirical backtest."""
    from conviction_dial import data
    from conviction_dial.backtest import backtest
    from conviction_dial.reporting import save_results

    def fake_fetch(symbol, start, end, session=None):
        return fictional_prices[symbol].rename(symbol)

    monkeypatch.setattr(data, "download_symbol", fake_fetch)
    data.download_dataset(cfg, tmp_path)
    prices, manifest = load_dataset(cfg, tmp_path)
    assert len(prices) == len(fictional_prices)
    assert manifest["data_sha256"]
    assert len(list((tmp_path / "data/raw").glob("*.csv"))) == 22
    result = backtest(prices, cfg)
    save_results(result, cfg, manifest, tmp_path)
    assert (tmp_path / "results/milestone2_report.md").exists()
    assert (tmp_path / "results/equity_curves.png").stat().st_size > 10000
