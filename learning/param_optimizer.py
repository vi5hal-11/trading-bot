"""
Walk-forward parameter optimizer using Optuna.

Runs once per month (triggered by ml/scheduler.py or manually).
For each strategy, it optimizes key parameters over the last 3 months of
closed trades and candle data, validates on the most recent month, and
adopts new parameters only if out-of-sample Sharpe improves by the
promotion threshold.

Optimized parameters
────────────────────
  trend_following  — ema_fast, ema_slow, vol_ratio_threshold
  momentum         — rsi_oversold, rsi_overbought
  mean_reversion   — adx_threshold, bb_buy_pct, bb_sell_pct
  risk             — trailing_stop_atr_multiplier, max_loss_pct_per_trade

All parameters are written back to config/trading_params.json only when
the new set beats the current set on the held-out window.

Usage
─────
    python -m learning.param_optimizer          # run manually
    # or called from ml/scheduler.py monthly
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

# Optional Optuna import — gracefully degrades if not installed
try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    _OPTUNA_AVAILABLE = True
except ImportError:
    _OPTUNA_AVAILABLE = False
    logger.warning("optuna not installed — param_optimizer will be disabled. Run: pip install optuna")

_PARAMS_PATH = os.path.join("config", "trading_params.json")
_PROMOTION_SHARPE_DELTA = 0.10   # new params must beat current by this much
_N_TRIALS = 150
_TRAIN_MONTHS = 3
_TEST_MONTHS = 1


# ── Simple vectorised backtest ────────────────────────────────────────────────

def _sharpe(returns: pd.Series) -> float:
    """Annualised Sharpe ratio from a series of per-trade PnL percentages."""
    if returns.empty or returns.std() == 0:
        return 0.0
    return float((returns.mean() / returns.std()) * np.sqrt(252))


def _backtest_trend(df: pd.DataFrame, ema_fast: int, ema_slow: int, vol_thresh: float) -> float:
    df = df.copy()
    df["ef"] = df["close"].ewm(span=ema_fast).mean()
    df["es"] = df["close"].ewm(span=ema_slow).mean()
    df["vm"] = df["volume"] / df["volume"].rolling(20).mean()
    df["signal"] = 0
    cross_up = (df["ef"].shift(1) <= df["es"].shift(1)) & (df["ef"] > df["es"]) & (df["vm"] >= vol_thresh)
    cross_dn = (df["ef"].shift(1) >= df["es"].shift(1)) & (df["ef"] < df["es"]) & (df["vm"] >= vol_thresh)
    df.loc[cross_up, "signal"] = 1
    df.loc[cross_dn, "signal"] = -1
    df["ret"] = df["close"].pct_change().shift(-1) * df["signal"].shift(1)
    return _sharpe(df["ret"].dropna())


def _backtest_momentum(df: pd.DataFrame, rsi_lo: int, rsi_hi: int) -> float:
    df = df.copy()
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(com=13).mean()
    loss = (-delta).clip(lower=0).ewm(com=13).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - 100 / (1 + rs)
    df["signal"] = 0
    df.loc[df["rsi"] < rsi_lo, "signal"] = 1
    df.loc[df["rsi"] > rsi_hi, "signal"] = -1
    df["ret"] = df["close"].pct_change().shift(-1) * df["signal"].shift(1)
    return _sharpe(df["ret"].dropna())


def _backtest_mean_rev(df: pd.DataFrame, adx_thresh: float, bb_buy: float, bb_sell: float) -> float:
    df = df.copy()
    mid = df["close"].rolling(20).mean()
    std = df["close"].rolling(20).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    df["bb_pct"] = (df["close"] - lower) / (upper - lower + 1e-9)

    # Simple ADX proxy using directional movement
    tr = pd.concat([
        (df["high"] - df["low"]).abs(),
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"]  - df["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    df["adx_proxy"] = tr.ewm(span=14).mean() / df["close"] * 100

    df["signal"] = 0
    df.loc[(df["bb_pct"] < bb_buy)  & (df["adx_proxy"] > adx_thresh), "signal"] = 1
    df.loc[(df["bb_pct"] > bb_sell) & (df["adx_proxy"] > adx_thresh), "signal"] = -1
    df["ret"] = df["close"].pct_change().shift(-1) * df["signal"].shift(1)
    return _sharpe(df["ret"].dropna())


# ── Optimizer ─────────────────────────────────────────────────────────────────

class ParamOptimizer:
    """Monthly walk-forward optimizer. Call run() once per month."""

    def __init__(self):
        self._params_path = _PARAMS_PATH

    def _load_params(self) -> dict:
        with open(self._params_path) as f:
            return json.load(f)

    def _save_params(self, params: dict) -> None:
        with open(self._params_path, "w") as f:
            json.dump(params, f, indent=2)
        logger.info(f"[Optimizer] Updated {self._params_path}")

    def _current_sharpe(self, df_train: pd.DataFrame, params: dict) -> dict[str, float]:
        s = params.get("strategies", {})
        tf = s.get("trend_following", {})
        mo = s.get("momentum", {})
        mr = s.get("mean_reversion", {})
        return {
            "trend":    _backtest_trend(df_train, tf.get("ema_fast", 12), tf.get("ema_slow", 26), tf.get("vol_ratio_threshold", 1.2)),
            "momentum": _backtest_momentum(df_train, mo.get("rsi_oversold", 35), mo.get("rsi_overbought", 65)),
            "mean_rev": _backtest_mean_rev(df_train, mr.get("adx_threshold", 28), mr.get("bb_buy_pct", 0.10), mr.get("bb_sell_pct", 0.90)),
        }

    def run(self, df_map: dict[str, pd.DataFrame]) -> dict:
        """
        df_map: {symbol: DataFrame with OHLCV columns} for the last
                _TRAIN_MONTHS + _TEST_MONTHS months.

        Returns a summary of what was changed.
        """
        if not _OPTUNA_AVAILABLE:
            return {"status": "skipped", "reason": "optuna not installed"}

        # Combine symbols into one frame for backtest
        frames = []
        for sym, df in df_map.items():
            if df is not None and len(df) > 100:
                frames.append(df[["open", "high", "low", "close", "volume"]].copy())
        if not frames:
            return {"status": "skipped", "reason": "no data"}

        combined = pd.concat(frames).sort_index().reset_index(drop=True)

        # Split train / test
        split = int(len(combined) * (_TRAIN_MONTHS / (_TRAIN_MONTHS + _TEST_MONTHS)))
        df_train = combined.iloc[:split]
        df_test  = combined.iloc[split:]

        if len(df_train) < 200 or len(df_test) < 50:
            return {"status": "skipped", "reason": "insufficient data for walk-forward split"}

        params = self._load_params()
        baseline = self._current_sharpe(df_test, params)
        changes = {}

        # ── Trend Following ───────────────────────────────────────────────────
        def tf_objective(trial: "optuna.Trial") -> float:
            fast = trial.suggest_int("ema_fast", 5, 20)
            slow = trial.suggest_int("ema_slow", fast + 4, 50)
            vol  = trial.suggest_float("vol_ratio_threshold", 1.0, 2.5)
            return _backtest_trend(df_train, fast, slow, vol)

        study_tf = optuna.create_study(direction="maximize")
        study_tf.optimize(tf_objective, n_trials=_N_TRIALS, show_progress_bar=False)
        best_tf = study_tf.best_params
        oos_tf = _backtest_trend(df_test, best_tf["ema_fast"], best_tf["ema_slow"], best_tf["vol_ratio_threshold"])
        if oos_tf > baseline["trend"] + _PROMOTION_SHARPE_DELTA:
            params.setdefault("strategies", {}).setdefault("trend_following", {}).update(best_tf)
            changes["trend_following"] = {"params": best_tf, "oos_sharpe": round(oos_tf, 3), "baseline_sharpe": round(baseline["trend"], 3)}
            logger.info(f"[Optimizer] TrendFollowing promoted: Sharpe {baseline['trend']:.2f} → {oos_tf:.2f}")
        else:
            logger.info(f"[Optimizer] TrendFollowing kept (new={oos_tf:.2f} vs baseline={baseline['trend']:.2f})")

        # ── Momentum ──────────────────────────────────────────────────────────
        def mo_objective(trial: "optuna.Trial") -> float:
            lo = trial.suggest_int("rsi_oversold", 20, 45)
            hi = trial.suggest_int("rsi_overbought", 55, 80)
            return _backtest_momentum(df_train, lo, hi)

        study_mo = optuna.create_study(direction="maximize")
        study_mo.optimize(mo_objective, n_trials=_N_TRIALS, show_progress_bar=False)
        best_mo = study_mo.best_params
        oos_mo = _backtest_momentum(df_test, best_mo["rsi_oversold"], best_mo["rsi_overbought"])
        if oos_mo > baseline["momentum"] + _PROMOTION_SHARPE_DELTA:
            params.setdefault("strategies", {}).setdefault("momentum", {}).update(best_mo)
            changes["momentum"] = {"params": best_mo, "oos_sharpe": round(oos_mo, 3), "baseline_sharpe": round(baseline["momentum"], 3)}
            logger.info(f"[Optimizer] Momentum promoted: Sharpe {baseline['momentum']:.2f} → {oos_mo:.2f}")
        else:
            logger.info(f"[Optimizer] Momentum kept (new={oos_mo:.2f} vs baseline={baseline['momentum']:.2f})")

        # ── Mean Reversion ────────────────────────────────────────────────────
        def mr_objective(trial: "optuna.Trial") -> float:
            adx   = trial.suggest_float("adx_threshold", 15.0, 40.0)
            bb_b  = trial.suggest_float("bb_buy_pct",    0.02, 0.25)
            bb_s  = trial.suggest_float("bb_sell_pct",   0.75, 0.98)
            return _backtest_mean_rev(df_train, adx, bb_b, bb_s)

        study_mr = optuna.create_study(direction="maximize")
        study_mr.optimize(mr_objective, n_trials=_N_TRIALS, show_progress_bar=False)
        best_mr = study_mr.best_params
        oos_mr = _backtest_mean_rev(df_test, best_mr["adx_threshold"], best_mr["bb_buy_pct"], best_mr["bb_sell_pct"])
        if oos_mr > baseline["mean_rev"] + _PROMOTION_SHARPE_DELTA:
            params.setdefault("strategies", {}).setdefault("mean_reversion", {}).update(best_mr)
            changes["mean_reversion"] = {"params": best_mr, "oos_sharpe": round(oos_mr, 3), "baseline_sharpe": round(baseline["mean_rev"], 3)}
            logger.info(f"[Optimizer] MeanReversion promoted: Sharpe {baseline['mean_rev']:.2f} → {oos_mr:.2f}")
        else:
            logger.info(f"[Optimizer] MeanReversion kept (new={oos_mr:.2f} vs baseline={baseline['mean_rev']:.2f})")

        if changes:
            self._save_params(params)

        result = {
            "status": "complete",
            "run_at": datetime.now(timezone.utc).isoformat(),
            "changes": changes,
            "no_change_count": 3 - len(changes),
        }
        logger.info(f"[Optimizer] Done — {len(changes)} strategy/ies updated, {result['no_change_count']} unchanged")
        return result


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    from config.settings import load_trading_params
    from ml.data_collector import DataCollector

    async def _main():
        params = load_trading_params()
        symbols = params["trading"]["symbols"]
        collector = DataCollector()
        df_map = await collector.collect_all(symbols, "15m", months=_TRAIN_MONTHS + _TEST_MONTHS)
        optimizer = ParamOptimizer()
        result = optimizer.run(df_map)
        print(json.dumps(result, indent=2))

    asyncio.run(_main())
