"""Tests for IFVG Pydantic models."""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from ifvg.models import (
    Bias, LiquidityPool, SweepEvent, DisplacementEvent,
    IFVGZone, ConfluenceScore, TradeState,
)

NOW = datetime.now(timezone.utc)


def test_bias_bull():
    b = Bias(direction="BULL", timestamp=NOW)
    assert b.direction == "BULL"


def test_bias_none():
    b = Bias(direction="NONE", timestamp=NOW)
    assert b.direction == "NONE"


def test_liquidity_pool():
    pool = LiquidityPool(
        level=Decimal("50000"),
        side="BSL",
        touch_count=3,
        formed_at=NOW,
        expires_at=NOW,
    )
    assert pool.side == "BSL"
    assert pool.touch_count == 3


def test_sweep_event():
    s = SweepEvent(
        symbol="BTC/USDT:USDT",
        candle_timestamp=NOW,
        sweep_extreme=Decimal("50100"),
        pool_level=Decimal("50000"),
        direction="BSL_SWEEP",
        extension_pct=0.002,
    )
    assert s.direction == "BSL_SWEEP"


def test_displacement_event():
    d = DisplacementEvent(
        candle_timestamp=NOW,
        atr_ratio=2.1,
        direction="BEAR",
        body_close=Decimal("49500"),
    )
    assert d.direction == "BEAR"


def test_ifvg_zone_valid():
    z = IFVGZone(
        symbol="BTC/USDT:USDT",
        zone_high=Decimal("50000"),
        zone_low=Decimal("49800"),
        ce=Decimal("49900"),
        direction="BULL",
        formed_at=NOW,
        expires_at=NOW,
        width_pct=0.004,
    )
    assert float(z.ce) == 49900.0


def test_ifvg_zone_invalid_raises():
    with pytest.raises(Exception):
        IFVGZone(
            symbol="BTC/USDT:USDT",
            zone_high=Decimal("49800"),  # lower than zone_low — should fail
            zone_low=Decimal("50000"),
            ce=Decimal("49900"),
            direction="BULL",
            formed_at=NOW,
            expires_at=NOW,
            width_pct=0.004,
        )


def test_confluence_score():
    cs = ConfluenceScore(
        total=5,
        breakdown={
            "bias_confirmed": True,
            "structure_ok": True,
            "strong_sweep": True,
            "strong_displacement": True,
            "ob_aligned": True,
            "smt_divergence": False,
        },
    )
    assert cs.total == 5


def test_trade_state_defaults():
    ts = TradeState(
        symbol="BTC/USDT:USDT",
        entry_price=Decimal("50000"),
        sl_price=Decimal("49800"),
        tp1_price=Decimal("50200"),
        tp2_price=Decimal("50400"),
        dol_level=Decimal("50500"),
        position_size=Decimal("0.01"),
        risk_amount=Decimal("100"),
        status="PENDING_A",
    )
    assert ts.tp1_hit is False
    assert ts.candles_since_entry == 0
    assert ts.entry_mode == "NONE"
