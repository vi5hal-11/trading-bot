import pandas as pd
from strategies.base import BaseStrategy
from config.settings import load_trading_params


class MomentumStrategy(BaseStrategy):
    name = "momentum"

    def __init__(self):
        cfg = load_trading_params().get("strategies", {}).get("momentum", {})
        self.rsi_oversold = cfg.get("rsi_oversold", 35)
        self.rsi_overbought = cfg.get("rsi_overbought", 65)

    def generate_signal(self, df: pd.DataFrame, symbol: str = "") -> dict:
        row = df.iloc[-1]

        rsi = row["rsi"]
        macd_hist = row["macd_hist"]

        # MACD histogram direction (confirmation, not strict crossover)
        macd_bullish = macd_hist > 0
        macd_bearish = macd_hist < 0

        if rsi < self.rsi_oversold and macd_bullish:
            confidence = min(1.0, (self.rsi_oversold - rsi) / self.rsi_oversold + 0.4)
            return {"action": "BUY", "confidence": round(confidence, 3)}

        if rsi > self.rsi_overbought and macd_bearish:
            confidence = min(1.0, (rsi - self.rsi_overbought) / (100 - self.rsi_overbought) + 0.4)
            return {"action": "SELL", "confidence": round(confidence, 3)}

        return {"action": "HOLD", "confidence": 0.0}
