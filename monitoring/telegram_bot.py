"""
Telegram command handler — polls getUpdates and dispatches bot commands.
Only responds to messages from the authorized TELEGRAM_CHAT_ID.

Commands:
  /status          — mode, loop count, circuit breaker, uptime
  /balance         — balance + total PnL
  /positions       — list open positions with PnL
  /trades          — last 5 closed trades
  /start           — resume bot loop
  /stop            — stop loop (hold open positions)
  /stopall         — stop loop + close all positions at market
  /pause           — keep loop running but block new entries
  /resume          — unblock new entries
  /strategies      — show all strategies and their on/off status + bandit weights
  /enable <name>   — enable a strategy  (e.g. /enable ifvg)
  /disable <name>  — disable a strategy (e.g. /disable sentiment)
  /risk            — show current risk parameters
  /setrisk <p> <v> — change a risk param (e.g. /setrisk max_open_positions 3)
  /postmortem      — loss attribution summary (why trades are losing)
  /signals         — last signal from each strategy on each symbol
  /update          — git pull + docker compose rebuild (VPS only)
  /help            — show this list
"""
import asyncio
import os
import subprocess
from datetime import datetime, timezone

import httpx
from loguru import logger

from web.state import BotState

_STRATEGY_NAMES = ["momentum", "mean_reversion", "trend_following", "ml_xgboost", "sentiment", "ifvg"]

_RISK_EDITABLE = {
    "max_open_positions":          ("max_open_positions",        int),
    "max_loss_pct":                ("max_loss_pct_per_trade",    float),
    "daily_circuit_breaker":       ("daily_loss_circuit_breaker",float),
    "atr_multiplier":              ("trailing_stop_atr_multiplier", float),
    "max_drawdown":                ("max_portfolio_drawdown",    float),
}


class TelegramCommandBot:
    def __init__(self, token: str, chat_id: str, bot_state: BotState):
        self._token = token
        self._chat_id = str(chat_id)
        self._state = bot_state
        self._base = f"https://api.telegram.org/bot{token}"
        self._offset = 0
        self._running = False

    def start(self):
        self._running = True
        asyncio.create_task(self._poll_loop(), name="tg_command_bot")
        logger.info("Telegram command bot started — send /help to your bot")

    def stop(self):
        self._running = False

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
            parts = text.split()
            cmd = parts[0].lower()
            reply = await self._dispatch(cmd, parts, full_text=text)
            await self._send(client, reply)

    async def _send(self, client: httpx.AsyncClient, text: str):
        try:
            await client.post(
                f"{self._base}/sendMessage",
                json={"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"},
            )
        except Exception as e:
            logger.debug(f"Telegram reply failed: {e}")

    async def _dispatch(self, cmd: str, parts: list[str], full_text: str) -> str:
        state = self._state
        trader = state.paper_trader
        prices = state.current_prices

        # ── Help ──────────────────────────────────────────────────────────────

        if cmd == "/help":
            return (
                "📋 <b>Commands</b>\n\n"
                "<b>Monitoring</b>\n"
                "/status — bot status &amp; uptime\n"
                "/balance — balance &amp; PnL\n"
                "/positions — open positions\n"
                "/trades — last 5 closed trades\n"
                "/signals — latest signal per symbol\n"
                "/postmortem — why trades are losing\n\n"
                "<b>Control</b>\n"
                "/start — start loop\n"
                "/stop — stop (hold positions)\n"
                "/stopall — stop + close all\n"
                "/pause — block new entries\n"
                "/resume — allow entries\n\n"
                "<b>Strategy</b>\n"
                "/strategies — show strategy status\n"
                "/enable &lt;name&gt; — enable a strategy\n"
                "/disable &lt;name&gt; — disable a strategy\n\n"
                "<b>Risk</b>\n"
                "/risk — show risk params\n"
                "/setrisk &lt;param&gt; &lt;value&gt;\n\n"
                "<b>System</b>\n"
                "/update — pull latest &amp; rebuild"
            )

        # ── Status ────────────────────────────────────────────────────────────

        if cmd == "/status":
            uptime = int((datetime.now(timezone.utc) - state.started_at).total_seconds())
            h, m = divmod(uptime // 60, 60)
            cb = "🔴 TRIPPED" if state.circuit_breaker_active else "✅ OK"
            open_pos = len(trader.positions) if trader else 0
            return (
                f"🤖 <b>Bot Status</b>\n"
                f"Mode: <code>{state.mode}</code>\n"
                f"Loop: {'▶️ running' if state.running else '⏹ stopped'}"
                f"{' (paused)' if state.paused else ''}\n"
                f"Loop #: <code>{state.loop_count}</code>\n"
                f"Open positions: <code>{open_pos}</code>\n"
                f"Circuit breaker: {cb}\n"
                f"Uptime: <code>{h}h {m}m</code>"
            )

        # ── Balance ───────────────────────────────────────────────────────────

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
                f"Win rate: <code>{s['win_rate']:.1%}</code> ({s['total_trades']} trades)\n"
                f"Drawdown: <code>{s['drawdown_from_peak']:.1%}</code>"
            )

        # ── Positions ─────────────────────────────────────────────────────────

        if cmd == "/positions":
            if trader is None or not trader.positions:
                return "📭 No open positions"
            lines = ["📊 <b>Open Positions</b>"]
            for sym, pos in trader.positions.items():
                price = prices.get(sym, pos.entry_price)
                pnl = pos.unrealized_pnl(price)
                pnl_pct = pos.unrealized_pnl_pct(price)
                short = sym.replace("/USDT:USDT", "")
                emoji = "🟢" if pnl >= 0 else "🔴"
                lines.append(
                    f"{emoji} <b>{short}</b> {pos.side} @ <code>{pos.entry_price:.4f}</code>\n"
                    f"  Now: <code>{price:.4f}</code> | PnL: <code>{pnl:+.2f} ({pnl_pct:+.1%})</code>\n"
                    f"  SL: <code>{pos.stop_loss:.4f}</code> | TP: <code>{pos.take_profit:.4f}</code>\n"
                    f"  Strategy: <code>{pos.strategy}</code>"
                )
            return "\n".join(lines)

        # ── Trades ────────────────────────────────────────────────────────────

        if cmd == "/trades":
            if trader is None or not trader.closed_trades:
                return "📭 No closed trades yet"
            recent = list(reversed(trader.closed_trades))[:5]
            lines = ["📜 <b>Last 5 Trades</b>"]
            for t in recent:
                e = "✅" if t["pnl"] >= 0 else "❌"
                short = t["symbol"].replace("/USDT:USDT", "")
                lines.append(
                    f"{e} {short} {t['side']} — <code>{t['pnl']:+.2f}</code> ({t['reason']})"
                )
            return "\n".join(lines)

        # ── Signals ───────────────────────────────────────────────────────────

        if cmd == "/signals":
            if not state.last_signals:
                return "📭 No signals yet — wait for the next loop"
            lines = ["📡 <b>Latest Signals</b>"]
            for sym, sig in state.last_signals.items():
                short = sym.replace("/USDT:USDT", "")
                action = sig.get("action", "HOLD")
                conf = sig.get("confidence", 0)
                consensus = sig.get("consensus_score", 0)
                emoji = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "⚪"
                lines.append(f"{emoji} <b>{short}</b>: {action} | conf={conf:.2f} | score={consensus:+.3f}")
                cs = sig.get("component_signals", {})
                cc = sig.get("component_confidences", {})
                for strat, vote in cs.items():
                    v_emoji = "↑" if vote == "BUY" else "↓" if vote == "SELL" else "—"
                    lines.append(f"  {v_emoji} {strat}: {vote} ({cc.get(strat, 0):.2f})")
            return "\n".join(lines)

        # ── Strategies ────────────────────────────────────────────────────────

        if cmd == "/strategies":
            enabled = state.strategy_enabled
            # Try to get bandit weights if available
            bandit = getattr(state, "_bandit", None)
            weights = bandit.current_weights() if bandit else {}

            lines = ["⚙️ <b>Strategies</b>"]
            for name in _STRATEGY_NAMES:
                on = enabled.get(name, True)
                status = "✅ ON " if on else "❌ OFF"
                w = weights.get(name)
                w_str = f" | weight={w:.2f}" if w else ""
                lines.append(f"{status} <code>{name}</code>{w_str}")
            lines.append("\nUse /enable &lt;name&gt; or /disable &lt;name&gt;")
            return "\n".join(lines)

        # ── Enable strategy ───────────────────────────────────────────────────

        if cmd == "/enable":
            if len(parts) < 2:
                return "Usage: /enable &lt;strategy_name&gt;\nStrategies: " + ", ".join(_STRATEGY_NAMES)
            name = parts[1].lower()
            if name not in _STRATEGY_NAMES:
                return f"❓ Unknown strategy: <code>{name}</code>\nValid: {', '.join(_STRATEGY_NAMES)}"
            state.strategy_enabled[name] = True
            state.log_activity("system", f"Strategy {name} enabled via Telegram")
            logger.info(f"[Telegram] Strategy {name} enabled")
            return f"✅ <code>{name}</code> enabled — takes effect next loop"

        # ── Disable strategy ──────────────────────────────────────────────────

        if cmd == "/disable":
            if len(parts) < 2:
                return "Usage: /disable &lt;strategy_name&gt;\nStrategies: " + ", ".join(_STRATEGY_NAMES)
            name = parts[1].lower()
            if name not in _STRATEGY_NAMES:
                return f"❓ Unknown strategy: <code>{name}</code>\nValid: {', '.join(_STRATEGY_NAMES)}"
            state.strategy_enabled[name] = False
            state.log_activity("system", f"Strategy {name} disabled via Telegram")
            logger.info(f"[Telegram] Strategy {name} disabled")
            return f"❌ <code>{name}</code> disabled — takes effect next loop"

        # ── Risk params ───────────────────────────────────────────────────────

        if cmd == "/risk":
            try:
                from trading_engine.risk_calculator import RiskCalculator
                from config.settings import load_trading_params
                p = load_trading_params()["risk"]
                return (
                    f"🛡 <b>Risk Parameters</b>\n"
                    f"Max open positions: <code>{p.get('max_open_positions', '?')}</code>\n"
                    f"Max loss/trade: <code>{p.get('max_loss_pct_per_trade', 0):.1%}</code>\n"
                    f"Daily circuit breaker: <code>{p.get('daily_loss_circuit_breaker', 0):.1%}</code>\n"
                    f"ATR stop multiplier: <code>{p.get('trailing_stop_atr_multiplier', '?')}×</code>\n"
                    f"Max drawdown halt: <code>{p.get('max_portfolio_drawdown', 0):.1%}</code>\n"
                    f"Max exposure: <code>{p.get('max_total_exposure_pct', 0):.0%}</code>\n\n"
                    f"<i>Change with: /setrisk &lt;param&gt; &lt;value&gt;</i>\n"
                    f"Params: max_open_positions, max_loss_pct, daily_circuit_breaker, atr_multiplier, max_drawdown"
                )
            except Exception as e:
                return f"❌ Could not load risk params: {e}"

        if cmd == "/setrisk":
            if len(parts) < 3:
                return "Usage: /setrisk &lt;param&gt; &lt;value&gt;\nExample: /setrisk max_open_positions 3"
            param_alias = parts[1].lower()
            if param_alias not in _RISK_EDITABLE:
                return (
                    f"❓ Unknown param: <code>{param_alias}</code>\n"
                    f"Valid: {', '.join(_RISK_EDITABLE.keys())}"
                )
            yaml_key, cast = _RISK_EDITABLE[param_alias]
            try:
                value = cast(parts[2])
            except ValueError:
                return f"❌ Invalid value: <code>{parts[2]}</code> — expected {'integer' if cast is int else 'decimal'}"
            try:
                import yaml
                from pathlib import Path
                params_path = Path("config/trading_params.yaml")
                with open(params_path) as f:
                    params = yaml.safe_load(f)
                params["risk"][yaml_key] = value
                with open(params_path, "w") as f:
                    yaml.dump(params, f, default_flow_style=False, sort_keys=False)
                state.log_activity("system", f"Risk param {yaml_key}={value} set via Telegram")
                logger.info(f"[Telegram] Risk param updated: {yaml_key} = {value}")
                return f"✅ <code>{yaml_key}</code> set to <code>{value}</code>\nTakes effect on next loop restart."
            except Exception as e:
                return f"❌ Failed to update param: {e}"

        # ── Post-mortem ───────────────────────────────────────────────────────

        if cmd == "/postmortem":
            pm = getattr(state, "_post_mortem", None)
            if pm is None:
                return "📭 No post-mortem data yet — needs closed trades"
            s = pm.summary()
            if s["total"] == 0:
                return "📭 No closed trades analysed yet"
            buckets = s.get("buckets", {})
            lines = [
                f"🔬 <b>Loss Attribution</b> ({s['total']} trades)\n"
                f"Win rate: <code>{s['win_rate']:.1%}</code> ({s['wins']}W / {s['losses']}L)\n"
                f"Top loss reason: <code>{s.get('top_loss_reason', 'n/a')}</code>\n"
            ]
            loss_buckets = {k: v for k, v in buckets.items() if k != "win"}
            if loss_buckets:
                lines.append("<b>Loss breakdown:</b>")
                for reason, count in sorted(loss_buckets.items(), key=lambda x: -x[1]):
                    pct = count / s["total"] * 100
                    lines.append(f"  • {reason}: <code>{count}</code> ({pct:.0f}%)")
            return "\n".join(lines)

        # ── Bot controls ──────────────────────────────────────────────────────

        if cmd == "/start":
            state.running = True
            state.paused = False
            state.log_activity("system", "Bot started via Telegram")
            return "▶️ Bot started — loop running"

        if cmd == "/stop":
            state.running = False
            state.log_activity("system", "Bot stopped via Telegram (positions held)")
            return "⏹ Bot stopped — open positions held with stops active"

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
            state.log_activity("system", "Bot stopped + all positions closed via Telegram")
            suffix = f" — closed: {', '.join(closed_syms)}" if closed_syms else " — no open positions"
            return f"🛑 Bot stopped{suffix}"

        if cmd == "/pause":
            state.paused = True
            state.log_activity("system", "Bot paused via Telegram")
            return "⏸ Paused — signals still run but no new entries"

        if cmd == "/resume":
            state.paused = False
            state.log_activity("system", "Bot resumed via Telegram")
            return "▶️ Resumed — new entries allowed"

        # ── Update (VPS) ──────────────────────────────────────────────────────

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
                    capture_output=True, text=True, timeout=300,
                )
                lines = (result.stdout + result.stderr).strip().splitlines()
                tail = "\n".join(lines[-15:])
                rc = result.returncode
                status = "✅ Update complete" if rc == 0 else f"❌ Update failed (exit {rc})"
                return f"{status}\n<pre>{tail}</pre>"
            except subprocess.TimeoutExpired:
                return "⏳ Update timed out — check VPS manually"
            except Exception as e:
                return f"❌ Update error: {e}"

        return f"❓ Unknown command: <code>{cmd}</code>\nSend /help for the list"
