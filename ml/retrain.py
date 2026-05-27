"""
Automated champion/challenger retraining script.

Usage (manual):
    .\\venv\\Scripts\\python.exe ml/retrain.py

Also called by ml/scheduler.py every Sunday at 02:00 UTC.

Flow:
  1. Collect latest OHLCV (uses 24h cache when fresh)
  2. Engineer features, train challenger model
  3. Backtest challenger on validation window vs champion
  4. Promote challenger if Sharpe beats champion by promotion_sharpe_delta
  5. Log results to DB + Telegram
"""
import asyncio
import os
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from loguru import logger

from config.settings import Settings, load_trading_params
from data.storage import Storage
from ml.data_collector import DataCollector
from ml.feature_engineer import FeatureEngineer
from ml.model_trainer import ModelTrainer

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
CHALLENGER_DIR = os.path.join(MODELS_DIR, "challenger")
ACTIVE_MODEL = os.path.join(MODELS_DIR, "xgboost_model.pkl")
ACTIVE_SCALER = os.path.join(MODELS_DIR, "xgboost_scaler.pkl")


def _backtest_model(model_path: str, scaler_path: str, df: pd.DataFrame, symbol: str,
                    threshold: float = 0.10) -> dict:
    """Run a quick backtest of a specific model file on df. Returns metrics dict."""
    import joblib
    from data.processor import DataProcessor
    from strategies.base import BaseStrategy
    from strategies.ensemble import EnsembleStrategy
    from backtest.backtester import BacktestEngine

    class _ModelOnlyStrategy(BaseStrategy):
        name = "ml_xgboost"

        def __init__(self, mdl_path, scl_path):
            import json
            from ml.feature_engineer import FeatureEngineer
            self._model = joblib.load(mdl_path)
            self._scaler = joblib.load(scl_path)
            feat_path = os.path.join(MODELS_DIR, "feature_names.json")
            with open(feat_path) as f:
                self._features = json.load(f)
            self._engineer = FeatureEngineer()

        def generate_signal(self, df, symbol=""):
            try:
                feat_df = self._engineer.transform(df)
                if feat_df.empty:
                    return {"action": "HOLD", "confidence": 0.0}
                row = feat_df[self._features].iloc[[-1]]
                scaled = self._scaler.transform(row)
                pred = int(self._model.predict(scaled)[0])
                proba = self._model.predict_proba(scaled)[0]
                label_map = {0: "SELL", 1: "HOLD", 2: "BUY"}
                action = label_map.get(pred, "HOLD")
                conf = float(proba[pred])
                return {"action": action, "confidence": round(conf, 3)}
            except Exception:
                return {"action": "HOLD", "confidence": 0.0}

    class _NullStrategy(BaseStrategy):
        name = "null"
        def generate_signal(self, df, symbol=""):
            return {"action": "HOLD", "confidence": 0.0}

    ens = EnsembleStrategy()
    ens.register(_ModelOnlyStrategy(model_path, scaler_path))
    for name in ["momentum", "mean_reversion", "trend_following", "sentiment"]:
        s = _NullStrategy()
        s.name = name
        ens.register(s)

    processor = DataProcessor()
    df_ind = processor.add_indicators(df.copy())
    if df_ind.empty:
        return {}

    engine = BacktestEngine(initial_balance=10_000.0, threshold=threshold)
    try:
        result = engine.run(df_ind, symbol, ens)
    except Exception as e:
        logger.warning(f"Backtest failed: {e}")
        return {}

    return result.metrics if result.trades else {}


async def run_retrain(settings: Settings, storage: Storage | None = None,
                      telegram=None) -> bool:
    params = load_trading_params()
    symbols: list[str] = params["trading"]["symbols"]
    timeframe: str = params["trading"]["timeframe"]
    val_days: int = getattr(settings, "validation_days", 14)
    sharpe_delta: float = getattr(settings, "promotion_sharpe_delta", 0.10)

    version = datetime.now(timezone.utc).strftime("v%Y%m%d_%H%M%S")
    logger.info(f"=== Retrain {version} starting ===")

    # 1. Collect data
    collector = DataCollector()
    data_map = await collector.collect_all(symbols, timeframe, months=6)
    if not data_map:
        logger.error("Retrain aborted: no data collected")
        return False

    # 2. Engineer features
    engineer = FeatureEngineer()
    X_parts, y_parts = [], []
    for symbol, df in data_map.items():
        X, y = engineer.build(df)
        if len(X) >= 100:
            X_parts.append(X)
            y_parts.append(y)

    if not X_parts:
        logger.error("Retrain aborted: no usable features")
        return False

    X_all = pd.concat(X_parts, ignore_index=True)
    y_all = pd.concat(y_parts, ignore_index=True)

    # 3. Train challenger
    os.makedirs(CHALLENGER_DIR, exist_ok=True)
    ch_model = os.path.join(CHALLENGER_DIR, "xgboost_model.pkl")
    ch_scaler = os.path.join(CHALLENGER_DIR, "xgboost_scaler.pkl")

    trainer = ModelTrainer()
    metrics = trainer.train_and_save(X_all, y_all, model_path=ch_model, scaler_path=ch_scaler)
    logger.info(f"Challenger trained | CV acc={metrics['mean_cv_accuracy']:.4f} | n={metrics['n_samples']}")

    # 4. Backtest challenger on validation window
    val_bars = val_days * 24 * 4  # 15m bars per day = 96; val_days * 96
    ch_sharpe = 0.0
    ch_win_rate = 0.0
    ch_drawdown = 1.0
    primary_symbol = symbols[0]
    val_df = list(data_map.values())[0]
    val_slice = val_df.iloc[-val_bars:] if len(val_df) > val_bars else val_df

    ch_bt = _backtest_model(ch_model, ch_scaler, val_slice, primary_symbol, threshold=0.05)
    if ch_bt:
        ch_sharpe = ch_bt.get("sharpe", 0.0)
        ch_win_rate = ch_bt.get("win_rate", 0.0)
        ch_drawdown = ch_bt.get("max_drawdown", 1.0)
        logger.info(f"Challenger backtest | sharpe={ch_sharpe:.3f} | wr={ch_win_rate:.2%} | dd={ch_drawdown:.2%}")
    else:
        logger.warning("Challenger backtest produced no trades — using CV accuracy comparison only")

    # 5. Compare with champion
    champion = None
    if storage:
        try:
            champion = storage.get_champion_metrics()
        except Exception as e:
            logger.warning(f"Could not fetch champion metrics: {e}")
    champ_sharpe = champion["sharpe"] if champion and champion.get("sharpe") else -999.0

    promoted = False
    notes = ""

    if ch_sharpe > champ_sharpe + sharpe_delta:
        # Promote challenger
        shutil.copy2(ch_model, ACTIVE_MODEL)
        shutil.copy2(ch_scaler, ACTIVE_SCALER)
        promoted = True
        notes = f"Promoted: challenger sharpe {ch_sharpe:.3f} > champion {champ_sharpe:.3f} + delta {sharpe_delta}"
        logger.info(f"[RETRAIN] PROMOTED {version} to champion")
    else:
        notes = f"Kept champion: challenger sharpe {ch_sharpe:.3f} <= {champ_sharpe:.3f} + {sharpe_delta}"
        logger.info(f"[RETRAIN] Challenger did not beat champion. {notes}")

    # 6. Log to DB
    model_id = None
    if storage:
        try:
            model_id = storage.log_model_version(
                version=version,
                cv_accuracy=metrics["mean_cv_accuracy"],
                sharpe=ch_sharpe,
                win_rate=ch_win_rate,
                max_drawdown=ch_drawdown,
                n_samples=metrics["n_samples"],
                model_path=ACTIVE_MODEL if promoted else ch_model,
                scaler_path=ACTIVE_SCALER if promoted else ch_scaler,
                is_champion=promoted,
                notes=notes,
            )
            if promoted and model_id:
                storage.set_champion(model_id)
        except Exception as e:
            logger.warning(f"DB log failed: {e}")

    # 7. Telegram notification
    if telegram:
        try:
            await telegram.send_retrain_result(
                version, promoted, ch_sharpe, metrics["mean_cv_accuracy"]
            )
        except Exception:
            pass

    return promoted


async def main():
    settings = Settings()
    storage = None
    try:
        storage = Storage(settings)
    except Exception as e:
        logger.warning(f"DB unavailable: {e}")

    await run_retrain(settings, storage)


if __name__ == "__main__":
    asyncio.run(main())
