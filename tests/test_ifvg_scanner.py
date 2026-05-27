"""Tests for IFVG zone scanner."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pandas as pd
import pytest

from ifvg.models import SweepEvent, DisplacementEvent, IFVGZone
from ifvg.ifvg_scanner import find_ifvg, is_ifvg_expired, is_ifvg_invalidated

NOW = datetime.now(timezone.utc)


def _make_sweep(direction: str = "BSL_SWEEP") -> SweepEvent:
    return SweepEvent(
        symbol="BTC/USDT:USDT",
        candle_timestamp=NOW - timedelta(minutes=30),
        sweep_extreme=Decimal("50100"),
        pool_level=Decimal("50000"),
        direction=direction,
        extension_pct=0.002,
    )


def _make_displacement(direction: str = "BEAR", close: float = 49600.0) -> DisplacementEvent:
    return DisplacementEvent(
        candle_timestamp=NOW - timedelta(minutes=15),
        atr_ratio=2.2,
        direction=direction,
        body_close=Decimal(str(close)),
    )


def _make_candles_with_fvg() -> pd.DataFrame:
    """
    Build a 15-min DataFrame containing a bullish FVG (3-candle gap) before a BSL sweep.
    Candle layout (oldest → newest):
      0-7:  normal candles around 50000
      8:    big bullish candle (high=50200) — gap candle
      9:    impulse candle: prev_low > next_high creates gap
      10:   next candle (low at 49900)  → gap = 49900 (i+1 high) to 50200 (i-1 low)... we build differently
    """
    # For a bearish FVG (swept by BSL then displaced BEAR):
    # We need a bullish FVG: candle[i-1].low > candle[i+1].high
    # Then displacement closes below zone_low (i+1.high)

    base_time = NOW - timedelta(minutes=15 * 55)
    times = [base_time + timedelta(minutes=15 * i) for i in range(60)]

    closes = [50000.0] * 60
    opens = [50000.0] * 60
    highs = [50010.0] * 60
    lows = [49990.0] * 60

    # Create a bullish FVG at index 30: candle[29].low > candle[31].high
    # FVG gap = candle[31].high (49700) to candle[29].low (50000)
    lows[29] = 50000.0
    highs[29] = 50200.0
    closes[29] = 50150.0
    opens[29] = 50050.0

    # Gap candle (middle of FVG)
    opens[30] = 50200.0
    closes[30] = 50150.0
    highs[30] = 50400.0
    lows[30] = 50100.0

    # Next candle — high must be below prev.low to create BULL FVG
    opens[31] = 49700.0
    closes[31] = 49750.0
    highs[31] = 49800.0   # 49800 < 50000 (lows[29]) → bullish FVG created
    lows[31] = 49650.0

    # Sweep candle at index 48 (matches sweep timestamp ~NOW - 30m)
    sweep_idx = 48
    highs[sweep_idx] = 50110.0
    closes[sweep_idx] = 50050.0
    opens[sweep_idx] = 50020.0
    lows[sweep_idx] = 50010.0

    # Displacement candle at index 49 (big bearish, closes below FVG zone_low=49800)
    opens[49] = 50040.0
    closes[49] = 49600.0
    highs[49] = 50050.0
    lows[49] = 49580.0

    df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [100.0] * 60,
    }, index=pd.DatetimeIndex(times))
    return df


def test_find_ifvg_returns_zone():
    df = _make_candles_with_fvg()
    sweep = _make_sweep("BSL_SWEEP")
    displacement = _make_displacement("BEAR", 49600.0)
    zone = find_ifvg(df, sweep, displacement, "BTC/USDT:USDT")
    # Should find a BEAR IFVG (BSL sweep + BEAR displacement through bullish FVG)
    assert zone is not None
    assert zone.direction == "BEAR"
    assert float(zone.zone_high) > float(zone.zone_low)


def test_is_ifvg_expired_true():
    zone = IFVGZone(
        symbol="BTC/USDT:USDT",
        zone_high=Decimal("50000"),
        zone_low=Decimal("49800"),
        ce=Decimal("49900"),
        direction="BEAR",
        formed_at=NOW - timedelta(hours=6),
        expires_at=NOW - timedelta(minutes=1),
        width_pct=0.004,
    )
    assert is_ifvg_expired(zone, now=NOW) is True


def test_is_ifvg_expired_false():
    zone = IFVGZone(
        symbol="BTC/USDT:USDT",
        zone_high=Decimal("50000"),
        zone_low=Decimal("49800"),
        ce=Decimal("49900"),
        direction="BEAR",
        formed_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=4),
        width_pct=0.004,
    )
    assert is_ifvg_expired(zone, now=NOW) is False


def test_is_ifvg_invalidated_bull():
    zone = IFVGZone(
        symbol="BTC/USDT:USDT",
        zone_high=Decimal("50000"),
        zone_low=Decimal("49800"),
        ce=Decimal("49900"),
        direction="BULL",
        formed_at=NOW,
        expires_at=NOW + timedelta(hours=4),
        width_pct=0.004,
    )
    # BULL zone: body close below zone_low → invalidated
    assert is_ifvg_invalidated(zone, 49799.0) is True
    # Wick touches zone_low but close is above — NOT invalidated
    assert is_ifvg_invalidated(zone, 49801.0) is False


def test_is_ifvg_invalidated_bear():
    zone = IFVGZone(
        symbol="BTC/USDT:USDT",
        zone_high=Decimal("50000"),
        zone_low=Decimal("49800"),
        ce=Decimal("49900"),
        direction="BEAR",
        formed_at=NOW,
        expires_at=NOW + timedelta(hours=4),
        width_pct=0.004,
    )
    # BEAR zone: body close above zone_high → invalidated
    assert is_ifvg_invalidated(zone, 50001.0) is True
    assert is_ifvg_invalidated(zone, 49999.0) is False
