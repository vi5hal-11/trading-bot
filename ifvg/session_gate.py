"""Killzone time windows and news/shock blackout logic."""
from datetime import datetime, time, timezone
import redis
from loguru import logger
from config.settings import load_trading_params


def _cfg() -> dict:
    return load_trading_params().get("ifvg", {}).get("session", {})


def is_killzone_active(now: datetime | None = None) -> tuple[bool, str]:
    """Return (True, zone_name) if now (UTC) falls within any killzone, else (False, '')."""
    cfg = _cfg()
    kz = cfg.get("killzones_utc", {})
    if now is None:
        now = datetime.now(timezone.utc)
    t = now.time().replace(tzinfo=None)

    for zone_name, window in kz.items():
        start = time.fromisoformat(window["start"])
        end = time.fromisoformat(window["end"])
        if start <= t <= end:
            return True, zone_name
    return False, ""


def is_blackout_active(symbol: str, redis_client: redis.Redis) -> bool:
    """Return True if any blackout key exists for the symbol in Redis."""
    try:
        if redis_client.exists(f"ifvg:news_blackout:{symbol}"):
            return True
        if redis_client.exists(f"ifvg:shock_blackout:{symbol}"):
            return True
    except Exception as e:
        logger.warning(f"Redis blackout check failed for {symbol}: {e}")
    return False


def register_shock_candle(
    symbol: str,
    candle_high: float,
    candle_low: float,
    atr: float,
    redis_client: redis.Redis,
) -> None:
    """Set shock blackout in Redis if candle range exceeds ATR multiplier threshold."""
    cfg = _cfg()
    multiplier = cfg.get("shock_candle_atr_multiplier", 3.0)
    blackout_minutes = int(cfg.get("shock_blackout_minutes", 15))

    candle_range = candle_high - candle_low
    if atr > 0 and candle_range > multiplier * atr:
        try:
            redis_client.setex(
                f"ifvg:shock_blackout:{symbol}",
                blackout_minutes * 60,
                "1",
            )
            logger.info(
                f"[IFVG] Shock candle detected on {symbol} "
                f"(range={candle_range:.4f}, ATR={atr:.4f}) — blackout {blackout_minutes}m"
            )
        except Exception as e:
            logger.warning(f"Redis shock blackout set failed for {symbol}: {e}")
