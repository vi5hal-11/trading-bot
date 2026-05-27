"""1H BOS/MSS confirmation and liquidity pool detection."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pandas as pd
from loguru import logger
from config.settings import load_trading_params
from ifvg.models import Bias, LiquidityPool


def _cfg() -> dict:
    return load_trading_params().get("ifvg", {}).get("structure", {})


def get_active_pools(candles_1h: pd.DataFrame, now: datetime) -> list[LiquidityPool]:
    """Scan 1H candles for swing-based liquidity pools (equal highs/lows touched 2+ times)."""
    cfg = _cfg()
    lookback = cfg.get("pool_lookback", 20)
    expiry_candles = cfg.get("pool_expiry_candles", 40)
    max_per_side = cfg.get("pool_max_per_side", 3)
    min_distance_pct = cfg.get("pool_min_distance_pct", 0.003)
    touch_tolerance = 0.001  # 0.1% tolerance for "touching" a level

    df = candles_1h.iloc[-lookback:]
    current_price = float(candles_1h["close"].iloc[-1])
    expiry = now + timedelta(hours=expiry_candles)

    candidate_highs: list[float] = []
    candidate_lows: list[float] = []

    for i in range(1, len(df) - 1):
        h = float(df["high"].iloc[i])
        l = float(df["low"].iloc[i])
        if df["high"].iloc[i] >= df["high"].iloc[i - 1] and df["high"].iloc[i] >= df["high"].iloc[i + 1]:
            candidate_highs.append(h)
        if df["low"].iloc[i] <= df["low"].iloc[i - 1] and df["low"].iloc[i] <= df["low"].iloc[i + 1]:
            candidate_lows.append(l)

    pools: list[LiquidityPool] = []

    def count_touches(level: float, series: pd.Series) -> int:
        return int((series - level).abs().lt(level * touch_tolerance).sum())

    # BSL pools from swing highs
    bsl_pools: list[LiquidityPool] = []
    for level in candidate_highs:
        touches = count_touches(level, df["high"])
        dist_pct = abs(level - current_price) / current_price
        if touches >= 2 and dist_pct >= min_distance_pct:
            bsl_pools.append(LiquidityPool(
                level=Decimal(str(round(level, 8))),
                side="BSL",
                touch_count=touches,
                formed_at=now,
                expires_at=expiry,
            ))

    # SSL pools from swing lows
    ssl_pools: list[LiquidityPool] = []
    for level in candidate_lows:
        touches = count_touches(level, df["low"])
        dist_pct = abs(level - current_price) / current_price
        if touches >= 2 and dist_pct >= min_distance_pct:
            ssl_pools.append(LiquidityPool(
                level=Decimal(str(round(level, 8))),
                side="SSL",
                touch_count=touches,
                formed_at=now,
                expires_at=expiry,
            ))

    # Keep max_per_side, highest touch count first
    bsl_pools.sort(key=lambda p: p.touch_count, reverse=True)
    ssl_pools.sort(key=lambda p: p.touch_count, reverse=True)
    pools = bsl_pools[:max_per_side] + ssl_pools[:max_per_side]

    logger.debug(f"[IFVG] Active pools: {len(bsl_pools[:max_per_side])} BSL, {len(ssl_pools[:max_per_side])} SSL")
    return pools


def check_1h_structure(candles_1h: pd.DataFrame, bias: Bias) -> bool:
    """Return True if a BOS (Break of Structure) confirms the 4H bias on 1H chart."""
    cfg = _cfg()
    lookback = cfg.get("bos_lookback", 10)

    if bias.direction == "NONE":
        return False

    df = candles_1h.iloc[-lookback - 1:]

    if bias.direction == "BULL":
        # Find the most recent swing high before the last candle
        swing_highs = [float(df["high"].iloc[i]) for i in range(len(df) - 1)
                       if df["high"].iloc[i] >= df["high"].iloc[max(0, i-1)] and
                       df["high"].iloc[i] >= df["high"].iloc[min(len(df)-1, i+1)]]
        if not swing_highs:
            return False
        last_swing_high = max(swing_highs)
        # BOS = close above that swing high
        return float(df["close"].iloc[-1]) > last_swing_high

    else:  # BEAR
        swing_lows = [float(df["low"].iloc[i]) for i in range(len(df) - 1)
                      if df["low"].iloc[i] <= df["low"].iloc[max(0, i-1)] and
                      df["low"].iloc[i] <= df["low"].iloc[min(len(df)-1, i+1)]]
        if not swing_lows:
            return False
        last_swing_low = min(swing_lows)
        return float(df["close"].iloc[-1]) < last_swing_low
