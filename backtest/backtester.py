from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dataclasses import dataclass, field
import pandas as pd
from loguru import logger

from trading_engine.risk_calculator import RiskCalculator
from backtest.metrics import compile_metrics

SLIPPAGE = 0.0005       # 0.05% per side
COMMISSION = 0.0006     # 0.06% Blofin taker fee per side
WINDOW = 250            # rolling candles fed to strategies
TIME_STOP_BARS = 16     # 4h at 15m
TP1_PCT = 0.01
TP2_PCT = 0.02
TP1_RATIO = 0.25        # close 25% at TP1
TP2_RATIO = 0.50        # close 50% of remaining at TP2


@dataclass
class BacktestPosition:
    symbol: str
    side: str            # BUY | SELL
    entry_price: float
    quantity: float
    stop_loss: float
    opened_bar: int      # bar index
    strategy: str = "ensemble"
    confidence: float = 0.0
    partial_tp1_done: bool = False
    partial_tp2_done: bool = False


@dataclass
class BacktestResult:
    trades: list[dict] = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=pd.Series)
    metrics: dict = field(default_factory=dict)


def _fill_price(price: float, side: str, is_entry: bool) -> float:
    """Apply slippage: entry buys higher, exits sell lower (conservative)."""
    factor = 1 + SLIPPAGE if side == "BUY" else 1 - SLIPPAGE
    if not is_entry:
        factor = 1 - SLIPPAGE if side == "BUY" else 1 + SLIPPAGE
    return price * factor


def _trade_pnl(pos: BacktestPosition, exit_price: float, qty: float) -> float:
    if pos.side == "BUY":
        gross = (exit_price - pos.entry_price) * qty
    else:
        gross = (pos.entry_price - exit_price) * qty
    cost = pos.entry_price * qty * COMMISSION + exit_price * qty * COMMISSION
    return gross - cost


class BacktestEngine:
    def __init__(self, initial_balance: float = 10_000.0, threshold: float = 0.10):
        self.initial_balance = initial_balance
        self.threshold = threshold  # consensus_score cutoff (lower than live 0.30 to get trade samples)
        self._risk = RiskCalculator()

    def run(self, df: pd.DataFrame, symbol: str, ensemble) -> BacktestResult:
        if len(df) < WINDOW + 1:
            logger.warning(f"{symbol}: not enough bars ({len(df)}) for backtesting")
            return BacktestResult()

        balance = self.initial_balance
        pos: BacktestPosition | None = None
        trades: list[dict] = []
        equity_ts: list[tuple] = []

        for i in range(WINDOW, len(df)):
            bar = df.iloc[i]
            bar_time = df.index[i]

            # ── Check open position ───────────────────────────────────
            if pos is not None:
                closed = False

                # Intra-bar stop-loss check (worst-case fill at stop price)
                if pos.side == "BUY" and bar["low"] <= pos.stop_loss:
                    exit_px = _fill_price(pos.stop_loss, pos.side, is_entry=False)
                    pnl = _trade_pnl(pos, exit_px, pos.quantity)
                    balance += pos.entry_price * pos.quantity + pnl  # return capital + pnl
                    trades.append(_make_trade(pos, exit_px, pnl, bar_time, i, "stop_loss"))
                    pos = None
                    closed = True

                elif pos.side == "SELL" and bar["high"] >= pos.stop_loss:
                    exit_px = _fill_price(pos.stop_loss, pos.side, is_entry=False)
                    pnl = _trade_pnl(pos, exit_px, pos.quantity)
                    balance += pos.entry_price * pos.quantity + pnl
                    trades.append(_make_trade(pos, exit_px, pnl, bar_time, i, "stop_loss"))
                    pos = None
                    closed = True

                if not closed:
                    close_price = bar["close"]
                    unrealized = _trade_pnl(pos, close_price, pos.quantity)

                    # Partial TP1
                    if not pos.partial_tp1_done:
                        tp1_hit = (pos.side == "BUY" and close_price >= pos.entry_price * (1 + TP1_PCT)) or \
                                  (pos.side == "SELL" and close_price <= pos.entry_price * (1 - TP1_PCT))
                        if tp1_hit:
                            qty1 = pos.quantity * TP1_RATIO
                            exit_px = _fill_price(close_price, pos.side, is_entry=False)
                            pnl1 = _trade_pnl(pos, exit_px, qty1)
                            balance += pos.entry_price * qty1 + pnl1
                            pos.quantity -= qty1
                            pos.partial_tp1_done = True
                            trades.append(_make_trade(pos, exit_px, pnl1, bar_time, i, "partial_tp1", qty=qty1))

                    # Partial TP2
                    if pos.partial_tp1_done and not pos.partial_tp2_done:
                        tp2_hit = (pos.side == "BUY" and close_price >= pos.entry_price * (1 + TP2_PCT)) or \
                                  (pos.side == "SELL" and close_price <= pos.entry_price * (1 - TP2_PCT))
                        if tp2_hit:
                            qty2 = pos.quantity * TP2_RATIO
                            exit_px = _fill_price(close_price, pos.side, is_entry=False)
                            pnl2 = _trade_pnl(pos, exit_px, qty2)
                            balance += pos.entry_price * qty2 + pnl2
                            pos.quantity -= qty2
                            pos.partial_tp2_done = True
                            trades.append(_make_trade(pos, exit_px, pnl2, bar_time, i, "partial_tp2", qty=qty2))

                    # Time-stop: close if open too long with no profit
                    bars_open = i - pos.opened_bar
                    if bars_open >= TIME_STOP_BARS and unrealized <= 0:
                        exit_px = _fill_price(close_price, pos.side, is_entry=False)
                        pnl = _trade_pnl(pos, exit_px, pos.quantity)
                        balance += pos.entry_price * pos.quantity + pnl
                        trades.append(_make_trade(pos, exit_px, pnl, bar_time, i, "time_stop"))
                        pos = None
                        closed = True

                if pos is not None:
                    unrealized = _trade_pnl(pos, bar["close"], pos.quantity)
                    equity = balance + unrealized
                else:
                    equity = balance
            else:
                equity = balance

            equity_ts.append((bar_time, equity))

            # ── Generate new signal (only if flat) ────────────────────
            if pos is None:
                window_df = df.iloc[i - WINDOW: i]
                try:
                    signal = ensemble.generate_signal(window_df, symbol)
                except Exception as e:
                    logger.warning(f"Signal error at bar {i}: {e}")
                    continue

                score = signal.get("consensus_score", 0.0)
                if abs(score) < self.threshold:
                    continue
                side = "BUY" if score > 0 else "SELL"
                atr = bar.get("atr", bar["close"] * 0.01)
                entry_raw = bar["close"]
                entry_px = _fill_price(entry_raw, side, is_entry=True)
                stop_loss = self._risk.stop_loss_price(entry_px, side, atr)
                qty = self._risk.position_size(balance, entry_px, stop_loss, signal["confidence"])

                if qty <= 0:
                    continue

                cost = entry_px * qty
                if cost > balance:
                    qty = balance / entry_px * 0.95  # use 95% of available

                balance -= entry_px * qty  # reserve capital
                pos = BacktestPosition(
                    symbol=symbol,
                    side=side,
                    entry_price=entry_px,
                    quantity=qty,
                    stop_loss=stop_loss,
                    opened_bar=i,
                    strategy=signal.get("strategy", "ensemble"),
                    confidence=signal["confidence"],
                )

        # Close any open position at end of period
        if pos is not None:
            last_bar = df.iloc[-1]
            last_time = df.index[-1]
            exit_px = _fill_price(last_bar["close"], pos.side, is_entry=False)
            pnl = _trade_pnl(pos, exit_px, pos.quantity)
            balance += pos.entry_price * pos.quantity + pnl
            trades.append(_make_trade(pos, exit_px, pnl, last_time, len(df) - 1, "end_of_period"))
            equity_ts[-1] = (equity_ts[-1][0], balance)

        equity_curve = pd.Series(
            [v for _, v in equity_ts],
            index=[t for t, _ in equity_ts],
        )

        m = compile_metrics(equity_curve, trades, self.initial_balance)
        return BacktestResult(trades=trades, equity_curve=equity_curve, metrics=m)


def _make_trade(
    pos: BacktestPosition,
    exit_price: float,
    pnl: float,
    exit_time,
    exit_bar: int,
    reason: str,
    qty: float | None = None,
) -> dict:
    q = qty if qty is not None else pos.quantity
    capital = pos.entry_price * q
    pnl_pct = pnl / capital if capital else 0.0
    return {
        "symbol": pos.symbol,
        "side": pos.side,
        "entry_price": pos.entry_price,
        "exit_price": exit_price,
        "quantity": q,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "reason": reason,
        "entry_bar": pos.opened_bar,
        "exit_bar": exit_bar,
        "duration_bars": exit_bar - pos.opened_bar,
        "exit_time": exit_time,
        "strategy": pos.strategy,
        "confidence": pos.confidence,
    }
