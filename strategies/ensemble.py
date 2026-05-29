import pandas as pd
from loguru import logger
from strategies.base import BaseStrategy
from config.settings import load_trading_params


class EnsembleStrategy:
    def __init__(self):
        weights = load_trading_params()["ensemble"]["weights"]
        self.threshold = load_trading_params()["ensemble"]["threshold"]
        self._strategies: dict[str, tuple[BaseStrategy, float]] = {}
        self._weights = weights

    def register(self, strategy: BaseStrategy):
        weight = self._weights.get(strategy.name, 1.0)
        self._strategies[strategy.name] = (strategy, weight)

    def set_weights(self, weights: dict[str, float]) -> None:
        """Replace per-strategy weights (called each loop by BanditEnsemble)."""
        for name, w in weights.items():
            if name in self._strategies:
                strat, _ = self._strategies[name]
                self._strategies[name] = (strat, w)

    def generate_signal(
        self,
        df: pd.DataFrame,
        symbol: str = "",
        enabled_strategies: dict | None = None,
    ) -> dict:
        if len(df) < 3:
            return {"action": "HOLD", "confidence": 0.0, "consensus_score": 0.0}

        vote = 0.0
        total_weight = 0.0
        component_signals = {}
        component_confidences = {}

        for name, (strategy, weight) in self._strategies.items():
            if enabled_strategies is not None and not enabled_strategies.get(name, True):
                component_signals[name] = "HOLD"
                component_confidences[name] = 0.0
                continue
            try:
                sig = strategy.generate_signal(df, symbol)
            except Exception as e:
                logger.warning(f"Strategy {name} error on {symbol}: {e}")
                continue

            action = sig["action"]
            conf = sig["confidence"]
            component_signals[name] = action
            component_confidences[name] = conf

            val = 1 if action == "BUY" else (-1 if action == "SELL" else 0)
            vote += val * weight * conf
            total_weight += weight

        consensus = vote / total_weight if total_weight > 0 else 0.0

        if consensus > self.threshold:
            action = "BUY"
        elif consensus < -self.threshold:
            action = "SELL"
        else:
            action = "HOLD"

        return {
            "action": action,
            "confidence": round(abs(consensus), 4),
            "consensus_score": round(consensus, 4),
            "strategy": "ensemble",
            "component_signals": component_signals,
            "component_confidences": component_confidences,
        }
