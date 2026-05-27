"""Tests for IFVG sweep detector."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pandas as pd
import numpy as np
import pytest

from ifvg.models import LiquidityPool
from ifvg.sweep_detector import detect_sweep

NOW = datetime.now(timezone.utc)


def _make_pool(level: float, side: str) -> LiquidityPool:
    return LiquidityPool(
        level=Decimal(str(level)),
        side=side,
        touch_count=2,
        formed_at=NOW - timedelta(hours=5),
        expires_at=NOW + timedelta(hours=10),
    )


def _make_candles_with_sweep(pool_level: float, side: str) -> pd.DataFrame:
    """
    Build a small DataFrame where the last completed candle wicks through pool_level
    but closes back inside.
    """
    times = [NOW - timedelta(minutes=30 * i) for i in range(10, -1, -1)]
    closes = [pool_level * 0.999] * 11  # all below pool by default
    opens = closes.copy()
    highs = [pool_level * 0.9995] * 11
    lows = [pool_level * 0.9985] * 11

    if side == "BSL":
        # Last closed candle (index -2) wicks above pool then closes below
        highs[-2] = pool_level * 1.002  # wick above
        closes[-2] = pool_level * 0.999  # close back below
        opens[-2] = pool_level * 0.998
        lows[-2] = pool_level * 0.997
    else:  # SSL
        closes = [pool_level * 1.001] * 11
        opens = closes.copy()
        highs = [pool_level * 1.002] * 11
        lows = [pool_level * 0.9985] * 11

        lows[-2] = pool_level * 0.998  # wick below
        closes[-2] = pool_level * 1.001  # close back above
        opens[-2] = pool_level * 1.002
        highs[-2] = pool_level * 1.003

    df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [100.0] * 11,
    }, index=pd.DatetimeIndex(times))
    return df


def test_bsl_sweep_detected():
    pool_level = 50000.0
    pool = _make_pool(pool_level, "BSL")
    df = _make_candles_with_sweep(pool_level, "BSL")
    atr = pool_level * 0.002  # 0.2% ATR
    result = detect_sweep(df, [pool], atr, "BTC/USDT:USDT")
    assert result is not None
    assert result.direction == "BSL_SWEEP"


def test_ssl_sweep_detected():
    pool_level = 50000.0
    pool = _make_pool(pool_level, "SSL")
    df = _make_candles_with_sweep(pool_level, "SSL")
    atr = pool_level * 0.002
    result = detect_sweep(df, [pool], atr, "BTC/USDT:USDT")
    assert result is not None
    assert result.direction == "SSL_SWEEP"


def test_no_sweep_flat_candles():
    pool_level = 50000.0
    pool = _make_pool(pool_level, "BSL")
    times = [NOW - timedelta(minutes=30 * i) for i in range(10, -1, -1)]
    df = pd.DataFrame({
        "open": [49900.0] * 11,
        "high": [49950.0] * 11,
        "low": [49850.0] * 11,
        "close": [49900.0] * 11,
        "volume": [100.0] * 11,
    }, index=pd.DatetimeIndex(times))
    atr = 100.0
    result = detect_sweep(df, [pool], atr, "BTC/USDT:USDT")
    assert result is None
