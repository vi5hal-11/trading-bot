"""IFVG zone identification, expiry, and invalidation management."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
import pandas as pd
from loguru import logger
from config.settings import load_trading_params
from ifvg.models import DisplacementEvent, IFVGZone, SweepEvent


def _cfg() -> dict:
    return load_trading_params().get("ifvg", {}).get("ifvg_zone", {})


def _find_fvgs(candles: pd.DataFrame) -> list[dict]:
    """Scan for 3-candle FVG patterns. Returns list of {type, high, low, idx}."""
    fvgs = []
    for i in range(1, len(candles) - 1):
        prev_low = float(candles["low"].iloc[i - 1])
        prev_high = float(candles["high"].iloc[i - 1])
        next_low = float(candles["low"].iloc[i + 1])
        next_high = float(candles["high"].iloc[i + 1])

        # Bullish FVG: gap between candle[i-1].low and candle[i+1].high
        if prev_low > next_high:
            fvgs.append({
                "type": "BULL",
                "zone_high": prev_low,
                "zone_low": next_high,
                "idx": i,
                "width": prev_low - next_high,
            })

        # Bearish FVG: gap between candle[i+1].low and candle[i-1].high
        elif next_low > prev_high:
            fvgs.append({
                "type": "BEAR",
                "zone_high": next_low,
                "zone_low": prev_high,
                "idx": i,
                "width": next_low - prev_high,
            })

    return fvgs


def find_ifvg(
    candles_15m: pd.DataFrame,
    sweep: SweepEvent,
    displacement: DisplacementEvent,
    symbol: str = "",
) -> Optional[IFVGZone]:
    """Identify the most significant IFVG zone created by the sweep+displacement sequence."""
    cfg = _cfg()
    min_width_pct = cfg.get("min_width_pct", 0.001)
    expiry_candles = cfg.get("expiry_candles", 20)

    # Locate sweep candle index
    sweep_ts = sweep.candle_timestamp
    sweep_idx: Optional[int] = None
    for i, idx in enumerate(candles_15m.index):
        ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
        if ts >= sweep_ts:
            sweep_idx = i
            break

    if sweep_idx is None:
        return None

    # Scan 50 candles before the sweep for FVGs
    scan_start = max(0, sweep_idx - 50)
    pre_sweep_candles = candles_15m.iloc[scan_start: sweep_idx]

    if len(pre_sweep_candles) < 3:
        return None

    fvgs = _find_fvgs(pre_sweep_candles)
    if not fvgs:
        logger.debug("[IFVG] No FVGs found before sweep")
        return None

    # Locate displacement candle
    disp_ts = displacement.candle_timestamp
    disp_idx: Optional[int] = None
    for i, idx in enumerate(candles_15m.index):
        ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
        if ts >= disp_ts:
            disp_idx = i
            break

    if disp_idx is None:
        return None

    disp_close = float(displacement.body_close)
    valid_ifvgs: list[dict] = []

    for fvg in fvgs:
        zone_high = fvg["zone_high"]
        zone_low = fvg["zone_low"]
        ref_price = zone_low if zone_low > 0 else zone_high
        width_pct = (zone_high - zone_low) / ref_price if ref_price > 0 else 0

        if width_pct < min_width_pct:
            continue

        # BSL_SWEEP + bearish displacement: look for bullish FVG closed through bearishly
        if sweep.direction == "BSL_SWEEP" and displacement.direction == "BEAR":
            if fvg["type"] == "BULL" and disp_close < zone_low:
                valid_ifvgs.append({**fvg, "ifvg_direction": "BEAR", "width_pct": width_pct})

        # SSL_SWEEP + bullish displacement: look for bearish FVG closed through bullishly
        elif sweep.direction == "SSL_SWEEP" and displacement.direction == "BULL":
            if fvg["type"] == "BEAR" and disp_close > zone_high:
                valid_ifvgs.append({**fvg, "ifvg_direction": "BULL", "width_pct": width_pct})

    if not valid_ifvgs:
        logger.debug("[IFVG] No valid IFVG zones after displacement check")
        return None

    # Pick the widest (most significant)
    best = max(valid_ifvgs, key=lambda x: x["width_pct"])
    zone_high = best["zone_high"]
    zone_low = best["zone_low"]
    ce = (zone_high + zone_low) / 2
    expires_at = displacement.candle_timestamp + timedelta(minutes=expiry_candles * 15)

    logger.info(
        f"[IFVG] Zone identified on {symbol} | {best['ifvg_direction']} "
        f"| high={zone_high:.4f} low={zone_low:.4f} CE={ce:.4f} "
        f"| width={best['width_pct']:.4%} expires={expires_at}"
    )

    return IFVGZone(
        symbol=symbol,
        zone_high=Decimal(str(round(zone_high, 8))),
        zone_low=Decimal(str(round(zone_low, 8))),
        ce=Decimal(str(round(ce, 8))),
        direction=best["ifvg_direction"],
        formed_at=displacement.candle_timestamp,
        expires_at=expires_at,
        width_pct=best["width_pct"],
    )


def is_ifvg_expired(ifvg: IFVGZone, now: datetime | None = None) -> bool:
    """Return True if the IFVG zone has passed its expiry time."""
    if now is None:
        now = datetime.now(timezone.utc)
    return now > ifvg.expires_at


def is_ifvg_invalidated(ifvg: IFVGZone, candle_close: float) -> bool:
    """Return True if price body-closed through the IFVG zone (wick touches do NOT count)."""
    if ifvg.direction == "BULL":
        return candle_close < float(ifvg.zone_low)
    else:
        return candle_close > float(ifvg.zone_high)
