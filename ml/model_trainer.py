import json
import os
import joblib
import numpy as np
import pandas as pd
from loguru import logger
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score
from sklearn.utils.class_weight import compute_sample_weight
import xgboost as xgb
from config.settings import load_trading_params

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")


class ModelTrainer:
    def __init__(self):
        cfg = load_trading_params().get("ml", {})
        self.model_path   = cfg.get("model_path",   "ml/models/xgboost_model.pkl")
        self.scaler_path  = cfg.get("scaler_path",  "ml/models/xgboost_scaler.pkl")
        self.feat_path    = cfg.get("feature_names_path", "ml/models/feature_names.json")
        os.makedirs(MODELS_DIR, exist_ok=True)

    def train_and_save(self, X: pd.DataFrame, y: pd.Series,
                       model_path: str = None, scaler_path: str = None) -> dict:
        # Map labels -1/0/1 → 0/1/2 for XGBoost multi-class
        label_map = {-1: 0, 0: 1, 1: 2}
        y_enc = y.map(label_map)

        tscv = TimeSeriesSplit(n_splits=5)
        fold_accuracies = []
        best_model = None
        best_acc = -1

        logger.info(f"Training XGBoost on {len(X)} samples, {X.shape[1]} features")

        for fold, (train_idx, val_idx) in enumerate(tscv.split(X), 1):
            X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_tr, y_val = y_enc.iloc[train_idx], y_enc.iloc[val_idx]

            scaler = StandardScaler()
            X_tr_s  = scaler.fit_transform(X_tr)
            X_val_s = scaler.transform(X_val)

            model = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=5,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                objective="multi:softmax",
                num_class=3,
                eval_metric="mlogloss",
                early_stopping_rounds=20,
                random_state=42,
                verbosity=0,
            )
            # Upweight BUY/SELL relative to HOLD to counter class imbalance
            sample_weights = compute_sample_weight("balanced", y_tr)
            model.fit(
                X_tr_s, y_tr,
                sample_weight=sample_weights,
                eval_set=[(X_val_s, y_val)],
                verbose=False,
            )

            preds = model.predict(X_val_s)
            acc = accuracy_score(y_val, preds)
            fold_accuracies.append(acc)
            logger.info(f"  Fold {fold}: accuracy={acc:.4f} | best_iteration={model.best_iteration}")

            if acc > best_acc:
                best_acc = acc
                best_model = (model, scaler)

        mean_acc = float(np.mean(fold_accuracies))
        logger.info(f"Mean CV accuracy: {mean_acc:.4f}")

        # Feature importance (top 10)
        model_final, scaler_final = best_model
        importance = pd.Series(
            model_final.feature_importances_, index=X.columns
        ).sort_values(ascending=False)
        logger.info("Top 10 features:\n" + importance.head(10).to_string())

        # Save
        save_model_path = model_path or self.model_path
        save_scaler_path = scaler_path or self.scaler_path
        os.makedirs(os.path.dirname(save_model_path), exist_ok=True)
        joblib.dump(model_final, save_model_path)
        joblib.dump(scaler_final, save_scaler_path)
        if not model_path:
            with open(self.feat_path, "w") as f:
                json.dump(list(X.columns), f)

        logger.info(f"Model saved to {save_model_path}")

        return {
            "mean_cv_accuracy": mean_acc,
            "fold_accuracies": fold_accuracies,
            "n_samples": len(X),
            "n_features": X.shape[1],
            "top_features": importance.head(5).to_dict(),
            "model_path": save_model_path,
            "scaler_path": save_scaler_path,
        }
