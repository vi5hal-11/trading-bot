"""
BinanceTrader — places real orders on Binance USDT-M perpetual futures via CCXT.
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
    sl_order_id: Optional[str] = None
    tp_order_id: Optional[str] = None
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


class BinanceTrader:
    """Live/testnet trading engine backed by Binance USDT-M futures via CCXT."""

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
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="binance")

        exc_kwargs: dict = {
            "apiKey": settings.binance_api_key,
            "secret": settings.binance_secret_key,
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        }

        self._is_demo = settings.binance_testnet
        self._exchange = ccxt.binanceusdm(exc_kwargs)

        if settings.binance_testnet:
            # Apply demo-fapi.binance.com URLs manually — options['demo'] flag
            # doesn't auto-switch URLs in CCXT 4.x for binanceusdm
            demo_urls = self._exchange.urls.get("demo", {})
            if isinstance(demo_urls, dict) and demo_urls:
                api_urls = self._exchange.urls.get("api", {})
                if isinstance(api_urls, dict):
                    api_urls.update(demo_urls)
                    self._exchange.urls["api"] = api_urls
            logger.info("BinanceTrader: DEMO mode — demo-fapi.binance.com (fake money)")
        else:
            logger.warning("BinanceTrader: LIVE mode — real money at risk ⚠️")

        # Disable sapi currency fetch (no demo equivalent) then pre-load markets
        self._exchange.options["fetchCurrencies"] = False
        self._exchange.load_markets()

        # Probe connection and get starting balance
        self.balance: float = self._fetch_usdt_balance_sync()
        self._session_start = self.balance
        self._daily_start = self.balance
        self._intraday_start = self.balance
        self._intraday_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._peak_equity = self.balance
        mode_str = "DEMO" if settings.binance_testnet else "LIVE"
        logger.info(f"BinanceTrader ready [{mode_str}] — balance={self.balance:.2f} USDT")

    # ── Async CCXT helper ─────────────────────────────────────────────────────

    async def _run(self, fn, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, partial(fn, *args, **kwargs))

    def _fetch_usdt_balance_sync(self) -> float:
        """Use v2 account endpoint — works on both demo and live, avoids sapi."""
        try:
            acct = self._exchange.fapiPrivateV2GetAccount()
            for asset in acct.get("assets", []):
                if asset.get("asset") == "USDT":
                    return float(asset.get("availableBalance") or asset.get("walletBalance") or 0)
        except Exception as e:
            logger.warning(f"Balance fetch via v2 account failed: {e}")
        return 0.0

    async def _refresh_balance(self):
        try:
            new_bal = await self._run(self._fetch_usdt_balance_sync)
            if new_bal > 0:
                self.balance = new_bal
            else:
                logger.warning("Balance refresh returned 0 — keeping last known balance")
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

    async def _place_sl_tp_orders(
        self, symbol: str, pos_side: str, qty: float, stop_loss: float, take_profit: float
    ) -> tuple[Optional[str], Optional[str]]:
        """Place separate STOP_MARKET and TAKE_PROFIT_MARKET orders for SL/TP."""
        close_side = "sell" if pos_side == "BUY" else "buy"
        sl_id = tp_id = None

        try:
            sl_order = await self._run(
                self._exchange.create_order,
                symbol,
                "STOP_MARKET",
                close_side,
                qty,
                None,
                {"stopPrice": stop_loss, "reduceOnly": True, "closePosition": False},
            )
            sl_id = str(sl_order.get("id", ""))
        except Exception as e:
            logger.warning(f"[BINANCE] SL order failed {symbol}: {e}")

        try:
            tp_order = await self._run(
                self._exchange.create_order,
                symbol,
                "TAKE_PROFIT_MARKET",
                close_side,
                qty,
                None,
                {"stopPrice": take_profit, "reduceOnly": True, "closePosition": False},
            )
            tp_id = str(tp_order.get("id", ""))
        except Exception as e:
            logger.warning(f"[BINANCE] TP order failed {symbol}: {e}")

        return sl_id, tp_id

    async def _cancel_sl_tp(self, symbol: str, pos: Position):
        for order_id in [pos.sl_order_id, pos.tp_order_id]:
            if order_id:
                try:
                    await self._run(self._exchange.cancel_order, order_id, symbol)
                except Exception:
                    pass  # already filled or cancelled

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
            logger.debug(f"[BINANCE] Cannot open {symbol}: {reason}")
            return None

        ok, reason = self.risk.circuit_breaker(self.daily_pnl_pct, self.intraday_pnl_pct)
        if not ok:
            logger.warning(f"[BINANCE] Circuit breaker: {reason}")
            return None

        ok, reason = self.risk.drawdown_breaker(self.drawdown_from_peak)
        if not ok:
            logger.warning(f"[BINANCE] Drawdown halt: {reason}")
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
            )
            order_id = str(order.get("id", ""))
        except Exception as e:
            logger.error(f"[BINANCE] Market order failed {symbol} {side}: {e}")
            return None

        # Place separate SL/TP orders (Binance futures requirement)
        sl_id, tp_id = await self._place_sl_tp_orders(symbol, side, qty, stop_loss, take_profit)

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
            sl_order_id=sl_id,
            tp_order_id=tp_id,
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
            f"[BINANCE] OPEN {side} {symbol} @ {current_price:.4f} | "
            f"qty={qty:.4f} | sl={stop_loss:.4f} | tp={take_profit:.4f} | "
            f"order={order_id} sl_order={sl_id} tp_order={tp_id}"
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

        # Cancel outstanding SL/TP orders first
        await self._cancel_sl_tp(symbol, pos)

        close_side = "sell" if pos.side == "BUY" else "buy"
        try:
            await self._run(
                self._exchange.create_order,
                symbol,
                "market",
                close_side,
                pos.quantity,
                None,
                {"reduceOnly": True},
            )
        except Exception as e:
            logger.error(f"[BINANCE] Close failed {symbol}: {e}")

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
        logger.info(f"[BINANCE] CLOSE {symbol} @ {current_price:.4f} | PnL≈{pnl:+.2f} | {reason}")
        return trade

    # ── Sync with exchange (detect SL/TP hits) ────────────────────────────────

    async def check_stops_and_targets(
        self, prices: dict[str, float], storage=None
    ) -> list[dict]:
        closed = []

        ok, reason = self.risk.drawdown_breaker(self.drawdown_from_peak)
        if not ok:
            logger.warning(f"[BINANCE] Drawdown halt — closing all. {reason}")
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
                logger.info(f"[BINANCE] {symbol} closed by exchange @ {price:.4f} | PnL≈{pnl:+.2f}")
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
        logger.info(f"[BINANCE] Stop updated locally {symbol} → {new_stop:.4f}")
        return True

    def update_tp(self, symbol: str, new_tp: float) -> bool:
        pos = self.positions.get(symbol)
        if pos is None:
            return False
        pos.take_profit = new_tp
        logger.info(f"[BINANCE] TP updated locally {symbol} → {new_tp:.4f}")
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
