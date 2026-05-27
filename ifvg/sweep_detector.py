"""15m liquidity sweep identification."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
import pandas as pd
from loguru import logger
from config.settings import load_trading_params
from ifvg.models import LiquidityPool, SweepEvent

_DEDUP_CANDLES = 3  # ignore re-sweep of same pool within this many candles


def _cfg() -> dict:
    return load_trading_params().get("ifvg", {}).get("sweep", {})


def detect_sweep(
    candles_15m: pd.DataFrame,
    pools: list[LiquidityPool],
    atr: float,
    symbol: str = "",
) -> Optional[SweepEvent]:
    """Check the most recently closed 15m candle for a valid liquidity sweep.

    Returns a SweepEvent if a sweep is found, None otherwise.
    """
    if len(candles_15m) < 2 or not pools:
        return None

    cfg = _cfg()
    min_ext = cfg.get("min_extension_pct", 0.0005)
    max_body_mult = cfg.get("max_body_atr_multiplier", 2.0)

    # Use the second-to-last candle (last fully closed)
    candle = candles_15m.iloc[-2]
    candle_ts: datetime = candle.name.to_pydatetime() if hasattr(candle.name, "to_pydatetime") else datetime.now(timezone.utc)

    c_open = float(candle["open"])
    c_high = float(candle["high"])
    c_low = float(candle["low"])
    c_close = float(candle["close"])
    body_size = abs(c_close - c_open)

    if body_size > max_body_mult * atr:
        logger.debug(f"[IFVG] Candle body {body_size:.4f} exceeds {max_body_mult}×ATR — skipping sweep check")
        return None

    # Deduplication: check if sweep happened within last N candles
    recent_closes = candles_15m["close"].iloc[-_DEDUP_CANDLES - 2: -2]

    for pool in pools:
        level = float(pool.level)

        if pool.side == "BSL":
            # Wick above pool, close below pool = sweep of buy-side liquidity
            if c_high > level and c_close < level:
                extension = (c_high - level) / level
                if extension >= min_ext:
                    # Dedup: check if price was already above level recently
                    if any(float(p) > level for p in recent_closes):
                        logger.debug(f"[IFVG] BSL sweep dedup — pool {level:.4f} already swept recently")
                        continue
                    logger.info(
                        f"[IFVG] BSL sweep on {symbol} | pool={level:.4f} "
                        f"wick_high={c_high:.4f} ext={extension:.4%}"
                    )
                    return SweepEvent(
                        symbol=symbol,
                        candle_timestamp=candle_ts,
                        sweep_extreme=Decimal(str(round(c_high, 8))),
                        pool_level=pool.level,
                        direction="BSL_SWEEP",
                        extension_pct=extension,
                    )

        else:  # SSL
            # Wick below pool, close above pool = sweep of sell-side liquidity
            if c_low < level and c_close > level:
                extension = (level - c_low) / level
                if extension >= min_ext:
                    if any(float(p) < level for p in recent_closes):
                        logger.debug(f"[IFVG] SSL sweep dedup — pool {level:.4f} already swept recently")
                        continue
                    logger.info(
                        f"[IFVG] SSL sweep on {symbol} | pool={level:.4f} "
                        f"wick_low={c_low:.4f} ext={extension:.4%}"
                    )
                    return SweepEvent(
                        symbol=symbol,
                        candle_timestamp=candle_ts,
                        sweep_extreme=Decimal(str(round(c_low, 8))),
                        pool_level=pool.level,
                        direction="SSL_SWEEP",
                        extension_pct=extension,
                    )

    return None
