"""Post-sweep displacement candle validation."""
from decimal import Decimal
from typing import Optional
import pandas as pd
from loguru import logger
from config.settings import load_trading_params
from ifvg.models import DisplacementEvent, SweepEvent


def _cfg() -> dict:
    return load_trading_params().get("ifvg", {}).get("displacement", {})


def check_displacement(
    candles_15m: pd.DataFrame,
    sweep: SweepEvent,
    atr: float,
) -> Optional[DisplacementEvent]:
    """Validate that a strong displacement candle follows the sweep.

    Looks at up to max_candles_after_sweep candles after the sweep candle.
    Returns DisplacementEvent if found, None otherwise.
    """
    cfg = _cfg()
    min_atr_mult = cfg.get("min_atr_multiplier", 1.5)
    max_candles = cfg.get("max_candles_after_sweep", 2)

    if atr <= 0:
        return None

    # Locate the sweep candle index in the DataFrame
    sweep_ts = sweep.candle_timestamp
    sweep_idx: Optional[int] = None
    for i, idx in enumerate(candles_15m.index):
        ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
        if ts >= sweep_ts:
            sweep_idx = i
            break

    if sweep_idx is None or sweep_idx + 1 >= len(candles_15m):
        logger.debug("[IFVG] Cannot find post-sweep candles for displacement check")
        return None

    sweep_candle = candles_15m.iloc[sweep_idx]
    sweep_mid = (float(sweep_candle["open"]) + float(sweep_candle["close"])) / 2

    # Check candles immediately after the sweep
    for offset in range(1, max_candles + 1):
        idx = sweep_idx + offset
        if idx >= len(candles_15m):
            break

        c = candles_15m.iloc[idx]
        c_open = float(c["open"])
        c_high = float(c["high"])
        c_low = float(c["low"])
        c_close = float(c["close"])
        c_range = c_high - c_low
        atr_ratio = c_range / atr

        if atr_ratio < min_atr_mult:
            continue

        ts = c.name.to_pydatetime() if hasattr(c.name, "to_pydatetime") else c.name

        # BSL_SWEEP → expect bearish displacement
        if sweep.direction == "BSL_SWEEP":
            if c_close < sweep_mid and c_close < c_open:
                logger.info(
                    f"[IFVG] Bearish displacement found after BSL sweep "
                    f"| atr_ratio={atr_ratio:.2f} | close={c_close:.4f}"
                )
                return DisplacementEvent(
                    candle_timestamp=ts,
                    atr_ratio=round(atr_ratio, 3),
                    direction="BEAR",
                    body_close=Decimal(str(round(c_close, 8))),
                )

        # SSL_SWEEP → expect bullish displacement
        else:
            if c_close > sweep_mid and c_close > c_open:
                logger.info(
                    f"[IFVG] Bullish displacement found after SSL sweep "
                    f"| atr_ratio={atr_ratio:.2f} | close={c_close:.4f}"
                )
                return DisplacementEvent(
                    candle_timestamp=ts,
                    atr_ratio=round(atr_ratio, 3),
                    direction="BULL",
                    body_close=Decimal(str(round(c_close, 8))),
                )

    logger.debug("[IFVG] No valid displacement found after sweep")
    return None
