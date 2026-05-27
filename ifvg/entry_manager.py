"""Dual-mode entry logic: CE limit (Mode A) → confirmation fallback (Mode B)."""
from decimal import Decimal
from typing import Optional
import pandas as pd
from loguru import logger
from config.settings import load_trading_params
from ifvg.models import ConfluenceScore, IFVGZone, LiquidityPool, SweepEvent, TradeState


def _cfg() -> dict:
    return load_trading_params().get("ifvg", {})


def _find_dol(
    ifvg: IFVGZone,
    pools: list[LiquidityPool],
    sl_dist: float,
    dol_min_r: float,
) -> Optional[float]:
    """Find nearest opposing liquidity pool at minimum R distance from entry."""
    ce = float(ifvg.ce)
    opposing_side = "BSL" if ifvg.direction == "BULL" else "SSL"
    candidates = [float(p.level) for p in pools if p.side == opposing_side]
    if not candidates:
        return None

    min_dist = dol_min_r * sl_dist
    if ifvg.direction == "BULL":
        valid = [c for c in candidates if c > ce + min_dist]
        return min(valid) if valid else None
    else:
        valid = [c for c in candidates if c < ce - min_dist]
        return max(valid) if valid else None


def manage_entry(
    symbol: str,
    ifvg: IFVGZone,
    sweep: SweepEvent,
    score: ConfluenceScore,
    candles_15m: pd.DataFrame,
    account_balance: float,
    atr: float,
    pools: list[LiquidityPool],
    existing_trade: Optional[TradeState] = None,
) -> Optional[TradeState]:
    """Compute the desired trade state for Mode A (CE limit) entry.

    Does NOT place orders directly — returns TradeState for the main loop to act on.
    Mode B (confirmation) is signalled via returned status='PENDING_B'.
    """
    cfg = _cfg()
    risk_cfg = cfg.get("risk", {})
    entry_cfg = cfg.get("entry", {})

    risk_pct = risk_cfg.get("risk_pct", 1.0)
    sl_atr_mult = risk_cfg.get("sl_atr_multiplier", 1.5)
    tp1_r = risk_cfg.get("tp1_r", 1.0)
    tp2_r = risk_cfg.get("tp2_r", 2.0)
    dol_min_r = risk_cfg.get("dol_min_r", 2.0)
    mode_switch = entry_cfg.get("mode_switch_candles", 5)
    total_expiry = entry_cfg.get("total_expiry_candles", 10)
    wick_body_ratio = entry_cfg.get("confirmation_wick_body_ratio", 1.5)

    ce = float(ifvg.ce)
    sweep_extreme = float(sweep.sweep_extreme)
    direction = ifvg.direction  # "BULL" or "BEAR"

    # --- Mode B progression: check existing pending trade ---
    if existing_trade and existing_trade.status in ("PENDING_A", "PENDING_B"):
        candles_since = existing_trade.candles_since_entry + 1

        if candles_since > total_expiry:
            logger.info(f"[IFVG] {symbol} — entry expired after {total_expiry} candles")
            return None

        # Switch from Mode A to Mode B after mode_switch candles
        if existing_trade.status == "PENDING_A" and candles_since >= mode_switch:
            logger.info(f"[IFVG] {symbol} — switching to Mode B confirmation entry")
            return existing_trade.model_copy(update={
                "status": "PENDING_B",
                "candles_since_entry": candles_since,
            })

        # Mode B: check for rejection candle inside zone
        if existing_trade.status == "PENDING_B":
            last_c = candles_15m.iloc[-2]
            c_open = float(last_c["open"])
            c_close = float(last_c["close"])
            c_high = float(last_c["high"])
            c_low = float(last_c["low"])
            body = abs(c_close - c_open)
            wick = (c_high - c_low) - body

            inside_zone = float(ifvg.zone_low) <= c_close <= float(ifvg.zone_high)
            rejection = wick / body >= wick_body_ratio if body > 0 else False
            is_bull_rejection = direction == "BULL" and c_close > c_open and rejection
            is_bear_rejection = direction == "BEAR" and c_close < c_open and rejection

            if inside_zone and (is_bull_rejection or is_bear_rejection):
                logger.info(f"[IFVG] {symbol} — Mode B rejection confirmed, triggering market entry")
                return existing_trade.model_copy(update={
                    "status": "OPEN",
                    "entry_mode": "CONFIRM",
                    "candles_since_entry": candles_since,
                })

        return existing_trade.model_copy(update={"candles_since_entry": candles_since})

    # --- New Mode A entry ---
    # Calculate SL: 1 tick beyond sweep extreme
    tick = atr * 0.0001
    if direction == "BULL":
        sl = sweep_extreme - tick
    else:
        sl = sweep_extreme + tick

    sl_dist = abs(ce - sl)
    if sl_dist <= 0:
        logger.debug(f"[IFVG] {symbol} — zero SL distance, skipping")
        return None

    # SL width check
    if sl_dist > sl_atr_mult * atr:
        logger.info(f"[IFVG] {symbol} — SL too wide ({sl_dist:.4f} > {sl_atr_mult}×ATR={sl_atr_mult * atr:.4f})")
        return None

    # DOL check
    dol = _find_dol(ifvg, pools, sl_dist, dol_min_r)
    if dol is None:
        logger.info(f"[IFVG] {symbol} — no valid DOL at ≥{dol_min_r}R distance, skipping")
        return None

    # TP levels
    if direction == "BULL":
        tp1 = ce + tp1_r * sl_dist
        tp2 = ce + tp2_r * sl_dist
    else:
        tp1 = ce - tp1_r * sl_dist
        tp2 = ce - tp2_r * sl_dist

    # Position sizing
    risk_amount = account_balance * (risk_pct / 100)
    position_size = risk_amount / sl_dist if sl_dist > 0 else 0

    if position_size <= 0:
        return None

    logger.info(
        f"[IFVG] {symbol} — Mode A entry | {direction} CE={ce:.4f} "
        f"SL={sl:.4f} TP1={tp1:.4f} TP2={tp2:.4f} DOL={dol:.4f} "
        f"size={position_size:.6f} risk=${risk_amount:.2f}"
    )

    return TradeState(
        symbol=symbol,
        entry_price=Decimal(str(round(ce, 8))),
        sl_price=Decimal(str(round(sl, 8))),
        tp1_price=Decimal(str(round(tp1, 8))),
        tp2_price=Decimal(str(round(tp2, 8))),
        dol_level=Decimal(str(round(dol, 8))),
        position_size=Decimal(str(round(position_size, 8))),
        risk_amount=Decimal(str(round(risk_amount, 4))),
        status="PENDING_A",
        entry_mode="LIMIT",
        candles_since_entry=0,
    )
