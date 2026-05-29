"""
Backtest runner.

CLI usage:
    .\\venv\\Scripts\\python.exe backtest/run.py
    .\\venv\\Scripts\\python.exe backtest/run.py --symbol BTC/USDT:USDT
    .\\venv\\Scripts\\python.exe backtest/run.py --walk-forward
    .\\venv\\Scripts\\python.exe backtest/run.py --months 3 --threshold 0.20

Programmatic usage (from web API):
    from backtest.run import run_backtest
    result = await run_backtest(symbol="BTC/USDT:USDT", months=3)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

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
RESULTS_DIR = Path(__file__).parent / "results"


# ── Strategy stubs (no live feeds in backtest) ────────────────────────────────

class _NullSentiment(BaseStrategy):
    """No RSS/API data in backtest — contributes HOLD to ensemble."""
    name = "sentiment"

    def generate_signal(self, df, symbol=""):
        return {"action": "HOLD", "confidence": 0.0}


class _NullIFVG(BaseStrategy):
    """IFVG requires async multi-TF fetcher — contributes HOLD in backtest."""
    name = "ifvg"

    def generate_signal(self, df, symbol=""):
        return {"action": "HOLD", "confidence": 0.0}


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_csv(symbol: str, timeframe: str, months: int | None) -> pd.DataFrame:
    """Load pre-cached data from ml/data/ (written by ml/train.py)."""
    safe = symbol.replace("/", "_").replace(":", "_")
    path = os.path.join(ML_DATA_DIR, f"{safe}_{timeframe}.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    if months:
        cutoff = df.index.max() - pd.Timedelta(days=months * 30)
        df = df[df.index >= cutoff]
    return df


async def _fetch_live(symbol: str, timeframe: str, months: int) -> pd.DataFrame:
    """Fetch fresh OHLCV from Binance when no cached CSV is available."""
    try:
        from ml.data_collector import DataCollector
        collector = DataCollector()
        data_map = await collector.collect_all([symbol], timeframe, months=months)
        df = data_map.get(symbol, pd.DataFrame())
        if not df.empty:
            logger.info(f"Fetched {len(df)} bars live for {symbol}")
        return df
    except Exception as e:
        logger.warning(f"Live fetch failed for {symbol}: {e}")
        return pd.DataFrame()


async def _get_data(
    symbol: str, timeframe: str, months: int, processor: DataProcessor
) -> pd.DataFrame:
    """Try CSV cache first, fall back to live Binance fetch."""
    df = _load_csv(symbol, timeframe, months)
    if df.empty:
        logger.info(f"No cached data for {symbol} — fetching from Binance...")
        df = await _fetch_live(symbol, timeframe, months)
    if df.empty:
        return df
    df = processor.add_indicators(df.copy())
    return df


# ── Ensemble builder ──────────────────────────────────────────────────────────

def _build_ensemble() -> EnsembleStrategy:
    ensemble = EnsembleStrategy()
    ensemble.register(MomentumStrategy())
    ensemble.register(MeanReversionStrategy())
    ensemble.register(TrendFollowingStrategy())
    ensemble.register(MLXGBoostStrategy())
    ensemble.register(_NullSentiment())
    ensemble.register(_NullIFVG())
    return ensemble


# ── Single run ────────────────────────────────────────────────────────────────

def _run_single(
    df: pd.DataFrame,
    symbol: str,
    ensemble,
    label: str,
    threshold: float = 0.10,
    initial_balance: float = 10_000.0,
    save: bool = True,
) -> dict:
    engine = BacktestEngine(initial_balance=initial_balance, threshold=threshold)
    result = engine.run(df, symbol, ensemble)
    if not result.trades and result.equity_curve.empty:
        logger.warning(f"No trades generated for {label}")
        return {}
    rpt.print_report(result.metrics, label)
    if save:
        rpt.save_equity_curve(result.equity_curve, label)
        rpt.save_trade_log(result.trades, label)
    return {
        "metrics": result.metrics,
        "trades": result.trades,
        "equity": result.equity_curve.tolist() if not result.equity_curve.empty else [],
        "equity_timestamps": [str(t) for t in result.equity_curve.index],
    }


# ── Walk-forward run ──────────────────────────────────────────────────────────

def _run_walk_forward(
    df: pd.DataFrame,
    symbol: str,
    ensemble,
    threshold: float = 0.10,
    initial_balance: float = 10_000.0,
) -> dict:
    """
    Rolling walk-forward: 6-week test windows, 2-week step.
    Tests whether the edge is consistent across different time periods.
    """
    test_bars = 6 * 7 * 24 * 4   # 6 weeks at 15m = 4032 bars
    step_bars = 2 * 7 * 24 * 4   # 2-week step
    min_bars = 300

    n_bars = len(df)
    start = max(min_bars, n_bars - 4 * test_bars)

    window_metrics: list[dict] = []
    window_labels: list[str] = []
    all_trades: list[dict] = []
    equity_parts: list[pd.Series] = []

    i = start
    window_num = 1
    while i + test_bars <= n_bars:
        window_df = df.iloc[i: i + test_bars]
        if len(window_df) < min_bars:
            break

        t_start = window_df.index[0].strftime("%Y-%m-%d")
        t_end   = window_df.index[-1].strftime("%Y-%m-%d")
        label   = f"{symbol} | W{window_num} ({t_start} → {t_end})"

        engine = BacktestEngine(initial_balance=initial_balance, threshold=threshold)
        result = engine.run(window_df, symbol, ensemble)

        if result.trades:
            rpt.print_report(result.metrics, label)
            rpt.save_trade_log(result.trades, label)
            window_metrics.append(result.metrics)
            window_labels.append(f"W{window_num} {t_start}")
            all_trades.extend(result.trades)
            equity_parts.append(result.equity_curve)

        i += step_bars
        window_num += 1

    if not window_metrics:
        logger.warning(f"No walk-forward windows produced trades for {symbol}")
        return {}

    combined_equity = pd.concat(equity_parts) if equity_parts else pd.Series()
    rpt.save_equity_curve(combined_equity, f"{symbol} | Walk-Forward Combined")
    rpt.print_walkforward_summary(window_metrics, window_labels)

    consistency = edge_consistency(window_metrics)
    return {
        "windows": [{"label": l, "metrics": m} for l, m in zip(window_labels, window_metrics)],
        "consistency": consistency,
        "all_trades": all_trades,
        "equity": combined_equity.tolist() if not combined_equity.empty else [],
        "equity_timestamps": [str(t) for t in combined_equity.index],
    }


# ── Public async API (called from web/app.py) ─────────────────────────────────

async def run_backtest(
    symbol: str | None = None,
    months: int = 3,
    walk_forward: bool = False,
    threshold: float = 0.10,
    initial_balance: float = 10_000.0,
) -> dict:
    """
    Programmatic entry point — used by /api/backtest.
    Returns a dict with metrics, trades list, and equity curve.
    """
    params = load_trading_params()
    symbols: list[str] = [symbol] if symbol else params["trading"]["symbols"]
    timeframe: str = params["trading"]["timeframe"]
    processor = DataProcessor()
    ensemble = _build_ensemble()

    results = {}
    started_at = datetime.now(timezone.utc).isoformat()

    for sym in symbols:
        df = await _get_data(sym, timeframe, months, processor)
        if df.empty or len(df) < 300:
            results[sym] = {"error": f"Insufficient data ({len(df)} bars — need 300+)"}
            continue

        logger.info(f"Backtesting {sym} | {len(df)} bars | walk_forward={walk_forward}")

        if walk_forward:
            r = _run_walk_forward(df, sym, ensemble, threshold, initial_balance)
        else:
            label = f"{sym} | Last {months}m"
            r = _run_single(df, sym, ensemble, label, threshold, initial_balance)

        results[sym] = r

    # Save JSON summary to results/
    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    summary = {
        "run_at": started_at,
        "params": {"months": months, "walk_forward": walk_forward, "threshold": threshold},
        "results": {
            sym: {k: v for k, v in r.items() if k not in ("trades", "equity", "equity_timestamps", "all_trades")}
            for sym, r in results.items()
        },
    }
    summary_path = RESULTS_DIR / f"backtest_{ts}.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))
    logger.info(f"Backtest summary saved → {summary_path}")

    return {"started_at": started_at, "results": results, "summary_path": str(summary_path)}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Trading bot backtester")
    parser.add_argument("--symbol",       type=str,   default=None)
    parser.add_argument("--months",       type=int,   default=3)
    parser.add_argument("--walk-forward", action="store_true")
    parser.add_argument("--threshold",    type=float, default=0.10,
                        help="Consensus score threshold (live bot uses 0.30, backtest default 0.10)")
    parser.add_argument("--balance",      type=float, default=10_000.0)
    args = parser.parse_args()

    result = asyncio.run(run_backtest(
        symbol=args.symbol,
        months=args.months,
        walk_forward=args.walk_forward,
        threshold=args.threshold,
        initial_balance=args.balance,
    ))

    for sym, r in result["results"].items():
        if "error" in r:
            print(f"\n{sym}: ERROR — {r['error']}")
        elif "metrics" in r:
            m = r["metrics"]
            print(f"\n{sym}: {m['total_trades']} trades | Return {m['total_return']:+.2%} | Sharpe {m['sharpe']:.2f}")


if __name__ == "__main__":
    main()
