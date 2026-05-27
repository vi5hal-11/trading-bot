"""6-point confluence scoring for IFVG setups."""
import pandas as pd
from loguru import logger
from config.settings import load_trading_params
from ifvg.models import Bias, ConfluenceScore, DisplacementEvent, IFVGZone, SweepEvent


def _cfg() -> dict:
    return load_trading_params().get("ifvg", {}).get("confluence", {})


def _find_order_blocks(candles_1h: pd.DataFrame, lookback: int = 20) -> list[dict]:
    """Find the last opposing candle before a strong 1H move (Order Block definition)."""
    obs = []
    df = candles_1h.iloc[-lookback:]
    for i in range(1, len(df) - 1):
        curr_close = float(df["close"].iloc[i])
        curr_open = float(df["open"].iloc[i])
        next_close = float(df["close"].iloc[i + 1])

        body = abs(curr_close - curr_open)
        next_body = abs(next_close - float(df["open"].iloc[i + 1]))

        # Bullish OB: bearish candle followed by a strong bullish move
        if curr_close < curr_open and next_close > float(df["open"].iloc[i + 1]) and next_body > body * 1.5:
            obs.append({"type": "BULL", "high": float(df["high"].iloc[i]), "low": float(df["low"].iloc[i])})

        # Bearish OB: bullish candle followed by a strong bearish move
        elif curr_close > curr_open and next_close < float(df["open"].iloc[i + 1]) and next_body > body * 1.5:
            obs.append({"type": "BEAR", "high": float(df["high"].iloc[i]), "low": float(df["low"].iloc[i])})

    return obs


def check_smt(
    sweep: SweepEvent,
    correlated_candles: dict[str, pd.DataFrame],
    smt_window: int = 1,
) -> bool:
    """Return True if SMT divergence exists between the swept symbol and a correlated asset."""
    # Determine which correlated asset to check
    sym = sweep.symbol.upper()
    corr_sym = None
    if "BTC" in sym:
        corr_sym = next((k for k in correlated_candles if "ETH" in k.upper()), None)
    elif "ETH" in sym or "SOL" in sym:
        corr_sym = next((k for k in correlated_candles if "BTC" in k.upper()), None)

    if corr_sym is None or corr_sym not in correlated_candles:
        return False

    corr_df = correlated_candles[corr_sym]
    if len(corr_df) < 3:
        return False

    # Get recent highs/lows of the correlated asset
    recent_corr_high = float(corr_df["high"].iloc[-smt_window - 2: -2].max())
    recent_corr_low = float(corr_df["low"].iloc[-smt_window - 2: -2].min())
    last_corr_high = float(corr_df["high"].iloc[-2])
    last_corr_low = float(corr_df["low"].iloc[-2])

    # BSL sweep primary but correlated did NOT make new high → divergence
    if sweep.direction == "BSL_SWEEP":
        return last_corr_high < recent_corr_high

    # SSL sweep primary but correlated did NOT make new low → divergence
    if sweep.direction == "SSL_SWEEP":
        return last_corr_low > recent_corr_low

    return False


def score_setup(
    bias_4h: Bias,
    structure_ok: bool,
    sweep: SweepEvent,
    displacement: DisplacementEvent,
    ifvg: IFVGZone,
    candles_1h: pd.DataFrame,
    correlated_candles: dict[str, pd.DataFrame],
    atr: float,
) -> ConfluenceScore:
    """Score an IFVG setup on a 0–6 scale. Each condition awards 1 point."""
    cfg = _cfg()
    strong_sweep_ticks = cfg.get("strong_sweep_ticks", 5)
    strong_disp_mult = cfg.get("strong_displacement_multiplier", 2.0)
    smt_window = load_trading_params().get("ifvg", {}).get("ifvg_zone", {}).get("smt_window_candles", 1)

    breakdown: dict[str, bool] = {}

    # 1. 4H bias confirmed
    breakdown["bias_confirmed"] = bias_4h.direction != "NONE"

    # 2. 1H BOS/MSS confirmed
    breakdown["structure_ok"] = structure_ok

    # 3. Strong sweep (extension >= strong_sweep_ticks × 0.0001)
    strong_sweep_threshold = strong_sweep_ticks * 0.0001
    breakdown["strong_sweep"] = sweep.extension_pct >= strong_sweep_threshold

    # 4. Strong displacement (atr_ratio >= multiplier)
    breakdown["strong_displacement"] = displacement.atr_ratio >= strong_disp_mult

    # 5. IFVG aligns with 1H Order Block (overlap within 0.2%)
    obs = _find_order_blocks(candles_1h)
    ob_aligned = False
    tolerance = 0.002
    for ob in obs:
        if ob["type"] == ifvg.direction:
            ob_mid = (ob["high"] + ob["low"]) / 2
            ifvg_mid = float(ifvg.ce)
            if abs(ob_mid - ifvg_mid) / ifvg_mid <= tolerance:
                ob_aligned = True
                break
    breakdown["ob_aligned"] = ob_aligned

    # 6. SMT divergence present
    breakdown["smt_divergence"] = check_smt(sweep, correlated_candles, smt_window)

    total = sum(breakdown.values())
    logger.debug(f"[IFVG] Confluence score={total}/6 | {breakdown}")
    return ConfluenceScore(total=total, breakdown=breakdown)
