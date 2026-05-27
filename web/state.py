from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class BotState:
    paper_trader: object = None
    current_prices: dict = field(default_factory=dict)
    loop_count: int = 0
    paused: bool = False
    running: bool = True                 # False → loop skips signal processing
    mode: str = "PAPER"
    last_signals: dict = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    circuit_breaker_active: bool = False
    activity_log: list = field(default_factory=list)

    # Per-strategy enabled flags
    strategy_enabled: dict = field(default_factory=lambda: {
        "momentum": True,
        "mean_reversion": True,
        "trend_following": True,
        "ml_xgboost": True,
        "sentiment": True,
        "ifvg": True,
    })

    # Live risk overrides applied to running paper_trader + risk_calculator
    risk_overrides: dict = field(default_factory=dict)

    # Runtime-mutable symbol watchlist
    symbols: list = field(default_factory=list)

    # Live bot log stream (circular, last 200 lines)
    log_buffer: list = field(default_factory=list)

    # Latest indicator snapshot per symbol: symbol → {rsi, macd_hist, bb_pct, adx, ...}
    last_indicators: dict = field(default_factory=dict)

    def log_activity(self, type: str, message: str, symbol: str = ""):
        entry = {
            "type": type,
            "message": message,
            "symbol": symbol,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self.activity_log.append(entry)
        if len(self.activity_log) > 100:
            self.activity_log.pop(0)

    def push_log(self, level: str, message: str):
        entry = {
            "level": level,       # INFO, WARNING, ERROR, DEBUG
            "message": message,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self.log_buffer.append(entry)
        if len(self.log_buffer) > 200:
            self.log_buffer.pop(0)
