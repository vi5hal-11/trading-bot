import pandas as pd
from strategies.base import BaseStrategy
from config.settings import load_trading_params


class MeanReversionStrategy(BaseStrategy):
    name = "mean_reversion"

    def __init__(self):
        cfg = load_trading_params().get("strategies", {}).get("mean_reversion", {})
        self.adx_threshold = cfg.get("adx_threshold", 28)
        self.bb_buy_pct  = cfg.get("bb_buy_pct", 0.10)
        self.bb_sell_pct = cfg.get("bb_sell_pct", 0.90)

    def generate_signal(self, df: pd.DataFrame, symbol: str = "") -> dict:
        row = df.iloc[-1]

        bb_pct = row["bb_pct"]
        adx = row["adx"]

        trending = adx > self.adx_threshold

        if bb_pct < self.bb_buy_pct and trending:
            confidence = min(1.0, 0.3 + (self.bb_buy_pct - bb_pct) * 4)
            return {"action": "BUY", "confidence": round(confidence, 3)}

        if bb_pct > self.bb_sell_pct and trending:
            confidence = min(1.0, 0.3 + (bb_pct - self.bb_sell_pct) * 4)
            return {"action": "SELL", "confidence": round(confidence, 3)}

        return {"action": "HOLD", "confidence": 0.0}
