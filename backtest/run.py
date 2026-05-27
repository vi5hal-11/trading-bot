"""
Backtest runner. Usage:

    .\\venv\\Scripts\\python.exe backtest/run.py
    .\\venv\\Scripts\\python.exe backtest/run.py --symbol BTC/USDT:USDT
    .\\venv\\Scripts\\python.exe backtest/run.py --walk-forward
    .\\venv\\Scripts\\python.exe backtest/run.py --months 3
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from loguru import logger

from config.settings import load_trading_params
from data.processor import DataProcessor
from strategies.momentum import MomentumStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.trend_following import TrendFollowingStrategy
from strategies.ml_xgboost import MLXGBoostStrategy
from strategies.base import BaseStrategy
from strategies.ensemble import EnsembleStrategy
from backtest.backtester import BacktestEngine
from backtest import report as rpt
from backtest.metrics import edge_consistency

ML_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "ml", "data")


def _load_csv(symbol: str, timeframe: str, months: int | None) -> pd.DataFrame:
    safe = symbol.replace("/", "_").replace(":", "_")
    path = os.path.join(ML_DATA_DIR, f"{safe}_{timeframe}.csv")
    if not os.path.exists(path):
        logger.warning(f"No cached data for {symbol} at {path}. Run ml/train.py first.")
        return pd.DataFrame()
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    if months:
        cutoff = df.index.max() - pd.Timedelta(days=months * 30)
        df = df[df.index >= cutoff]
    return df


class _NullSentiment(BaseStrategy):
    """Backtest stub: contributes 0 weight to ensemble (no live RSS data available)."""
    name = "sentiment"

    def generate_signal(self, df, symbol=""):
        return {"action": "HOLD", "confidence": 0.0}


def _build_ensemble() -> EnsembleStrategy:
    ensemble = EnsembleStrategy()
    ensemble.register(MomentumStrategy())
    ensemble.register(MeanReversionStrategy())
    ensemble.register(TrendFollowingStrategy())
    ensemble.register(MLXGBoostStrategy())
    ensemble.register(_NullSentiment())
    return ensemble


def _run_single(df: pd.DataFrame, symbol: str, ensemble, label: str, threshold: float = 0.10) -> dict:
    engine = BacktestEngine(initial_balance=10_000.0, threshold=threshold)
    result = engine.run(df, symbol, ensemble)
    if not result.trades and result.equity_curve.empty:
        logger.warning(f"No trades generated for {label}")
        return {}
    rpt.print_report(result.metrics, label)
    rpt.save_equity_curve(result.equity_curve, label)
    rpt.save_trade_log(result.trades, label)
    return result.metrics


def _run_walk_forward(df: pd.DataFrame, symbol: str, ensemble, threshold: float = 0.10) -> None:
    """
    Rolling walk-forward: 6-week test windows, 2-week step.
    Strategy is stateless so no re-training needed per window —
    the key test is whether the edge is consistent across time periods
    (Trading in the Zone: edge must hold across a distribution of trades).
    """
    test_bars = 6 * 7 * 24 * 4   # 6 weeks at 15m = 4032 bars
    step_bars = 2 * 7 * 24 * 4   # 2-week step = 1344 bars
    min_bars = 300                # BacktestEngine WINDOW + buffer

    n_bars = len(df)
    start = n_bars - 4 * test_bars  # use last ~24 weeks for 4 windows
    if start < min_bars:
        start = min_bars

    window_metrics: list[dict] = []
    window_labels: list[str] = []
    combined_equity_parts: list[pd.Series] = []

    i = start
    window_num = 1
    while i + test_bars <= n_bars:
        window_df = df.iloc[i: i + test_bars]
        if len(window_df) < min_bars:
            break

        t_start = window_df.index[0].strftime("%Y-%m-%d")
        t_end = window_df.index[-1].strftime("%Y-%m-%d")
        label = f"{symbol} | W{window_num} ({t_start} → {t_end})"

        engine = BacktestEngine(initial_balance=10_000.0, threshold=threshold)
        result = engine.run(window_df, symbol, ensemble)

        if result.trades:
            rpt.print_report(result.metrics, label)
            rpt.save_trade_log(result.trades, label)
            window_metrics.append(result.metrics)
            window_labels.append(f"W{window_num} {t_start}")
            combined_equity_parts.append(result.equity_curve)

        i += step_bars
        window_num += 1

    if not window_metrics:
        logger.warning(f"No walk-forward windows produced trades for {symbol}")
        return

    # Combined equity curve across all test windows
    if combined_equity_parts:
        combined = pd.concat(combined_equity_parts)
        rpt.save_equity_curve(combined, f"{symbol} | Walk-Forward Combined")

    rpt.print_walkforward_summary(window_metrics, window_labels)


def main():
    parser = argparse.ArgumentParser(description="Trading bot backtester")
    parser.add_argument("--symbol", type=str, default=None, help="Single symbol to test")
    parser.add_argument("--months", type=int, default=None, help="Limit to last N months")
    parser.add_argument("--walk-forward", action="store_true", help="Run walk-forward validation")
    parser.add_argument("--threshold", type=float, default=0.10,
                        help="Consensus score threshold for entry (default 0.10; live bot uses 0.30)")
    args = parser.parse_args()

    params = load_trading_params()
    symbols: list[str] = params["trading"]["symbols"]
    timeframe: str = params["trading"]["timeframe"]

    if args.symbol:
        symbols = [args.symbol]

    processor = DataProcessor()
    ensemble = _build_ensemble()

    logger.info(f"Backtesting {len(symbols)} symbol(s) | timeframe={timeframe} | walk_forward={args.walk_forward}")

    for symbol in symbols:
        df_raw = _load_csv(symbol, timeframe, args.months)
        if df_raw.empty:
            continue

        # Ensure all indicator columns are present
        df = processor.add_indicators(df_raw.copy())
        if df.empty:
            logger.warning(f"Indicator computation returned empty DataFrame for {symbol}")
            continue

        logger.info(f"{symbol}: {len(df)} bars loaded")

        if args.walk_forward:
            _run_walk_forward(df, symbol, ensemble, args.threshold)
        else:
            label = f"{symbol} | Full Period"
            if args.months:
                label = f"{symbol} | Last {args.months}m"
            _run_single(df, symbol, ensemble, label, args.threshold)


if __name__ == "__main__":
    main()
