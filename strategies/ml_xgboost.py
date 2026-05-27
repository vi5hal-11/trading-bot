import json
import os
import joblib
import numpy as np
import pandas as pd
from loguru import logger
from strategies.base import BaseStrategy
from ml.feature_engineer import FeatureEngineer
from config.settings import load_trading_params


class MLXGBoostStrategy(BaseStrategy):
    name = "ml_xgboost"

    # Class-level cache — loaded once, shared across calls
    _model = None
    _scaler = None
    _feature_names: list[str] = []

    def __init__(self):
        cfg = load_trading_params().get("ml", {})
        self.model_path  = cfg.get("model_path",  "ml/models/xgboost_model.pkl")
        self.scaler_path = cfg.get("scaler_path", "ml/models/xgboost_scaler.pkl")
        self.feat_path   = cfg.get("feature_names_path", "ml/models/feature_names.json")
        self.conf_thresh = cfg.get("confidence_threshold", 0.15)
        self.engineer    = FeatureEngineer()
        self._try_load()

    def _try_load(self):
        if MLXGBoostStrategy._model is not None:
            return
        if not os.path.exists(self.model_path):
            logger.warning(
                f"XGBoost model not found at {self.model_path}. "
                "Run `python ml/train.py` to train. Strategy will return HOLD until then."
            )
            return
        try:
            MLXGBoostStrategy._model = joblib.load(self.model_path)
            MLXGBoostStrategy._scaler = joblib.load(self.scaler_path)
            with open(self.feat_path) as f:
                MLXGBoostStrategy._feature_names = json.load(f)
            logger.info("XGBoost model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load XGBoost model: {e}")

    def generate_signal(self, df: pd.DataFrame, symbol: str = "") -> dict:
        if MLXGBoostStrategy._model is None:
            return {"action": "HOLD", "confidence": 0.0}

        try:
            X = self.engineer.transform(df)
            if X.empty:
                return {"action": "HOLD", "confidence": 0.0}

            # Align features to training columns
            for col in MLXGBoostStrategy._feature_names:
                if col not in X.columns:
                    X[col] = 0.0
            X = X[MLXGBoostStrategy._feature_names]

            X_scaled = MLXGBoostStrategy._scaler.transform(X)
            probs = MLXGBoostStrategy._model.predict_proba(X_scaled)[0]
            # probs order: [sell(0), hold(1), buy(2)]

            best_class = int(np.argmax(probs))
            confidence = float(probs[best_class]) - (1.0 / 3.0)  # above random

            if confidence < self.conf_thresh:
                return {"action": "HOLD", "confidence": 0.0}

            action_map = {0: "SELL", 1: "HOLD", 2: "BUY"}
            action = action_map[best_class]

            return {"action": action, "confidence": round(max(confidence, 0.0), 4)}

        except Exception as e:
            logger.warning(f"MLXGBoostStrategy inference error: {e}")
            return {"action": "HOLD", "confidence": 0.0}
