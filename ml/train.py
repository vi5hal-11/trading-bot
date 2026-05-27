"""
One-shot training script. Run once before starting the bot:

    .\\venv\\Scripts\\python.exe ml\\train.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from loguru import logger
from config.settings import load_trading_params
from ml.data_collector import DataCollector
from ml.feature_engineer import FeatureEngineer
from ml.model_trainer import ModelTrainer


async def main():
    params = load_trading_params()
    symbols: list[str] = params["trading"]["symbols"]
    timeframe: str = params["trading"]["timeframe"]

    logger.info("=== Phase 2 Model Training ===")
    logger.info(f"Symbols: {symbols} | Timeframe: {timeframe} | Source: Binance")

    # 1. Collect historical data (from Binance — years of history available)
    collector = DataCollector()
    data_map = await collector.collect_all(symbols, timeframe, months=6)

    if not data_map:
        logger.error("No data collected. Aborting.")
        return

    # 2. Engineer features for all symbols and combine
    engineer = FeatureEngineer()
    X_parts, y_parts = [], []

    for symbol, df in data_map.items():
        logger.info(f"Engineering features for {symbol} ({len(df)} rows)")
        X, y = engineer.build(df)
        if len(X) < 100:
            logger.warning(f"Too few samples for {symbol} ({len(X)}), skipping")
            continue
        X_parts.append(X)
        y_parts.append(y)

    if not X_parts:
        logger.error("No usable feature sets. Aborting.")
        return

    X_all = pd.concat(X_parts, ignore_index=True)
    y_all = pd.concat(y_parts, ignore_index=True)
    logger.info(f"Combined training set: {X_all.shape}")

    # 3. Train and save
    trainer = ModelTrainer()
    metrics = trainer.train_and_save(X_all, y_all)

    logger.info("=== Training Complete ===")
    logger.info(f"Mean CV Accuracy : {metrics['mean_cv_accuracy']:.4f}")
    logger.info(f"Samples trained  : {metrics['n_samples']}")
    logger.info(f"Features used    : {metrics['n_features']}")
    logger.info(f"Top features     : {list(metrics['top_features'].keys())}")
    logger.info("Model ready. Run main.py to start the bot.")


if __name__ == "__main__":
    asyncio.run(main())
