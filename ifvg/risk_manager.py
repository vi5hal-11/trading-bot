"""Position update logic: partial TPs, trailing stop, daily loss guard."""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
import redis
from loguru import logger
from config.settings import load_trading_params
from ifvg.models import TradeState


def _cfg() -> dict:
    return load_trading_params().get("ifvg", {}).get("risk", {})


def update_trade(
    trade: TradeState,
    candle_high: float,
    candle_low: float,
    current_price: float,
    atr: float,
    candles_since_last_trail: int,
) -> TradeState:
    """Apply TP1, TP2, trailing stop, and SL logic to an open trade.

    Returns an updated TradeState. Caller checks status=='CLOSED' to close position.
    """
    cfg = _cfg()
    tp1_r = cfg.get("tp1_r", 1.0)
    tp2_r = cfg.get("tp2_r", 2.0)
    trail_mult = cfg.get("trail_atr_multiplier", 1.0)
    trail_recalc = cfg.get("trail_recalc_candles", 2)

    direction = "BULL" if float(trade.tp1_price) > float(trade.entry_price) else "BEAR"
    entry = float(trade.entry_price)
    sl = float(trade.sl_price)
    tp1 = float(trade.tp1_price)
    tp2 = float(trade.tp2_price)
    dol = float(trade.dol_level)
    tick = atr * 0.0001

    updates: dict = {}

    # --- SL hit check (always first) ---
    if direction == "BULL" and candle_low <= sl:
        logger.info(f"[IFVG] {trade.symbol} SL hit | low={candle_low:.4f} sl={sl:.4f}")
        sl_dist = abs(entry - sl)
        pnl_r = (candle_low - entry) / sl_dist if sl_dist > 0 else -1.0
        return trade.model_copy(update={
            "status": "CLOSED",
            "closed_at": datetime.now(timezone.utc),
            "outcome": "SL",
            "pnl_r": round(pnl_r, 3),
        })

    if direction == "BEAR" and candle_high >= sl:
        logger.info(f"[IFVG] {trade.symbol} SL hit | high={candle_high:.4f} sl={sl:.4f}")
        sl_dist = abs(entry - sl)
        pnl_r = (entry - candle_high) / sl_dist if sl_dist > 0 else -1.0
        return trade.model_copy(update={
            "status": "CLOSED",
            "closed_at": datetime.now(timezone.utc),
            "outcome": "SL",
            "pnl_r": round(pnl_r, 3),
        })

    # --- DOL hit (full exit) ---
    if direction == "BULL" and candle_high >= dol:
        logger.info(f"[IFVG] {trade.symbol} DOL hit | high={candle_high:.4f} dol={dol:.4f}")
        sl_dist = abs(entry - sl)
        pnl_r = (dol - entry) / sl_dist if sl_dist > 0 else 0
        return trade.model_copy(update={
            "status": "CLOSED",
            "closed_at": datetime.now(timezone.utc),
            "outcome": "DOL",
            "pnl_r": round(pnl_r, 3),
        })

    if direction == "BEAR" and candle_low <= dol:
        sl_dist = abs(entry - sl)
        pnl_r = (entry - dol) / sl_dist if sl_dist > 0 else 0
        return trade.model_copy(update={
            "status": "CLOSED",
            "closed_at": datetime.now(timezone.utc),
            "outcome": "DOL",
            "pnl_r": round(pnl_r, 3),
        })

    # --- TP1 (33% partial, move SL to breakeven) ---
    if not trade.tp1_hit:
        if (direction == "BULL" and candle_high >= tp1) or (direction == "BEAR" and candle_low <= tp1):
            logger.info(f"[IFVG] {trade.symbol} TP1 hit — partial close 33%, SL → breakeven+1")
            be_sl = entry + tick if direction == "BULL" else entry - tick
            updates["tp1_hit"] = True
            updates["sl_price"] = Decimal(str(round(be_sl, 8)))
            sl = be_sl  # update local for trailing

    # --- TP2 (33% partial) ---
    if trade.tp1_hit:
        if (direction == "BULL" and candle_high >= tp2) or (direction == "BEAR" and candle_low <= tp2):
            logger.info(f"[IFVG] {trade.symbol} TP2 hit — partial close 33%")
            # After TP2 the remainder trails — no status change yet

    # --- Trailing stop (remaining 34%) ---
    if trade.tp1_hit and candles_since_last_trail >= trail_recalc:
        if direction == "BULL":
            trail_stop = current_price - trail_mult * atr
            if trail_stop > sl:
                updates["sl_price"] = Decimal(str(round(trail_stop, 8)))
                sl = trail_stop
        else:
            trail_stop = current_price + trail_mult * atr
            if trail_stop < sl:
                updates["sl_price"] = Decimal(str(round(trail_stop, 8)))
                sl = trail_stop

        # Check if trail stop hit
        if (direction == "BULL" and candle_low <= sl) or (direction == "BEAR" and candle_high >= sl):
            sl_dist = abs(entry - float(trade.sl_price))
            price_at_exit = sl
            pnl_r = ((price_at_exit - entry) / sl_dist if direction == "BULL"
                     else (entry - price_at_exit) / sl_dist) if sl_dist > 0 else 0
            return trade.model_copy(update={
                **updates,
                "status": "CLOSED",
                "closed_at": datetime.now(timezone.utc),
                "outcome": "TRAIL",
                "pnl_r": round(pnl_r, 3),
            })

    if updates:
        return trade.model_copy(update=updates)
    return trade


def check_daily_loss(
    symbol: str,
    account_balance: float,
    redis_client: redis.Redis,
) -> bool:
    """Return True (halt) if cumulative daily IFVG loss exceeds the configured limit."""
    cfg = _cfg()
    limit_pct = cfg.get("daily_loss_limit_pct", 3.0)
    today = date.today().strftime("%Y%m%d")
    key = f"ifvg:daily_loss:{symbol}:{today}"
    try:
        raw = redis_client.get(key)
        if raw is None:
            return False
        cumulative_loss = abs(float(raw))
        limit = account_balance * (limit_pct / 100)
        if cumulative_loss >= limit:
            logger.warning(
                f"[IFVG] Daily loss limit hit on {symbol} "
                f"(loss={cumulative_loss:.2f}, limit={limit:.2f})"
            )
            return True
    except Exception as e:
        logger.warning(f"Redis daily loss check failed for {symbol}: {e}")
    return False


def record_trade_pnl(
    symbol: str,
    pnl_usd: float,
    redis_client: redis.Redis,
) -> None:
    """Accumulate trade PnL in Redis daily loss tracker (losses only)."""
    if pnl_usd >= 0:
        return
    today = date.today().strftime("%Y%m%d")
    key = f"ifvg:daily_loss:{symbol}:{today}"
    try:
        redis_client.incrbyfloat(key, abs(pnl_usd))
        redis_client.expire(key, 25 * 3600)  # 25h TTL (resets midnight UTC + buffer)
    except Exception as e:
        logger.warning(f"Redis daily loss record failed for {symbol}: {e}")
