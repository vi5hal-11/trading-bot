import asyncio
from loguru import logger
from config.settings import Settings

try:
    from telegram import Bot
    from telegram.error import TelegramError
    _HAS_TELEGRAM = True
except ImportError:
    _HAS_TELEGRAM = False


class TelegramAlerts:
    def __init__(self, settings: Settings):
        self.enabled = bool(settings.telegram_bot_token and settings.telegram_chat_id)
        self.chat_id = settings.telegram_chat_id
        self._token = settings.telegram_bot_token
        self._bot: "Bot | None" = None

        if not _HAS_TELEGRAM:
            logger.warning("python-telegram-bot not installed — Telegram alerts disabled")

    async def start(self):
        """Initialize the HTTP session. Must be called once before first send()."""
        if not self.enabled or not _HAS_TELEGRAM:
            return
        self._bot = Bot(token=self._token)
        await self._bot.initialize()
        logger.info("Telegram bot initialized — alerts active")

    async def close(self):
        """Cleanly shut down the HTTP session."""
        if self._bot is not None:
            try:
                await self._bot.shutdown()
            except Exception:
                pass
            self._bot = None

    async def send(self, message: str):
        if not self.enabled or self._bot is None:
            logger.info(f"[ALERT] {message}")
            return
        try:
            await self._bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode="HTML",
            )
        except TelegramError as e:
            logger.warning(f"Telegram send failed: {e}")
            # Reconnect on network errors so subsequent sends can recover
            try:
                await self._bot.shutdown()
                await self._bot.initialize()
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Telegram unexpected error: {e}")

    async def send_signal(self, symbol: str, signal: dict, price: float):
        action = signal["action"]
        conf = signal["confidence"]
        consensus = signal.get("consensus_score", 0)
        emoji = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "⚪"

        msg = (
            f"{emoji} <b>{action}</b> — {symbol}\n"
            f"Price: <code>{price:.4f}</code>\n"
            f"Confidence: <code>{conf:.2%}</code>\n"
            f"Consensus: <code>{consensus:+.4f}</code>"
        )
        await self.send(msg)

    async def send_trade_open(self, pos):
        emoji = "🟢" if pos.side == "BUY" else "🔴"
        msg = (
            f"{emoji} <b>PAPER OPEN</b> — {pos.symbol}\n"
            f"Side: {pos.side} | Qty: <code>{pos.quantity:.4f}</code>\n"
            f"Entry: <code>{pos.entry_price:.4f}</code>\n"
            f"Stop: <code>{pos.stop_loss:.4f}</code>"
        )
        await self.send(msg)

    async def send_trade_close(self, trade: dict):
        pnl = trade["pnl"]
        emoji = "✅" if pnl >= 0 else "❌"
        msg = (
            f"{emoji} <b>PAPER CLOSE</b> — {trade['symbol']}\n"
            f"PnL: <code>{pnl:+.2f} USDT ({trade['pnl_pct']:+.2%})</code>\n"
            f"Reason: {trade['reason']}"
        )
        await self.send(msg)

    async def send_portfolio_summary(self, summary: dict):
        pnl = summary["total_pnl"]
        emoji = "📈" if pnl >= 0 else "📉"
        msg = (
            f"{emoji} <b>Portfolio Summary</b>\n"
            f"Balance: <code>{summary['balance']:.2f} USDT</code>\n"
            f"Total PnL: <code>{pnl:+.2f} USDT</code>\n"
            f"Daily: <code>{summary['daily_pnl_pct']:+.2%}</code>\n"
            f"Win Rate: <code>{summary['win_rate']:.1%}</code> "
            f"({summary['total_trades']} trades)\n"
            f"Open Positions: {summary['open_positions']}"
        )
        await self.send(msg)

    async def send_drawdown_warning(self, drawdown_pct: float):
        msg = (
            f"⚠️ <b>Drawdown Warning</b>\n"
            f"Portfolio is <code>{drawdown_pct:.2%}</code> below peak.\n"
            f"Halt triggers at 15%. Review open positions."
        )
        await self.send(msg)

    async def send_drawdown_halt(self, drawdown_pct: float):
        msg = (
            f"🛑 <b>Drawdown Halt</b>\n"
            f"Portfolio dropped <code>{drawdown_pct:.2%}</code> from peak.\n"
            f"All positions closed. Trading paused until recovery."
        )
        await self.send(msg)

    async def send_circuit_breaker(self, reason: str):
        msg = (
            f"⚡ <b>Circuit Breaker Triggered</b>\n"
            f"No new positions will open.\n"
            f"Reason: <code>{reason}</code>"
        )
        await self.send(msg)

    async def send_daily_digest(self, summary: dict):
        pnl = summary["total_pnl"]
        daily = summary["daily_pnl_pct"]
        dd = summary.get("drawdown_from_peak", 0)
        emoji = "📈" if daily >= 0 else "📉"
        msg = (
            f"{emoji} <b>Daily Digest</b>\n"
            f"Balance: <code>{summary['balance']:.2f} USDT</code>\n"
            f"Day PnL: <code>{daily:+.2%}</code> | Total: <code>{pnl:+.2f} USDT</code>\n"
            f"Drawdown: <code>{dd:.2%}</code> from peak\n"
            f"Trades: {summary['total_trades']} | Win Rate: <code>{summary['win_rate']:.1%}</code>"
        )
        await self.send(msg)

    async def send_retrain_result(self, version: str, promoted: bool,
                                   sharpe: float, cv_acc: float):
        emoji = "✅" if promoted else "ℹ️"
        status = "PROMOTED to champion" if promoted else "Challenger did not beat champion"
        msg = (
            f"{emoji} <b>ML Retrain Complete</b>\n"
            f"Version: <code>{version}</code>\n"
            f"Status: {status}\n"
            f"Sharpe: <code>{sharpe:.3f}</code> | CV Acc: <code>{cv_acc:.4f}</code>"
        )
        await self.send(msg)
