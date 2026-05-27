"""4H directional bias detection using swing structure and midpoint filter."""
from datetime import datetime, timezone
import pandas as pd
from loguru import logger
from config.settings import load_trading_params
from ifvg.models import Bias


def _cfg() -> dict:
    return load_trading_params().get("ifvg", {}).get("bias", {})


def _find_swings(df: pd.DataFrame, lookback: int) -> tuple[list[float], list[float]]:
    """Return (swing_highs, swing_lows) as lists of price levels."""
    highs: list[float] = []
    lows: list[float] = []
    n = len(df)
    for i in range(lookback, n - lookback):
        window_high = df["high"].iloc[i - lookback: i + lookback + 1]
        window_low = df["low"].iloc[i - lookback: i + lookback + 1]
        if df["high"].iloc[i] == window_high.max():
            highs.append(float(df["high"].iloc[i]))
        if df["low"].iloc[i] == window_low.min():
            lows.append(float(df["low"].iloc[i]))
    return highs, lows


def get_4h_bias(candles: pd.DataFrame) -> Bias:
    """Determine 4H directional bias from swing structure and midpoint filter.

    Expects DataFrame with columns: open, high, low, close, volume.
    """
    cfg = _cfg()
    swing_lookback = cfg.get("swing_lookback", 5)
    midpoint_lookback = cfg.get("midpoint_lookback", 20)
    now = datetime.now(timezone.utc)

    if len(candles) < swing_lookback * 2 + midpoint_lookback:
        logger.debug("[IFVG] Insufficient 4H candles for bias detection")
        return Bias(direction="NONE", timestamp=now)

    swing_highs, swing_lows = _find_swings(candles, swing_lookback)

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return Bias(direction="NONE", timestamp=now)

    last_hh = swing_highs[-1] > swing_highs[-2]
    prev_hh = swing_highs[-2] > swing_highs[-3] if len(swing_highs) >= 3 else last_hh
    last_hl = swing_lows[-1] > swing_lows[-2]
    prev_hl = swing_lows[-2] > swing_lows[-3] if len(swing_lows) >= 3 else last_hl

    last_lh = swing_highs[-1] < swing_highs[-2]
    last_ll = swing_lows[-1] < swing_lows[-2]

    current_close = float(candles["close"].iloc[-1])
    midpoint = float(candles["close"].iloc[-midpoint_lookback:].mean())

    bull = last_hh and last_hl and current_close > midpoint
    bear = last_lh and last_ll and current_close < midpoint

    if bull and not bear:
        direction = "BULL"
    elif bear and not bull:
        direction = "BEAR"
    else:
        direction = "NONE"

    logger.debug(
        f"[IFVG] 4H bias={direction} | close={current_close:.2f} mid={midpoint:.2f} "
        f"HH={last_hh} HL={last_hl} LH={last_lh} LL={last_ll}"
    )
    return Bias(direction=direction, timestamp=now)
