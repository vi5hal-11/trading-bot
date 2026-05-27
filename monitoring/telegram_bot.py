"""
Telegram command handler — polls getUpdates and dispatches bot commands.
Only responds to messages from the authorized TELEGRAM_CHAT_ID.

Commands:
  /status      — mode, loop count, circuit breaker, uptime
  /balance     — balance + total PnL
  /positions   — list open positions with PnL
  /trades      — last 5 closed trades
  /start       — resume bot loop
  /stop        — stop loop (hold open positions)
  /stopall     — stop loop + close all positions at market
  /pause       — keep loop running but block new entries
  /resume      — unblock new entries
  /update      — git pull + docker compose rebuild (VPS only)
  /help        — show this list
"""
import asyncio
import os
import subprocess
from datetime import datetime, timezone

import httpx
from loguru import logger

from web.state import BotState


class TelegramCommandBot:
    def __init__(self, token: str, chat_id: str, bot_state: BotState):
        self._token = token
        self._chat_id = str(chat_id)
        self._state = bot_state
        self._base = f"https://api.telegram.org/bot{token}"
        self._offset = 0
        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        self._running = True
        asyncio.create_task(self._poll_loop(), name="tg_command_bot")
        logger.info("Telegram command bot started — send /help to your bot")

    def stop(self):
        self._running = False

    # ── Polling loop ──────────────────────────────────────────────────────────

    async def _poll_loop(self):
        async with httpx.AsyncClient(timeout=35.0) as client:
            while self._running:
                try:
                    await self._poll(client)
                except Exception as e:
                    logger.debug(f"Telegram poll error: {e}")
                await asyncio.sleep(2)

    async def _poll(self, client: httpx.AsyncClient):
        r = await client.get(
            f"{self._base}/getUpdates",
            params={"offset": self._offset, "timeout": 25, "allowed_updates": ["message"]},
        )
        if r.status_code != 200:
            return
        data = r.json()
        for update in data.get("result", []):
            self._offset = update["update_id"] + 1
            msg = update.get("message", {})
            chat_id = str(msg.get("chat", {}).get("id", ""))
            text = (msg.get("text") or "").strip()
            if chat_id != self._chat_id or not text.startswith("/"):
                continue
            reply = await self._dispatch(text.split()[0].lower(), text)
            await self._send(client, reply)

    async def _send(self, client: httpx.AsyncClient, text: str):
        try:
            await client.post(
                f"{self._base}/sendMessage",
                json={"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"},
            )
        except Exception as e:
            logger.debug(f"Telegram reply failed: {e}")

    # ── Command dispatch ──────────────────────────────────────────────────────

    async def _dispatch(self, cmd: str, full_text: str) -> str:
        state = self._state
        trader = state.paper_trader
        prices = state.current_prices

        if cmd == "/help":
            return (
                "📋 <b>Commands</b>\n"
                "/status — bot status\n"
                "/balance — balance & PnL\n"
                "/positions — open positions\n"
                "/trades — last 5 closed\n"
                "/start — start loop\n"
                "/stop — stop (hold positions)\n"
                "/stopall — stop + close all\n"
                "/pause — no new entries\n"
                "/resume — allow entries\n"
                "/update — pull latest & rebuild"
            )

        if cmd == "/status":
            uptime = int((datetime.now(timezone.utc) - state.started_at).total_seconds())
            h, m = divmod(uptime // 60, 60)
            cb = "🔴 ACTIVE" if state.circuit_breaker_active else "✅ OK"
            return (
                f"🤖 <b>Bot Status</b>\n"
                f"Mode: <code>{state.mode}</code>\n"
                f"Loop: {'▶️ running' if state.running else '⏹ stopped'}"
                f"{' (paused)' if state.paused else ''}\n"
                f"Loop #: <code>{state.loop_count}</code>\n"
                f"Circuit breaker: {cb}\n"
                f"Uptime: <code>{h}h {m}m</code>"
            )

        if cmd == "/balance":
            if trader is None:
                return "⚠️ Trader not ready"
            s = trader.summary()
            pnl_emoji = "📈" if s["total_pnl"] >= 0 else "📉"
            return (
                f"{pnl_emoji} <b>Balance</b>\n"
                f"Balance: <code>{s['balance']:.2f} USDT</code>\n"
                f"Total PnL: <code>{s['total_pnl']:+.2f} USDT</code>\n"
                f"Daily: <code>{s['daily_pnl_pct']:+.2%}</code>\n"
                f"Win rate: <code>{s['win_rate']:.1%}</code> ({s['total_trades']} trades)"
            )

        if cmd == "/positions":
            if trader is None or not trader.positions:
                return "📭 No open positions"
            lines = ["📊 <b>Open Positions</b>"]
            for sym, pos in trader.positions.items():
                price = prices.get(sym, pos.entry_price)
                pnl = pos.unrealized_pnl(price)
                short = sym.replace("/USDT:USDT", "")
                lines.append(
                    f"• {short} {pos.side} @ <code>{pos.entry_price:.4f}</code>\n"
                    f"  Now: <code>{price:.4f}</code> | uPnL: <code>{pnl:+.2f}</code>\n"
                    f"  SL: <code>{pos.stop_loss:.4f}</code> | TP: <code>{pos.take_profit:.4f}</code>"
                )
            return "\n".join(lines)

        if cmd == "/trades":
            if trader is None or not trader.closed_trades:
                return "📭 No closed trades yet"
            recent = list(reversed(trader.closed_trades))[:5]
            lines = ["📜 <b>Last 5 Trades</b>"]
            for t in recent:
                e = "✅" if t["pnl"] >= 0 else "❌"
                short = t["symbol"].replace("/USDT:USDT", "")
                lines.append(
                    f"{e} {short} {t['side']} — PnL <code>{t['pnl']:+.2f}</code> ({t['reason']})"
                )
            return "\n".join(lines)

        if cmd == "/start":
            state.running = True
            state.paused = False
            state.log_activity("system", "Bot started via Telegram")
            return "▶️ Bot started — loop running"

        if cmd == "/stop":
            state.running = False
            state.log_activity("system", "Bot stopped via Telegram (positions held)")
            return "⏹ Bot stopped — open positions are still running with stops active"

        if cmd == "/stopall":
            state.running = False
            if trader is None:
                return "⏹ Bot stopped — no trader active"
            closed_syms = []
            for sym in list(trader.positions.keys()):
                price = prices.get(sym, trader.positions[sym].entry_price)
                t = await trader.close_position(sym, price, "telegram_stopall")
                if t:
                    closed_syms.append(sym.replace("/USDT:USDT", ""))
            state.log_activity("system", f"Bot stopped + all positions closed via Telegram")
            suffix = f" — closed: {', '.join(closed_syms)}" if closed_syms else " — no open positions"
            return f"🛑 Bot stopped{suffix}"

        if cmd == "/pause":
            state.paused = True
            state.log_activity("system", "Bot paused via Telegram")
            return "⏸ Paused — signals still run but no new entries will open"

        if cmd == "/resume":
            state.paused = False
            state.log_activity("system", "Bot resumed via Telegram")
            return "▶️ Resumed — new entries are now allowed"

        if cmd == "/update":
            update_script = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "update.sh",
            )
            if not os.path.isfile(update_script):
                return "⚠️ update.sh not found — are you on the VPS?"
            try:
                result = subprocess.run(
                    ["bash", update_script],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                lines = (result.stdout + result.stderr).strip().splitlines()
                tail = "\n".join(lines[-15:])
                rc = result.returncode
                status = "✅ Update complete" if rc == 0 else f"❌ Update failed (exit {rc})"
                return f"{status}\n<pre>{tail}</pre>"
            except subprocess.TimeoutExpired:
                return "⏳ Update timed out after 5 min — check the VPS manually"
            except Exception as e:
                return f"❌ Update error: {e}"

        return f"❓ Unknown command: <code>{cmd}</code>\nSend /help for the list"
