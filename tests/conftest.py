import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def cfg():
    original = json.loads((Path(__file__).parents[1] / "config.json").read_text())
    # The example price array is deliberately SYNTHETIC and exists only in tests.
    original["data_start"] = "2020-01-01"
    original["data_end_exclusive"] = "2025-01-01"
    original["out_of_sample_start"] = "2024-01-01"
    return original


@pytest.fixture
def fictional_prices(cfg):
    rng = np.random.default_rng(42)
    idx = pd.bdate_range("2020-01-01", "2024-12-31")
    market = 100 * np.exp(np.cumsum(rng.normal(.00034, .012, len(idx))))
    bond = 100 * np.exp(np.cumsum(rng.normal(.00011, .003, len(idx))))
    data = {"SPY": market, "AGG": bond}
    for i, name in enumerate(cfg["equity_universe"]):
        rs = rng.normal(.00025 + .00002 * i, .012 + .0002 * i, len(idx))
        data[name] = 100 * np.exp(np.cumsum(rs))
    return pd.DataFrame(data, index=idx)
