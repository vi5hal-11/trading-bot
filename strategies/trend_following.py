import pandas as pd
from strategies.base import BaseStrategy
from config.settings import load_trading_params


class TrendFollowingStrategy(BaseStrategy):
    name = "trend_following"

    def __init__(self):
        cfg = load_trading_params().get("strategies", {}).get("trend_following", {})
        self.vol_threshold = cfg.get("vol_ratio_threshold", 1.2)

    def generate_signal(self, df: pd.DataFrame, symbol: str = "") -> dict:
        row = df.iloc[-1]
        prev = df.iloc[-2]

        ema_fast = row["ema_12"]
        ema_slow = row["ema_26"]
        prev_ema_fast = prev["ema_12"]
        prev_ema_slow = prev["ema_26"]
        vol_ratio = row["vol_ratio"]
        close = row["close"]

        golden_cross = prev_ema_fast <= prev_ema_slow and ema_fast > ema_slow
        death_cross  = prev_ema_fast >= prev_ema_slow and ema_fast < ema_slow
        high_volume  = vol_ratio >= self.vol_threshold

        if golden_cross and close > ema_slow and high_volume:
            confidence = min(1.0, 0.5 + (vol_ratio - self.vol_threshold) * 0.15)
            return {"action": "BUY", "confidence": round(confidence, 3)}

        if death_cross and close < ema_slow and high_volume:
            confidence = min(1.0, 0.5 + (vol_ratio - self.vol_threshold) * 0.15)
            return {"action": "SELL", "confidence": round(confidence, 3)}

        return {"action": "HOLD", "confidence": 0.0}
