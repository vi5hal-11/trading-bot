"""Tests for IFVG confluence scoring."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pandas as pd
import numpy as np
import pytest

from ifvg.models import Bias, SweepEvent, DisplacementEvent, IFVGZone
from ifvg.confluence import score_setup, check_smt

NOW = datetime.now(timezone.utc)


def _make_1h_candles(n: int = 30) -> pd.DataFrame:
    np.random.seed(0)
    base = 50000.0
    rows = []
    for _ in range(n):
        o = base
        c = base * (1 + np.random.uniform(-0.001, 0.001))
        h = max(o, c) * 1.001
        l = min(o, c) * 0.999
        rows.append({"open": o, "high": h, "low": l, "close": c, "volume": 1000.0})
        base = c
    return pd.DataFrame(rows)


def _make_sweep(direction: str = "BSL_SWEEP", extension: float = 0.001) -> SweepEvent:
    return SweepEvent(
        symbol="BTC/USDT:USDT",
        candle_timestamp=NOW,
        sweep_extreme=Decimal("50100"),
        pool_level=Decimal("50000"),
        direction=direction,
        extension_pct=extension,
    )


def _make_displacement(atr_ratio: float = 2.5) -> DisplacementEvent:
    return DisplacementEvent(
        candle_timestamp=NOW,
        atr_ratio=atr_ratio,
        direction="BEAR",
        body_close=Decimal("49700"),
    )


def _make_zone() -> IFVGZone:
    return IFVGZone(
        symbol="BTC/USDT:USDT",
        zone_high=Decimal("49900"),
        zone_low=Decimal("49700"),
        ce=Decimal("49800"),
        direction="BEAR",
        formed_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=4),
        width_pct=0.004,
    )


def test_score_returns_0_to_6():
    bias = Bias(direction="BEAR", timestamp=NOW)
    sweep = _make_sweep("BSL_SWEEP")
    displacement = _make_displacement()
    zone = _make_zone()
    candles_1h = _make_1h_candles()
    score = score_setup(
        bias_4h=bias,
        structure_ok=True,
        sweep=sweep,
        displacement=displacement,
        ifvg=zone,
        candles_1h=candles_1h,
        correlated_candles={},
        atr=100.0,
    )
    assert 0 <= score.total <= 6
    assert len(score.breakdown) == 6


def test_bias_confirmed_counts():
    bias = Bias(direction="BULL", timestamp=NOW)
    sweep = _make_sweep("SSL_SWEEP", extension=0.00001)
    disp = DisplacementEvent(
        candle_timestamp=NOW, atr_ratio=1.0, direction="BULL", body_close=Decimal("50100")
    )
    zone = IFVGZone(
        symbol="BTC/USDT:USDT",
        zone_high=Decimal("50100"),
        zone_low=Decimal("49900"),
        ce=Decimal("50000"),
        direction="BULL",
        formed_at=NOW,
        expires_at=NOW + timedelta(hours=4),
        width_pct=0.002,
    )
    score = score_setup(
        bias_4h=bias,
        structure_ok=False,
        sweep=sweep,
        displacement=disp,
        ifvg=zone,
        candles_1h=_make_1h_candles(),
        correlated_candles={},
        atr=100.0,
    )
    assert score.breakdown["bias_confirmed"] is True


def test_no_bias_zero_on_bias_point():
    bias = Bias(direction="NONE", timestamp=NOW)
    sweep = _make_sweep()
    displacement = _make_displacement()
    zone = _make_zone()
    score = score_setup(
        bias_4h=bias,
        structure_ok=True,
        sweep=sweep,
        displacement=displacement,
        ifvg=zone,
        candles_1h=_make_1h_candles(),
        correlated_candles={},
        atr=100.0,
    )
    assert score.breakdown["bias_confirmed"] is False


def test_strong_sweep_threshold():
    sweep_weak = _make_sweep(extension=0.00001)
    sweep_strong = _make_sweep(extension=0.001)
    bias = Bias(direction="BEAR", timestamp=NOW)
    zone = _make_zone()
    disp = _make_displacement()
    df = _make_1h_candles()

    score_weak = score_setup(bias, True, sweep_weak, disp, zone, df, {}, 100.0)
    score_strong = score_setup(bias, True, sweep_strong, disp, zone, df, {}, 100.0)
    assert score_weak.breakdown["strong_sweep"] is False
    assert score_strong.breakdown["strong_sweep"] is True


def test_check_smt_no_correlated_returns_false():
    sweep = _make_sweep("BSL_SWEEP")
    result = check_smt(sweep, {}, smt_window=1)
    assert result is False
