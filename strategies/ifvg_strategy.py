"""IFVG strategy adapter — bridges the async IFVG cycle with the synchronous BaseStrategy interface."""
import pandas as pd
from strategies.base import BaseStrategy
from ifvg import get_cached_signal


class IFVGStrategy(BaseStrategy):
    """Reads the IFVG signal cache populated by run_ifvg_cycle() in the main loop.

    generate_signal() is synchronous per BaseStrategy contract, so it simply
    returns the pre-computed signal from the module-level cache.  The cycle
    itself is called separately as an async task in main.py before the
    ensemble is evaluated.
    """

    name = "ifvg"

    def generate_signal(self, df: pd.DataFrame, symbol: str = "") -> dict:
        cached = get_cached_signal(symbol)
        action = cached.get("action", "HOLD")
        confidence = float(cached.get("confidence", 0.0))
        return {"action": action, "confidence": confidence}
