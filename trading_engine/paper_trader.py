from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from loguru import logger
from typing import Optional
from trading_engine.risk_calculator import RiskCalculator
from config.settings import Settings, load_trading_params


@dataclass
class Position:
    symbol: str
    side: str               # BUY | SELL
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    strategy: str
    confidence: float
    db_id: Optional[int] = None
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    partial_tp1_done: bool = False
    partial_tp2_done: bool = False

    @property
    def cost(self) -> float:
        return self.entry_price * self.quantity

    def unrealized_pnl(self, current_price: float) -> float:
        if self.side == "BUY":
            return (current_price - self.entry_price) * self.quantity
        return (self.entry_price - current_price) * self.quantity

    def unrealized_pnl_pct(self, current_price: float) -> float:
        return self.unrealized_pnl(current_price) / self.cost


class PaperTrader:
    def __init__(self, settings: Settings, risk: RiskCalculator):
        self.risk = risk
        params = load_trading_params()
        tp = params["take_profit"]
        self.tp1_pct = tp["partial_1_pct"]
        self.tp1_size = tp["partial_1_size"]
        self.tp2_pct = tp["partial_2_pct"]
        self.tp2_size = tp["partial_2_size"]
        self.time_stop_hours = params["risk"]["time_stop_hours"]

        self.balance: float = settings.paper_initial_balance
        self.positions: dict[str, Position] = {}
        self.closed_trades: list[dict] = []
        self._daily_start_balance = self.balance
        self._intraday_start_balance = self.balance
        self._intraday_date: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._session_start_balance = self.balance
        self._peak_equity: float = self.balance

    # ── Stats ────────────────────────────────────────────────────────────────

    @property
    def equity(self) -> float:
        return self.balance + sum(
            p.unrealized_pnl(p.entry_price) for p in self.positions.values()
        )

    @property
    def total_pnl(self) -> float:
        return self.balance - self._session_start_balance

    @property
    def daily_pnl_pct(self) -> float:
        return (self.balance - self._daily_start_balance) / self._daily_start_balance

    @property
    def intraday_pnl_pct(self) -> float:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._intraday_date:
            self._intraday_date = today
            self._intraday_start_balance = self.balance
        return (self.balance - self._intraday_start_balance) / self._intraday_start_balance

    @property
    def drawdown_from_peak(self) -> float:
        eq = self.equity
        if eq > self._peak_equity:
            self._peak_equity = eq
        if self._peak_equity == 0:
            return 0.0
        return (self._peak_equity - eq) / self._peak_equity

    @property
    def current_exposure(self) -> float:
        return sum(p.cost for p in self.positions.values())

    def reset_daily(self):
        self._daily_start_balance = self.balance

    # ── Order execution ───────────────────────────────────────────────────────

    async def open_position(
        self,
        symbol: str,
        signal: dict,
        current_price: float,
        atr: float,
        storage=None,
    ) -> Optional[Position]:
        side = signal["action"]  # BUY or SELL
        confidence = signal["confidence"]

        ok, reason = self.risk.validate_new_position(
            open_positions=len(self.positions),
            current_exposure=self.current_exposure,
            balance=self.balance,
            symbol=symbol,
            positions_map=self.positions,
        )
        if not ok:
            logger.debug(f"Cannot open {symbol}: {reason}")
            return None

        ok, reason = self.risk.circuit_breaker(self.daily_pnl_pct, self.intraday_pnl_pct)
        if not ok:
            logger.warning(f"Circuit breaker active: {reason}")
            return None

        ok, reason = self.risk.drawdown_breaker(self.drawdown_from_peak)
        if not ok:
            logger.warning(f"Drawdown halt: {reason}")
            return None

        if symbol in self.positions:
            logger.debug(f"Already have position in {symbol}")
            return None

        stop_loss = self.risk.stop_loss_price(current_price, side, atr)
        take_profit = (
            current_price * (1 + self.tp2_pct * 2)
            if side == "BUY"
            else current_price * (1 - self.tp2_pct * 2)
        )

        qty = self.risk.position_size(
            portfolio=self.balance,
            entry_price=current_price,
            stop_loss=stop_loss,
            signal_strength=confidence,
        )

        cost = current_price * qty
        if cost > self.balance:
            qty = self.balance / current_price
            cost = self.balance

        if qty <= 0:
            return None

        pos = Position(
            symbol=symbol,
            side=side,
            entry_price=current_price,
            quantity=qty,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy=signal.get("strategy", "ensemble"),
            confidence=confidence,
        )
        self.balance -= cost
        self.positions[symbol] = pos

        if storage:
            try:
                pos.db_id = storage.log_trade({
                    "symbol": symbol,
                    "side": side,
                    "entry_price": current_price,
                    "quantity": qty,
                    "strategy": pos.strategy,
                    "confidence": confidence,
                    "paper": True,
                })
            except Exception as e:
                logger.debug(f"Trade log skipped (DB unavailable): {e}")

        logger.info(
            f"[PAPER] OPEN {side} {symbol} @ {current_price:.4f} | "
            f"qty={qty:.4f} | stop={stop_loss:.4f} | conf={confidence:.2f}"
        )
        return pos

    async def close_position(
        self,
        symbol: str,
        current_price: float,
        reason: str = "signal",
        storage=None,
    ) -> Optional[dict]:
        pos = self.positions.pop(symbol, None)
        if pos is None:
            return None

        pnl = pos.unrealized_pnl(current_price)
        pnl_pct = pos.unrealized_pnl_pct(current_price)
        self.balance += pos.cost + pnl

        if storage and pos.db_id:
            try:
                storage.close_trade(pos.db_id, current_price, pnl, pnl_pct)
            except Exception as e:
                logger.debug(f"Trade close log skipped (DB unavailable): {e}")

        trade = {
            "symbol": symbol,
            "side": pos.side,
            "entry_price": pos.entry_price,
            "exit_price": current_price,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "reason": reason,
        }
        self.closed_trades.append(trade)

        emoji = "+" if pnl >= 0 else "-"
        logger.info(
            f"[PAPER] [{emoji}] CLOSE {symbol} @ {current_price:.4f} | "
            f"PnL={pnl:+.2f} USDT ({pnl_pct:+.2%}) | reason={reason}"
        )
        return trade

    # ── Position management ───────────────────────────────────────────────────

    async def check_stops_and_targets(
        self, prices: dict[str, float], storage=None
    ) -> list[dict]:
        closed = []
        now = datetime.now(timezone.utc)

        # Portfolio drawdown halt: close all positions if peak drawdown exceeded
        ok, reason = self.risk.drawdown_breaker(self.drawdown_from_peak)
        if not ok:
            logger.warning(f"[PAPER] Drawdown halt triggered — closing all positions. {reason}")
            for symbol in list(self.positions.keys()):
                price = prices.get(symbol, self.positions[symbol].entry_price)
                t = self.close_position(symbol, price, "drawdown_halt", storage)
                if t:
                    closed.append(t)
            return closed

        for symbol, pos in list(self.positions.items()):
            price = prices.get(symbol)
            if price is None:
                continue

            pnl_pct = pos.unrealized_pnl_pct(price)

            hit_stop = (
                (pos.side == "BUY" and price <= pos.stop_loss)
                or (pos.side == "SELL" and price >= pos.stop_loss)
            )
            if hit_stop:
                t = self.close_position(symbol, price, "stop_loss", storage)
                if t:
                    closed.append(t)
                continue

            age = now - pos.opened_at
            if age > timedelta(hours=self.time_stop_hours) and pnl_pct <= 0:
                t = self.close_position(symbol, price, "time_stop", storage)
                if t:
                    closed.append(t)
                continue

            # Partial TP1
            if not pos.partial_tp1_done and pnl_pct >= self.tp1_pct:
                partial_qty = pos.quantity * self.tp1_size
                pnl = (price - pos.entry_price) * partial_qty
                self.balance += pos.entry_price * partial_qty + pnl
                pos.quantity -= partial_qty
                pos.partial_tp1_done = True
                logger.info(f"[PAPER] TP1 partial close {symbol}: {pnl:+.2f} USDT")

            # Partial TP2
            if not pos.partial_tp2_done and pnl_pct >= self.tp2_pct:
                partial_qty = pos.quantity * self.tp2_size
                pnl = (price - pos.entry_price) * partial_qty
                self.balance += pos.entry_price * partial_qty + pnl
                pos.quantity -= partial_qty
                pos.partial_tp2_done = True
                logger.info(f"[PAPER] TP2 partial close {symbol}: {pnl:+.2f} USDT")

        return closed

    def update_stop(self, symbol: str, new_stop: float) -> bool:
        pos = self.positions.get(symbol)
        if pos is None:
            return False
        pos.stop_loss = new_stop
        logger.info(f"[PAPER] Stop updated {symbol} → {new_stop:.4f}")
        return True

    def update_tp(self, symbol: str, new_tp: float) -> bool:
        pos = self.positions.get(symbol)
        if pos is None:
            return False
        pos.take_profit = new_tp
        logger.info(f"[PAPER] TP updated {symbol} → {new_tp:.4f}")
        return True

    def summary(self) -> dict:
        wins = [t for t in self.closed_trades if t["pnl"] >= 0]
        total = len(self.closed_trades)
        return {
            "balance": self.balance,
            "equity": self.equity,
            "open_positions": len(self.positions),
            "total_trades": total,
            "win_rate": len(wins) / total if total else 0,
            "total_pnl": self.total_pnl,
            "daily_pnl_pct": self.daily_pnl_pct,
            "drawdown_from_peak": self.drawdown_from_peak,
        }
