"""
Parameter grid search over the backtest engine.

Usage:
    .\\venv\\Scripts\\python.exe backtest/optimize.py
    .\\venv\\Scripts\\python.exe backtest/optimize.py --symbol BTC/USDT:USDT
    .\\venv\\Scripts\\python.exe backtest/optimize.py --top 20
"""
import argparse
import itertools
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from loguru import logger

from config.settings import load_trading_params
from data.processor import DataProcessor
from strategies.base import BaseStrategy
from strategies.ensemble import EnsembleStrategy
from strategies.ml_xgboost import MLXGBoostStrategy
from backtest.backtester import BacktestEngine

ML_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "ml", "data")

PARAM_GRID = {
    "backtest_threshold": [0.05, 0.10, 0.15, 0.20],
    "atr_multiplier":     [1.0, 1.5, 2.0, 2.5],
    "rsi_oversold":       [30, 35, 40],
    "rsi_overbought":     [60, 65, 70],
    "adx_threshold":      [20, 25, 28, 30],
}


class _PatchedMomentum(BaseStrategy):
    name = "momentum"

    def __init__(self, rsi_oversold, rsi_overbought):
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought

    def generate_signal(self, df, symbol=""):
        row = df.iloc[-1]
        rsi = row["rsi"]
        macd_hist = row["macd_hist"]
        if rsi < self.rsi_oversold and macd_hist > 0:
            conf = min(1.0, (self.rsi_oversold - rsi) / self.rsi_oversold + 0.4)
            return {"action": "BUY", "confidence": round(conf, 3)}
        if rsi > self.rsi_overbought and macd_hist < 0:
            conf = min(1.0, (rsi - self.rsi_overbought) / (100 - self.rsi_overbought) + 0.4)
            return {"action": "SELL", "confidence": round(conf, 3)}
        return {"action": "HOLD", "confidence": 0.0}


class _PatchedMeanReversion(BaseStrategy):
    name = "mean_reversion"

    def __init__(self, adx_threshold):
        self.adx_threshold = adx_threshold

    def generate_signal(self, df, symbol=""):
        row = df.iloc[-1]
        bb_pct = row["bb_pct"]
        adx = row["adx"]
        if bb_pct < 0.10 and adx > self.adx_threshold:
            conf = min(1.0, 0.3 + (0.10 - bb_pct) * 4)
            return {"action": "BUY", "confidence": round(conf, 3)}
        if bb_pct > 0.90 and adx > self.adx_threshold:
            conf = min(1.0, 0.3 + (bb_pct - 0.90) * 4)
            return {"action": "SELL", "confidence": round(conf, 3)}
        return {"action": "HOLD", "confidence": 0.0}


class _PatchedTrendFollowing(BaseStrategy):
    name = "trend_following"

    def __init__(self, vol_ratio_threshold=1.2):
        self.vol_threshold = vol_ratio_threshold

    def generate_signal(self, df, symbol=""):
        row = df.iloc[-1]
        prev = df.iloc[-2]
        ema_fast = row["ema_12"]
        ema_slow = row["ema_26"]
        prev_ema_fast = prev["ema_12"]
        prev_ema_slow = prev["ema_26"]
        vol_ratio = row["vol_ratio"]
        close = row["close"]
        golden = prev_ema_fast <= prev_ema_slow and ema_fast > ema_slow
        death  = prev_ema_fast >= prev_ema_slow and ema_fast < ema_slow
        high_v = vol_ratio >= self.vol_threshold
        if golden and close > ema_slow and high_v:
            conf = min(1.0, 0.5 + (vol_ratio - self.vol_threshold) * 0.15)
            return {"action": "BUY", "confidence": round(conf, 3)}
        if death and close < ema_slow and high_v:
            conf = min(1.0, 0.5 + (vol_ratio - self.vol_threshold) * 0.15)
            return {"action": "SELL", "confidence": round(conf, 3)}
        return {"action": "HOLD", "confidence": 0.0}


class _NullSentiment(BaseStrategy):
    name = "sentiment"

    def generate_signal(self, df, symbol=""):
        return {"action": "HOLD", "confidence": 0.0}


def _build_ensemble(params: dict) -> EnsembleStrategy:
    ens = EnsembleStrategy()
    ens.register(_PatchedMomentum(params["rsi_oversold"], params["rsi_overbought"]))
    ens.register(_PatchedMeanReversion(params["adx_threshold"]))
    ens.register(_PatchedTrendFollowing())
    ens.register(MLXGBoostStrategy())
    ens.register(_NullSentiment())
    return ens


def _load_df(symbol: str, timeframe: str) -> pd.DataFrame:
    safe = symbol.replace("/", "_").replace(":", "_")
    path = os.path.join(ML_DATA_DIR, f"{safe}_{timeframe}.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def run_grid_search(symbol: str, timeframe: str, top_n: int) -> None:
    processor = DataProcessor()
    df_raw = _load_df(symbol, timeframe)
    if df_raw.empty:
        logger.error(f"No data for {symbol}. Run ml/train.py first.")
        return

    df = processor.add_indicators(df_raw.copy())
    if df.empty:
        return

    logger.info(f"Grid search: {symbol} | {len(df)} bars | sweeping {sum(len(v) for v in PARAM_GRID.values())} param values")

    keys = list(PARAM_GRID.keys())
    combos = list(itertools.product(*[PARAM_GRID[k] for k in keys]))
    total = len(combos)
    logger.info(f"Total combinations: {total}")

    results = []
    for idx, combo in enumerate(combos, 1):
        params = dict(zip(keys, combo))

        # Override atr_multiplier in risk_calculator via monkey-patch
        from trading_engine import risk_calculator as rc_mod
        orig_mult = None
        try:
            risk_inst = rc_mod.RiskCalculator()
            orig_mult = risk_inst.atr_mult
            risk_inst.atr_mult = params["atr_multiplier"]
        except Exception:
            pass

        ensemble = _build_ensemble(params)
        engine = BacktestEngine(initial_balance=10_000.0, threshold=params["backtest_threshold"])

        try:
            result = engine.run(df, symbol, ensemble)
        except Exception as e:
            logger.debug(f"Combo {idx}/{total} failed: {e}")
            continue

        if not result.trades:
            continue

        m = result.metrics
        row = {**params,
               "sharpe":        round(m["sharpe"], 4),
               "sortino":       round(m["sortino"], 4),
               "total_return":  round(m["total_return"], 4),
               "win_rate":      round(m["win_rate"], 4),
               "profit_factor": round(m["profit_factor"], 4),
               "expectancy":    round(m["expectancy"], 6),
               "n_trades":      m["total_trades"],
               "max_drawdown":  round(m["max_drawdown"], 4)}
        results.append(row)

        if idx % 50 == 0:
            logger.info(f"  {idx}/{total} combos done...")

    if not results:
        logger.warning("No valid results from grid search.")
        return

    df_res = pd.DataFrame(results).sort_values("sharpe", ascending=False)

    # Save CSV
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    safe = symbol.replace("/", "_").replace(":", "_")
    csv_path = out_dir / f"optimize_{safe}.csv"
    df_res.to_csv(csv_path, index=False)
    print(f"\nFull results saved -> {csv_path}")

    # Print top N
    print(f"\n{'='*72}")
    print(f"  Top {top_n} parameter sets for {symbol} (by Sharpe ratio)")
    print(f"{'='*72}")
    cols = ["backtest_threshold", "atr_multiplier", "rsi_oversold", "adx_threshold",
            "sharpe", "win_rate", "profit_factor", "expectancy", "n_trades"]
    top = df_res.head(top_n)[cols]
    print(top.to_string(index=False))
    print(f"{'='*72}\n")

    best = df_res.iloc[0]
    print(f"Best params: threshold={best['backtest_threshold']} | atr={best['atr_multiplier']} | "
          f"rsi_os={best['rsi_oversold']} | adx={best['adx_threshold']}")
    print(f"Best Sharpe: {best['sharpe']:.4f} | WinRate: {best['win_rate']:.1%} | "
          f"ProfitFactor: {best['profit_factor']:.3f}\n")


def main():
    parser = argparse.ArgumentParser(description="Backtest parameter grid search")
    parser.add_argument("--symbol", type=str, default=None)
    parser.add_argument("--top", type=int, default=10, help="Show top N results")
    args = parser.parse_args()

    params = load_trading_params()
    symbols: list[str] = params["trading"]["symbols"]
    timeframe: str = params["trading"]["timeframe"]

    if args.symbol:
        symbols = [args.symbol]

    for symbol in symbols:
        run_grid_search(symbol, timeframe, args.top)


if __name__ == "__main__":
    main()
