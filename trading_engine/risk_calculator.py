from loguru import logger
from config.settings import load_trading_params


class RiskCalculator:
    def __init__(self):
        p = load_trading_params()["risk"]
        self.max_loss_pct = p["max_loss_pct_per_trade"]
        self.max_pos_pct = p["max_position_pct"]
        self.max_open = p["max_open_positions"]
        self.daily_cb = p["daily_loss_circuit_breaker"]
        self.intraday_cb = p["intraday_loss_circuit_breaker"]
        self.kelly_fraction = p["kelly_fraction"]
        self.atr_mult = p["trailing_stop_atr_multiplier"]
        self.max_drawdown = p.get("max_portfolio_drawdown", 0.15)
        self.max_exposure = p.get("max_total_exposure_pct", 0.80)
        buckets = p.get("correlation_buckets", {})
        self._buckets: list[set] = [set(v) for v in buckets.values()]

    def position_size(
        self,
        portfolio: float,
        entry_price: float,
        stop_loss: float,
        signal_strength: float,
        win_rate: float = 0.55,
        avg_win: float = 0.02,
        avg_loss: float = 0.02,
    ) -> float:
        price_risk = abs(entry_price - stop_loss)
        if price_risk == 0:
            return 0.0

        max_from_loss = (portfolio * self.max_loss_pct) / price_risk

        kelly_pct = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
        kelly_pct = max(0.0, kelly_pct) * self.kelly_fraction
        kelly_pos = (portfolio * kelly_pct) / price_risk

        max_from_cap = (portfolio * self.max_pos_pct) / entry_price

        raw = min(max_from_loss, kelly_pos, max_from_cap)
        return raw * signal_strength

    def stop_loss_price(self, entry: float, side: str, atr: float) -> float:
        mult = self.atr_mult
        if side == "BUY":
            return entry - mult * atr
        return entry + mult * atr

    def circuit_breaker(
        self, daily_pnl_pct: float, intraday_pnl_pct: float
    ) -> tuple[bool, str]:
        if daily_pnl_pct < -self.daily_cb:
            return False, f"Daily loss circuit breaker: {daily_pnl_pct:.2%}"
        if intraday_pnl_pct < -self.intraday_cb:
            return False, f"Intraday loss circuit breaker: {intraday_pnl_pct:.2%}"
        return True, "ok"

    def drawdown_breaker(self, drawdown_from_peak: float) -> tuple[bool, str]:
        """Returns (False, reason) when portfolio drawdown exceeds max threshold."""
        if drawdown_from_peak > self.max_drawdown:
            return False, f"Portfolio drawdown {drawdown_from_peak:.2%} exceeds limit {self.max_drawdown:.2%}"
        return True, "ok"

    def exposure_check(self, current_exposure: float, balance: float) -> tuple[bool, str]:
        """Returns (False, reason) if adding a new position would breach total exposure cap."""
        exposure_pct = current_exposure / balance if balance > 0 else 1.0
        if exposure_pct >= self.max_exposure:
            return False, f"Total exposure {exposure_pct:.2%} at cap ({self.max_exposure:.2%})"
        return True, "ok"

    def correlation_check(
        self, symbol: str, open_positions: dict
    ) -> tuple[bool, str]:
        """Returns (False, reason) if adding symbol would double up in a correlated bucket."""
        for bucket in self._buckets:
            if symbol not in bucket:
                continue
            conflicts = [s for s in open_positions if s in bucket and s != symbol]
            if conflicts:
                return False, f"{symbol} correlates with open position(s): {conflicts}"
        return True, "ok"

    def validate_new_position(
        self,
        open_positions: int,
        current_exposure: float = 0.0,
        balance: float = 1.0,
        symbol: str = "",
        positions_map: dict = None,
    ) -> tuple[bool, str]:
        if open_positions >= self.max_open:
            return False, f"Max open positions ({self.max_open}) reached"
        ok, reason = self.exposure_check(current_exposure, balance)
        if not ok:
            return False, reason
        if symbol and positions_map is not None:
            ok, reason = self.correlation_check(symbol, positions_map)
            if not ok:
                return False, reason
        return True, "ok"
