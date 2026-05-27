from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame, symbol: str = "") -> dict:
        """Return dict with keys: action (BUY|SELL|HOLD), confidence (0-1)."""
        ...
