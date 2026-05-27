import pandas as pd
import numpy as np
from loguru import logger
from config.settings import load_trading_params


class FeatureEngineer:
    def __init__(self):
        cfg = load_trading_params().get("ml", {})
        self.horizon = cfg.get("horizon_candles", 8)
        self.threshold = cfg.get("label_threshold_pct", 0.005)
        self.feature_names: list[str] = []

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _add_features(self, df: pd.DataFrame) -> pd.DataFrame:
        f = pd.DataFrame(index=df.index)

        # Existing indicators (pass-through)
        for col in ["rsi", "macd", "macd_signal", "macd_hist",
                    "bb_upper", "bb_lower", "bb_mid", "bb_pct", "atr",
                    "sma_fast", "sma_slow", "ema_12", "ema_26", "adx",
                    "obv", "vol_ratio"]:
            if col in df.columns:
                f[col] = df[col]

        # Lagged features
        f["rsi_lag1"]       = df["rsi"].shift(1)
        f["macd_hist_lag1"] = df["macd_hist"].shift(1)
        f["bb_pct_lag1"]    = df["bb_pct"].shift(1)
        f["vol_ratio_lag1"] = df["vol_ratio"].shift(1)

        # Derived features
        f["bb_width"]      = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"].replace(0, np.nan)
        f["macd_strength"] = df["macd_hist"] / df["atr"].replace(0, np.nan)
        f["rsi_slope"]     = df["rsi"] - df["rsi"].shift(1)

        # Price momentum
        f["return_1"] = df["close"].pct_change(1)
        f["return_4"] = df["close"].pct_change(4)

        # Time features
        f["hour"]        = df.index.hour
        f["day_of_week"] = df.index.dayofweek

        f.replace([np.inf, -np.inf], np.nan, inplace=True)
        f.dropna(inplace=True)
        return f

    # ── Public API ────────────────────────────────────────────────────────────

    def build(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
        """Build feature matrix + target labels for training. Drops last `horizon` rows."""
        features = self._add_features(df)

        # Future return (look-ahead, safe because we're in training mode)
        future_return = df["close"].pct_change(-self.horizon).shift(-self.horizon)
        future_return = future_return.reindex(features.index)

        # Labels
        y = pd.Series(0, index=features.index, dtype=int)
        y[future_return > self.threshold]  = 1   # BUY
        y[future_return < -self.threshold] = -1  # SELL

        # Drop last `horizon` rows — no valid future label
        valid = y.dropna().index[:-self.horizon]
        X = features.loc[valid]
        y = y.loc[valid]

        self.feature_names = list(X.columns)
        logger.info(f"Feature matrix: {X.shape} | BUY={( y==1).sum()} HOLD={(y==0).sum()} SELL={(y==-1).sum()}")
        return X, y

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return the last row as a feature vector for inference."""
        features = self._add_features(df)
        if features.empty:
            return features
        return features.iloc[[-1]]  # keep as DataFrame (1 row)
