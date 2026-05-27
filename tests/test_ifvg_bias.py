"""Tests for IFVG bias engine."""
import numpy as np
import pandas as pd
import pytest
from ifvg.bias_engine import get_4h_bias


def _make_candles(n: int, trend: str = "bull") -> pd.DataFrame:
    """Create synthetic OHLCV with a clear trend."""
    np.random.seed(42)
    prices = []
    base = 50000.0
    for i in range(n):
        if trend == "bull":
            base *= 1 + np.random.uniform(0.001, 0.005)
        elif trend == "bear":
            base *= 1 - np.random.uniform(0.001, 0.005)
        else:
            base *= 1 + np.random.uniform(-0.002, 0.002)
        prices.append(base)

    df = pd.DataFrame({
        "open": prices,
        "high": [p * 1.002 for p in prices],
        "low": [p * 0.998 for p in prices],
        "close": prices,
        "volume": [100.0] * n,
    })
    return df


def test_bull_bias():
    df = _make_candles(60, trend="bull")
    bias = get_4h_bias(df)
    assert bias.direction == "BULL"


def test_bear_bias():
    df = _make_candles(60, trend="bear")
    bias = get_4h_bias(df)
    assert bias.direction == "BEAR"


def test_insufficient_candles_returns_none():
    df = _make_candles(5, trend="bull")
    bias = get_4h_bias(df)
    assert bias.direction == "NONE"
