"""
BlofinTrader — places real orders on Blofin (demo or live) via CCXT.
Exposes the same async interface as PaperTrader so main.py is unchanged.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from functools import partial
from typing import Optional

import ccxt
from loguru import logger

from config.settings import Settings, load_trading_params
from trading_engine.risk_calculator import RiskCalculator

# Blofin demo endpoint — API keys must be generated at demo.blofin.com
_DEMO_URLS = {
    "public": "https://openapi-demo.blofin.com",
    "private": "https://openapi-demo.blofin.com",
}


@dataclass
class Position:
    symbol: str
    side: str
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    strategy: str
    confidence: float
    order_id: Optional[str] = None
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
        return self.unrealized_pnl(current_price) / self.cost if self.cost else 0.0


class BlofinTrader:
    """Live/demo trading engine backed by Blofin via CCXT."""

    def __init__(self, settings: Settings, risk: RiskCalculator):
        self.risk = risk
        params = load_trading_params()
        tp = params["take_profit"]
        self.tp1_pct = tp["partial_1_pct"]
        self.tp1_size = tp["partial_1_size"]
        self.tp2_pct = tp["partial_2_pct"]
        self.tp2_size = tp["partial_2_size"]
        self.time_stop_hours = params["risk"]["time_stop_hours"]

        self.positions: dict[str, Position] = {}
        self.closed_trades: list[dict] = []
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="blofin")

        exc_kwargs: dict = {
            "apiKey": settings.blofin_api_key,
            "secret": settings.blofin_secret_key,
            "password": settings.blofin_passphrase,
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        }
        if settings.blofin_demo:
            exc_kwargs["urls"] = {"api": _DEMO_URLS}
            logger.info("BlofinTrader: DEMO endpoint — demo.blofin.com keys required")
        else:
            logger.warning("BlofinTrader: LIVE endpoint — real money at risk ⚠️")

        self._exchange = ccxt.blofin(exc_kwargs)

        # Probe connection and get starting balance
        bal = self._exchange.fetch_balance()
        usdt = bal.get("USDT", {})
        self.balance: float = float(usdt.get("free") or usdt.get("total") or 0)
        self._session_start = self.balance
        self._daily_start = self.balance
        self._intraday_start = self.balance
        self._intraday_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._peak_equity = self.balance
        logger.info(f"BlofinTrader ready — balance={self.balance:.2f} USDT")

    # ── Async CCXT helper ─────────────────────────────────────────────────────

    async def _run(self, fn, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, partial(fn, *args, **kwargs))

    async def _refresh_balance(self):
        try:
            bal = await self._run(self._exchange.fetch_balance)
            usdt = bal.get("USDT", {})
            self.balance = float(usdt.get("free") or usdt.get("total") or self.balance)
        except Exception as e:
            logger.warning(f"Balance refresh failed: {e}")

    # ── Stats (same properties as PaperTrader) ────────────────────────────────

    @property
    def equity(self) -> float:
        return self.balance

    @property
    def total_pnl(self) -> float:
        return self.balance - self._session_start

    @property
    def daily_pnl_pct(self) -> float:
        return (self.balance - self._daily_start) / self._daily_start if self._daily_start else 0.0

    @property
    def intraday_pnl_pct(self) -> float:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._intraday_date:
            self._intraday_date = today
            self._intraday_start = self.balance
        return (self.balance - self._intraday_start) / self._intraday_start if self._intraday_start else 0.0

    @property
    def drawdown_from_peak(self) -> float:
        eq = self.equity
        if eq > self._peak_equity:
            self._peak_equity = eq
        return (self._peak_equity - eq) / self._peak_equity if self._peak_equity else 0.0

    @property
    def current_exposure(self) -> float:
        return sum(p.cost for p in self.positions.values())

    def reset_daily(self):
        self._daily_start = self.balance

    # ── Order execution ───────────────────────────────────────────────────────

    async def open_position(
        self,
        symbol: str,
        signal: dict,
        current_price: float,
        atr: float,
        storage=None,
    ) -> Optional[Position]:
        side = signal["action"]
        confidence = signal["confidence"]

        ok, reason = self.risk.validate_new_position(
            open_positions=len(self.positions),
            current_exposure=self.current_exposure,
            balance=self.balance,
            symbol=symbol,
            positions_map=self.positions,
        )
        if not ok:
            logger.debug(f"[BLOFIN] Cannot open {symbol}: {reason}")
            return None

        ok, reason = self.risk.circuit_breaker(self.daily_pnl_pct, self.intraday_pnl_pct)
        if not ok:
            logger.warning(f"[BLOFIN] Circuit breaker: {reason}")
            return None

        ok, reason = self.risk.drawdown_breaker(self.drawdown_from_peak)
        if not ok:
            logger.warning(f"[BLOFIN] Drawdown halt: {reason}")
            return None

        if symbol in self.positions:
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
        if qty <= 0:
            return None

        order_side = "buy" if side == "BUY" else "sell"
        try:
            order = await self._run(
                self._exchange.create_order,
                symbol,
                "market",
                order_side,
                qty,
                None,
                {
                    "stopLoss": {"triggerPrice": str(round(stop_loss, 6)), "type": "market"},
                    "takeProfit": {"triggerPrice": str(round(take_profit, 6)), "type": "market"},
                    "marginMode": "isolated",
                    "leverage": "1",
                    "positionSide": "net",
                },
            )
            order_id = str(order.get("id", ""))
        except Exception as e:
            logger.error(f"[BLOFIN] Order failed {symbol} {side}: {e}")
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
            order_id=order_id,
        )
        self.positions[symbol] = pos
        await self._refresh_balance()

        if storage:
            try:
                pos.db_id = storage.log_trade({
                    "symbol": symbol, "side": side,
                    "entry_price": current_price, "quantity": qty,
                    "strategy": pos.strategy, "confidence": confidence,
                    "paper": False,
                })
            except Exception as e:
                logger.debug(f"Trade log skipped: {e}")

        logger.info(
            f"[BLOFIN] OPEN {side} {symbol} @ {current_price:.4f} | "
            f"qty={qty:.4f} | sl={stop_loss:.4f} | tp={take_profit:.4f} | id={order_id}"
        )
        return pos

    async def close_position(
        self,
        symbol: str,
        current_price: float,
        reason: str = "signal",
        storage=None,
    ) -> Optional[dict]:
        pos = self.positions.get(symbol)
        if pos is None:
            return None

        close_side = "sell" if pos.side == "BUY" else "buy"
        try:
            await self._run(
                self._exchange.create_order,
                symbol,
                "market",
                close_side,
                pos.quantity,
                None,
                {"marginMode": "isolated", "positionSide": "net", "reduceOnly": True},
            )
        except Exception as e:
            logger.error(f"[BLOFIN] Close failed {symbol}: {e}")

        self.positions.pop(symbol, None)
        pnl = pos.unrealized_pnl(current_price)
        pnl_pct = pos.unrealized_pnl_pct(current_price)
        await self._refresh_balance()

        if storage and pos.db_id:
            try:
                storage.close_trade(pos.db_id, current_price, pnl, pnl_pct)
            except Exception as e:
                logger.debug(f"Trade close log skipped: {e}")

        trade = {
            "symbol": symbol, "side": pos.side,
            "entry_price": pos.entry_price, "exit_price": current_price,
            "pnl": pnl, "pnl_pct": pnl_pct, "reason": reason,
        }
        self.closed_trades.append(trade)
        logger.info(f"[BLOFIN] CLOSE {symbol} @ {current_price:.4f} | PnL≈{pnl:+.2f} | {reason}")
        return trade

    # ── Sync with exchange (detect SL/TP hits) ────────────────────────────────

    async def check_stops_and_targets(
        self, prices: dict[str, float], storage=None
    ) -> list[dict]:
        closed = []

        ok, reason = self.risk.drawdown_breaker(self.drawdown_from_peak)
        if not ok:
            logger.warning(f"[BLOFIN] Drawdown halt — closing all. {reason}")
            for sym in list(self.positions.keys()):
                price = prices.get(sym, self.positions[sym].entry_price)
                t = await self.close_position(sym, price, "drawdown_halt", storage)
                if t:
                    closed.append(t)
            return closed

        # Detect positions closed by exchange SL/TP
        try:
            exchange_pos = await self._run(
                self._exchange.fetch_positions,
                list(self.positions.keys()) or None,
            )
            active_on_exchange = {
                p["symbol"]
                for p in (exchange_pos or [])
                if abs(float(p.get("contracts") or 0)) > 0
            }
        except Exception as e:
            logger.warning(f"fetch_positions failed: {e}")
            active_on_exchange = set(self.positions.keys())

        now = datetime.now(timezone.utc)
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            price = prices.get(symbol, pos.entry_price)

            if symbol not in active_on_exchange:
                # Exchange closed it (SL/TP hit)
                pnl = pos.unrealized_pnl(price)
                pnl_pct = pos.unrealized_pnl_pct(price)
                self.positions.pop(symbol, None)
                if storage and pos.db_id:
                    try:
                        storage.close_trade(pos.db_id, price, pnl, pnl_pct)
                    except Exception:
                        pass
                trade = {
                    "symbol": symbol, "side": pos.side,
                    "entry_price": pos.entry_price, "exit_price": price,
                    "pnl": pnl, "pnl_pct": pnl_pct, "reason": "sl_tp_exchange",
                }
                self.closed_trades.append(trade)
                closed.append(trade)
                logger.info(f"[BLOFIN] {symbol} closed by exchange @ {price:.4f} | PnL≈{pnl:+.2f}")
                continue

            # Time stop
            if (now - pos.opened_at) > timedelta(hours=self.time_stop_hours):
                if pos.unrealized_pnl_pct(price) <= 0:
                    t = await self.close_position(symbol, price, "time_stop", storage)
                    if t:
                        closed.append(t)

        await self._refresh_balance()
        return closed

    # ── Update SL / TP ────────────────────────────────────────────────────────

    def update_stop(self, symbol: str, new_stop: float) -> bool:
        pos = self.positions.get(symbol)
        if pos is None:
            return False
        pos.stop_loss = new_stop
        logger.info(f"[BLOFIN] Stop updated locally {symbol} → {new_stop:.4f}")
        return True

    def update_tp(self, symbol: str, new_tp: float) -> bool:
        pos = self.positions.get(symbol)
        if pos is None:
            return False
        pos.take_profit = new_tp
        logger.info(f"[BLOFIN] TP updated locally {symbol} → {new_tp:.4f}")
        return True

    def summary(self) -> dict:
        wins = [t for t in self.closed_trades if t["pnl"] >= 0]
        total = len(self.closed_trades)
        return {
            "balance": self.balance,
            "equity": self.equity,
            "open_positions": len(self.positions),
            "total_trades": total,
            "win_rate": len(wins) / total if total else 0.0,
            "total_pnl": self.total_pnl,
            "daily_pnl_pct": self.daily_pnl_pct,
            "drawdown_from_peak": self.drawdown_from_peak,
        }
