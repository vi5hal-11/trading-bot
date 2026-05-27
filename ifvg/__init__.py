"""IFVG strategy async cycle — called once per symbol per main loop iteration."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import redis
from loguru import logger

from config.settings import load_trading_params
from data.fetcher import BlofinDataFetcher
from data.storage import Storage
from ifvg.bias_engine import get_4h_bias
from ifvg.confluence import score_setup
from ifvg.displacement import check_displacement
from ifvg.entry_manager import manage_entry
from ifvg.ifvg_scanner import find_ifvg
from ifvg.invalidation import should_cancel_entry
from ifvg.models import IFVGZone, TradeState
from ifvg.risk_manager import check_daily_loss, record_trade_pnl, update_trade
from ifvg.session_gate import is_blackout_active, is_killzone_active, register_shock_candle
from ifvg.structure_filter import check_1h_structure, get_active_pools
from ifvg.sweep_detector import detect_sweep


def _cfg() -> dict:
    return load_trading_params().get("ifvg", {})


def _compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Compute ATR from OHLCV DataFrame."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    return float(atr) if not pd.isna(atr) else 0.0


# Per-symbol in-memory state (survives across loop iterations within a process)
_active_zones: dict[str, IFVGZone] = {}
_active_trades: dict[str, TradeState] = {}
_candles_since_trail: dict[str, int] = {}

# Signal cache read by IFVGStrategy.generate_signal()
_signal_cache: dict[str, dict] = {}


def get_cached_signal(symbol: str) -> dict:
    """Return the last computed IFVG signal for a symbol (default HOLD)."""
    return _signal_cache.get(symbol, {"action": "HOLD", "confidence": 0.0})


async def run_ifvg_cycle(
    symbol: str,
    fetcher: BlofinDataFetcher,
    redis_client: redis.Redis,
    storage: Optional[Storage],
    account_balance: float,
) -> None:
    """Run one IFVG analysis + trade-management cycle for a symbol.

    Fetches 4H / 1H / 15M candles asynchronously, walks through the full
    pipeline, and updates module-level state dictionaries.
    """
    cfg = _cfg()
    confluence_min = cfg.get("confluence", {}).get("min_score", 4)

    now = datetime.now(timezone.utc)

    # ── Session gate ──────────────────────────────────────────────────────────
    kz_active, kz_name = is_killzone_active(now)
    if not kz_active:
        logger.debug(f"[IFVG] {symbol} — outside killzone, skipping")
        return

    if is_blackout_active(symbol, redis_client):
        logger.info(f"[IFVG] {symbol} — blackout active, skipping")
        return

    # ── Daily loss guard ──────────────────────────────────────────────────────
    if check_daily_loss(symbol, account_balance, redis_client):
        logger.info(f"[IFVG] {symbol} — daily loss limit hit, skipping")
        return

    # ── Fetch multi-timeframe candles ─────────────────────────────────────────
    try:
        df_4h, df_1h, df_15m = await asyncio.gather(
            fetcher.fetch_ohlcv(symbol, "4h", limit=100),
            fetcher.fetch_ohlcv(symbol, "1h", limit=100),
            fetcher.fetch_ohlcv(symbol, "15m", limit=200),
        )
    except Exception as e:
        logger.warning(f"[IFVG] {symbol} — candle fetch failed: {e}")
        return

    if df_15m.empty or df_1h.empty or df_4h.empty:
        return

    atr_15m = _compute_atr(df_15m)
    if atr_15m <= 0:
        return

    last_candle = df_15m.iloc[-2]  # last *closed* candle
    candle_high = float(last_candle["high"])
    candle_low = float(last_candle["low"])
    current_price = float(df_15m["close"].iloc[-1])

    # Shock candle check
    register_shock_candle(symbol, candle_high, candle_low, atr_15m, redis_client)

    # ── Correlated candles for SMT ────────────────────────────────────────────
    corr_symbols: dict[str, str] = {}
    for s in ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]:
        if s != symbol:
            corr_symbols[s] = s

    correlated_candles: dict[str, pd.DataFrame] = {}
    for s in corr_symbols:
        try:
            correlated_candles[s] = await fetcher.fetch_ohlcv(s, "15m", limit=10)
        except Exception:
            pass

    # ── Existing trade management ─────────────────────────────────────────────
    existing_trade = _active_trades.get(symbol)
    if existing_trade and existing_trade.status == "OPEN":
        trail_count = _candles_since_trail.get(symbol, 0) + 1
        _candles_since_trail[symbol] = trail_count

        updated = update_trade(
            existing_trade, candle_high, candle_low, current_price, atr_15m, trail_count
        )
        _active_trades[symbol] = updated

        if updated.status == "CLOSED":
            logger.info(
                f"[IFVG] {symbol} trade closed | outcome={updated.outcome} pnl_r={updated.pnl_r}"
            )
            pnl_usd = float(updated.pnl_r or 0) * float(updated.risk_amount)
            record_trade_pnl(symbol, pnl_usd, redis_client)
            _signal_cache[symbol] = {
                "action": "SELL" if updated.outcome == "SL" else "HOLD",
                "confidence": 0.5,
                "ifvg_outcome": updated.outcome,
                "pnl_r": updated.pnl_r,
            }
            _active_trades.pop(symbol, None)
            _candles_since_trail.pop(symbol, None)
        return

    # ── Zone invalidation check ───────────────────────────────────────────────
    active_zone = _active_zones.get(symbol)
    pending_trade = _active_trades.get(symbol)

    if active_zone:
        candle_close = float(df_15m["close"].iloc[-2])
        if pending_trade and pending_trade.status in ("PENDING_A", "PENDING_B"):
            cancel, reason = should_cancel_entry(pending_trade, active_zone, candle_close, now)
            if cancel:
                logger.info(f"[IFVG] {symbol} — pending entry cancelled: {reason}")
                _active_zones.pop(symbol, None)
                _active_trades.pop(symbol, None)
                return
        elif not pending_trade:
            from ifvg.invalidation import check_zone_validity
            zone_reason = check_zone_validity(active_zone, candle_close, now)
            if zone_reason:
                logger.info(f"[IFVG] {symbol} — zone invalidated: {zone_reason}")
                _active_zones.pop(symbol, None)

    # ── Pending entry progression ─────────────────────────────────────────────
    if pending_trade and pending_trade.status in ("PENDING_A", "PENDING_B"):
        active_zone = _active_zones.get(symbol)
        if active_zone is None:
            _active_trades.pop(symbol, None)
            return

        pools = get_active_pools(df_1h, now)
        updated_trade = manage_entry(
            symbol=symbol,
            ifvg=active_zone,
            sweep=None,  # not needed for progression
            score=None,
            candles_15m=df_15m,
            account_balance=account_balance,
            atr=atr_15m,
            pools=pools,
            existing_trade=pending_trade,
        )
        if updated_trade is None:
            logger.info(f"[IFVG] {symbol} — entry expired")
            _active_zones.pop(symbol, None)
            _active_trades.pop(symbol, None)
        elif updated_trade.status == "OPEN":
            logger.info(f"[IFVG] {symbol} — Mode B confirmed, trade now OPEN")
            _active_trades[symbol] = updated_trade
            _candles_since_trail[symbol] = 0
            _signal_cache[symbol] = {
                "action": "BUY" if active_zone.direction == "BULL" else "SELL",
                "confidence": 0.65,
                "ifvg_mode": "B",
            }
        else:
            _active_trades[symbol] = updated_trade
        return

    # ── New setup detection ───────────────────────────────────────────────────
    if active_zone or existing_trade:
        return  # already has a setup, wait

    bias = get_4h_bias(df_4h)
    if bias.direction == "NONE":
        logger.debug(f"[IFVG] {symbol} — no 4H bias")
        return

    structure_ok = check_1h_structure(df_1h, bias)
    pools = get_active_pools(df_1h, now)

    sweep = detect_sweep(df_15m, pools, atr_15m, symbol)
    if sweep is None:
        return

    displacement = check_displacement(df_15m, sweep, atr_15m)
    if displacement is None:
        return

    ifvg = find_ifvg(df_15m, sweep, displacement, symbol)
    if ifvg is None:
        return

    score = score_setup(
        bias_4h=bias,
        structure_ok=structure_ok,
        sweep=sweep,
        displacement=displacement,
        ifvg=ifvg,
        candles_1h=df_1h,
        correlated_candles=correlated_candles,
        atr=atr_15m,
    )

    if score.total < confluence_min:
        logger.info(
            f"[IFVG] {symbol} — confluence too low ({score.total}/{confluence_min}), skipping"
        )
        return

    trade_state = manage_entry(
        symbol=symbol,
        ifvg=ifvg,
        sweep=sweep,
        score=score,
        candles_15m=df_15m,
        account_balance=account_balance,
        atr=atr_15m,
        pools=pools,
        existing_trade=None,
    )

    if trade_state is None:
        return

    _active_zones[symbol] = ifvg
    _active_trades[symbol] = trade_state

    direction = ifvg.direction
    confidence = min(1.0, score.total / 6)
    _signal_cache[symbol] = {
        "action": "BUY" if direction == "BULL" else "SELL",
        "confidence": round(confidence, 3),
        "ifvg_mode": "A",
        "confluence": score.total,
        "breakdown": score.breakdown,
        "zone_ce": float(ifvg.ce),
        "zone_direction": direction,
        "sl": float(trade_state.sl_price),
        "tp1": float(trade_state.tp1_price),
        "tp2": float(trade_state.tp2_price),
        "dol": float(trade_state.dol_level),
        "killzone": kz_name,
    }
    logger.info(
        f"[IFVG] {symbol} — new setup | dir={direction} conf={confidence:.2f} "
        f"score={score.total}/6 mode=A zone={kz_name}"
    )
