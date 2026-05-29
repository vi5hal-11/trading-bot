import asyncio
import sys
from loguru import logger

import uvicorn

from config.settings import Settings, load_trading_params
from data.fetcher import BlofinDataFetcher
from data.processor import DataProcessor
from data.storage import Storage
from monitoring.telegram_alerts import TelegramAlerts
from monitoring.telegram_bot import TelegramCommandBot
from strategies.momentum import MomentumStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.trend_following import TrendFollowingStrategy
from strategies.ml_xgboost import MLXGBoostStrategy
from strategies.sentiment import SentimentStrategy
from strategies.ensemble import EnsembleStrategy
from strategies.ifvg_strategy import IFVGStrategy
from ifvg import run_ifvg_cycle
from trading_engine.risk_calculator import RiskCalculator
from trading_engine.paper_trader import PaperTrader
from trading_engine.binance_trader import BinanceTrader
from ml.scheduler import build_scheduler
from web.app import app as web_app, ws_manager, _build_snapshot
from web.state import BotState
from learning.post_mortem import PostMortem, TradeRecord
from learning.bandit_ensemble import BanditEnsemble
from learning.drift_detector import DriftDetector
from learning.ppo_sizer import PPOSizer

SUMMARY_EVERY_N = 10
DRAWDOWN_WARN_THRESHOLD = 0.10


def _extract_indicators(df) -> dict:
    row = df.iloc[-1]

    def g(col, decimals=4):
        try:
            v = float(row[col])
            return round(v, decimals) if not __import__("math").isnan(v) else None
        except Exception:
            return None

    return {
        "rsi":         g("rsi", 2),
        "macd":        g("macd", 6),
        "macd_signal": g("macd_signal", 6),
        "macd_hist":   g("macd_hist", 6),
        "bb_pct":      g("bb_pct", 4),
        "bb_upper":    g("bb_upper", 4),
        "bb_lower":    g("bb_lower", 4),
        "adx":         g("adx", 2),
        "atr":         g("atr", 6),
        "sma_fast":    g("sma_fast", 4),
        "sma_slow":    g("sma_slow", 4),
        "ema_12":      g("ema_12", 4),
        "ema_26":      g("ema_26", 4),
        "vol_ratio":   g("vol_ratio", 3),
    }


async def main():
    settings = Settings()
    params = load_trading_params()
    symbols: list[str] = params["trading"]["symbols"]
    timeframe: str = params["trading"]["timeframe"]
    loop_interval: int = params["trading"]["loop_interval_seconds"]

    fetcher = BlofinDataFetcher(settings)
    processor = DataProcessor()
    risk = RiskCalculator()

    # ── Trader selection ──────────────────────────────────────────────────────
    if settings.paper_trading:
        trader = PaperTrader(settings, risk)
        mode = "PAPER"
    else:
        try:
            trader = BinanceTrader(settings, risk)
            mode = "TESTNET" if settings.binance_testnet else "LIVE"
        except Exception as e:
            logger.error(f"BinanceTrader init failed: {e} — falling back to PAPER")
            trader = PaperTrader(settings, risk)
            mode = "PAPER (fallback)"

    try:
        storage = Storage(settings)
    except Exception as e:
        logger.warning(
            f"DB unavailable — running without storage. "
            f"{type(e).__name__}: {str(e).splitlines()[0]}"
        )
        storage = None

    telegram = TelegramAlerts(settings)
    await telegram.start()

    # ── Shared state ──────────────────────────────────────────────────────────
    bot_state = BotState(paper_trader=trader, mode=mode)
    bot_state.symbols = list(symbols)
    web_app.state.bot_state = bot_state
    web_app.state.storage = storage
    # Learning components exposed to web endpoints (set after creation below)
    web_app.state.post_mortem = None
    web_app.state.bandit = None
    web_app.state.drift_detector = None
    web_app.state.ppo_sizer = None

    # ── Logging ───────────────────────────────────────────────────────────────
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}",
    )
    logger.add("logs/bot.log", rotation="1 day", retention="7 days", level="DEBUG")

    def _ui_sink(message):
        record = message.record
        bot_state.push_log(record["level"].name, record["message"])

    logger.add(_ui_sink, level="INFO", format="{message}")

    # ── Web server ────────────────────────────────────────────────────────────
    web_config = uvicorn.Config(
        web_app,
        host=settings.web_host,
        port=settings.web_port,
        log_level="warning",
        access_log=False,
    )
    web_server = uvicorn.Server(web_config)
    asyncio.create_task(web_server.serve())
    logger.info(f"FastAPI backend: http://localhost:{settings.web_port}")
    logger.info("Dashboard: http://localhost:3000")

    # ── Telegram command bot ──────────────────────────────────────────────────
    cmd_bot = None
    if settings.telegram_bot_token and settings.telegram_chat_id:
        cmd_bot = TelegramCommandBot(
            token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
            bot_state=bot_state,
        )
        cmd_bot.start()

    # ── ML scheduler ─────────────────────────────────────────────────────────
    scheduler = None
    if settings.model_retraining_enabled:
        try:
            scheduler = build_scheduler(settings, storage, telegram, bot_state=bot_state)
            scheduler.start()
        except Exception as e:
            logger.warning(f"Scheduler failed to start: {e}")

    # ── Ensemble strategies ───────────────────────────────────────────────────
    ensemble = EnsembleStrategy()
    ensemble.register(MomentumStrategy())
    ensemble.register(MeanReversionStrategy())
    ensemble.register(TrendFollowingStrategy())
    ensemble.register(MLXGBoostStrategy())
    ensemble.register(SentimentStrategy(settings))
    ensemble.register(IFVGStrategy())

    # ── Adaptive learning components ──────────────────────────────────────────
    _strategy_names = ["momentum", "mean_reversion", "trend_following", "ml_xgboost", "sentiment", "ifvg"]
    post_mortem  = PostMortem()
    bandit       = BanditEnsemble(_strategy_names)
    drift_detect = DriftDetector(
        on_drift=lambda: asyncio.create_task(
            telegram.send(
                "⚠️ <b>ML Drift Detected</b> — market regime changed. "
                "XGBoost model may be stale. Triggering retrain..."
            )
        )
    )
    ppo_sizer = PPOSizer()
    logger.info(
        f"Learning layer ready — "
        f"PostMortem ✓ | BanditEnsemble ✓ | DriftDetector ✓ | "
        f"PPOSizer {'✓' if ppo_sizer.is_trained() else '(untrained — using ×1.0)'}"
    )
    web_app.state.post_mortem  = post_mortem
    web_app.state.bandit       = bandit
    web_app.state.drift_detector = drift_detect
    web_app.state.ppo_sizer    = ppo_sizer
    # Also attach to bot_state so Telegram commands can reach them
    bot_state._post_mortem = post_mortem
    bot_state._bandit      = bandit

    # Redis client for IFVG state/blackout/daily-loss tracking
    # REDIS_URL env var takes priority (redis://redis:6379/0 in Docker, localhost locally)
    import os as _os
    import redis as _redis
    _redis_url = _os.environ.get("REDIS_URL") or settings.redis_url
    _redis_client = None
    try:
        _redis_client = _redis.Redis.from_url(_redis_url, decode_responses=True, socket_connect_timeout=2)
        _redis_client.ping()
        logger.info(f"Redis connected ({_redis_url}) — IFVG state persistence enabled")
    except Exception as _e:
        # Try to auto-start a local Redis container (local dev only, not in Docker)
        if "localhost" in _redis_url or "127.0.0.1" in _redis_url:
            try:
                import subprocess as _sp
                _sp.run(
                    ["docker", "run", "-d", "--name", "trading-bot-redis-local",
                     "-p", "6379:6379", "--restart", "unless-stopped", "redis:7-alpine"],
                    capture_output=True, timeout=15,
                )
                import time as _time; _time.sleep(2)
                _redis_client = _redis.Redis.from_url(_redis_url, decode_responses=True, socket_connect_timeout=2)
                _redis_client.ping()
                logger.info("Redis auto-started via Docker — IFVG state persistence enabled")
            except Exception as _e2:
                logger.warning(f"Redis unavailable (IFVG daily-loss guard runs in-memory only): {_e2}")
                _redis_client = None
        else:
            logger.warning(f"Redis unavailable — IFVG daily-loss guard disabled: {_e}")
            _redis_client = None

    balance_display = (
        f"{trader.balance:.0f} USDT"
        if not settings.paper_trading
        else f"{settings.paper_initial_balance:.0f} USDT (paper)"
    )
    logger.info(f"Bot starting — mode={mode} | symbols={symbols} | tf={timeframe}")
    await telegram.send(
        f"<b>Bot started</b> — {mode} mode\n"
        f"Symbols: {', '.join(s.replace('/USDT:USDT','') for s in symbols)}\n"
        f"Balance: {balance_display}\n"
        f"Dashboard: http://localhost:3000\n"
        f"Send /help to control via Telegram"
    )

    loop_count = 0
    _drawdown_warned = False
    _cb_alerted = False

    try:
        while True:
            loop_count += 1
            bot_state.loop_count = loop_count

            if not bot_state.running:
                logger.info("Bot stopped — idling (resume via dashboard or /start)")
                if ws_manager.has_clients:
                    try:
                        await ws_manager.broadcast(_build_snapshot(bot_state))
                    except Exception:
                        pass
                await asyncio.sleep(loop_interval)
                continue

            logger.info(f"━━ Loop {loop_count} ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

            active_symbols = list(bot_state.symbols) if bot_state.symbols else symbols
            logger.info(f"Fetching OHLCV for {', '.join(s.replace('/USDT:USDT','') for s in active_symbols)}")

            ohlcv_map = await fetcher.fetch_all_ohlcv(active_symbols, timeframe, limit=250)

            prices: dict[str, float] = {}
            for sym, df in ohlcv_map.items():
                prices[sym] = df["close"].iloc[-1]
            bot_state.current_prices = prices

            price_str = " | ".join(f"{s.replace('/USDT:USDT','')}=${p:.2f}" for s, p in prices.items())
            logger.info(f"Prices — {price_str}")

            # Check stops / targets
            closed = await trader.check_stops_and_targets(prices, storage=storage)
            for trade in closed:
                await telegram.send_trade_close(trade)
                bot_state.log_activity(
                    "close",
                    f"{trade['side']} {trade['symbol'].replace('/USDT:USDT','')} closed — "
                    f"PnL {trade['pnl']:+.2f} ({trade['reason']})",
                    trade["symbol"],
                )
                # Post-mortem attribution + bandit update
                sym_ind = bot_state.last_indicators.get(trade["symbol"], {})
                sig_cache = bot_state.last_signals.get(trade["symbol"], {})
                pm_record = TradeRecord(
                    symbol=trade["symbol"],
                    side=trade["side"],
                    entry_price=trade["entry_price"],
                    exit_price=trade["exit_price"],
                    pnl=trade["pnl"],
                    pnl_pct=trade["pnl_pct"],
                    reason=trade["reason"],
                    strategy=sig_cache.get("strategy", "ensemble"),
                    confidence=sig_cache.get("confidence", 0.0),
                    consensus_score=sig_cache.get("consensus_score", 0.0),
                    adx=sym_ind.get("adx") or 0.0,
                    atr=sym_ind.get("atr") or 0.0,
                    stop_distance=abs(trade["entry_price"] - trade.get("stop_loss", trade["entry_price"])),
                    vol_ratio=sym_ind.get("vol_ratio") or 1.0,
                    entry_hour_utc=trade.get("opened_at_hour", 0),
                    component_signals=sig_cache.get("component_signals", {}),
                )
                post_mortem.analyse(pm_record, storage)
                bandit.update(
                    component_signals=sig_cache.get("component_signals", {}),
                    trade_side=trade["side"],
                    pnl=trade["pnl"],
                    adx=sym_ind.get("adx") or 0.0,
                )

            if any(t["reason"] == "drawdown_halt" for t in closed):
                await telegram.send_drawdown_halt(trader.drawdown_from_peak)
                _drawdown_warned = True

            dd = trader.drawdown_from_peak
            if dd > DRAWDOWN_WARN_THRESHOLD and not _drawdown_warned:
                await telegram.send_drawdown_warning(dd)
                _drawdown_warned = True
            elif dd < 0.08:
                _drawdown_warned = False

            cb_ok, cb_reason = risk.circuit_breaker(trader.daily_pnl_pct, trader.intraday_pnl_pct)
            bot_state.circuit_breaker_active = not cb_ok
            if not cb_ok and not _cb_alerted:
                logger.warning(f"Circuit breaker active: {cb_reason}")
                await telegram.send_circuit_breaker(cb_reason)
                _cb_alerted = True
            elif cb_ok:
                _cb_alerted = False

            # ── IFVG cycles (per symbol, before ensemble) ─────────────────────
            if _redis_client is not None and bot_state.strategy_enabled.get("ifvg", True):
                ifvg_tasks = [
                    run_ifvg_cycle(
                        symbol=sym,
                        fetcher=fetcher,
                        redis_client=_redis_client,
                        storage=storage,
                        account_balance=float(trader.balance),
                    )
                    for sym in active_symbols
                ]
                await asyncio.gather(*ifvg_tasks, return_exceptions=True)

            # Generate signals
            for sym, df in ohlcv_map.items():
                short = sym.replace("/USDT:USDT", "")
                logger.info(f"▶ Analysing {short} ({len(df)} candles) ...")

                df = processor.add_indicators(df)
                if df.empty:
                    logger.warning(f"  {short}: empty DataFrame after indicators — skipping")
                    continue

                bot_state.last_indicators[sym] = _extract_indicators(df)
                ind = bot_state.last_indicators[sym]
                logger.info(
                    f"  {short} indicators — RSI={ind['rsi']} | MACD_hist={ind['macd_hist']} | "
                    f"BB%={ind['bb_pct']} | ADX={ind['adx']} | VolRatio={ind['vol_ratio']}"
                )

                # Update rolling ATR for volatility-scaled stops
                current_atr = float(df["atr"].iloc[-1])
                risk.update_atr(sym, current_atr)

                # Apply bandit-sampled weights to ensemble for this symbol
                adx_val = float(ind.get("adx") or 0.0)
                bandit_weights = bandit.sample_weights(adx=adx_val)
                ensemble.set_weights(bandit_weights)

                signal = ensemble.generate_signal(df, sym, enabled_strategies=bot_state.strategy_enabled)
                signal["symbol"] = sym
                signal["timeframe"] = timeframe
                signal["price"] = prices[sym]
                bot_state.last_signals[sym] = signal

                # Feed ML prediction to drift detector
                ml_sig = signal.get("component_signals", {}).get("ml_xgboost", "HOLD")
                if signal["action"] != "HOLD":
                    drift_detect.add_element(correct=(ml_sig == signal["action"]))

                current_price = prices[sym]
                atr = current_atr
                action = signal["action"]
                conf = signal["confidence"]
                consensus = signal["consensus_score"]

                logger.info(f"  {short} signal → {action} | conf={conf:.3f} | consensus={consensus:+.4f}")

                cs = signal.get("component_signals", {})
                cc = signal.get("component_confidences", {})
                for strat, vote in cs.items():
                    logger.info(f"    [{strat}] {vote} ({cc.get(strat, 0):.2f})")

                if action in ("BUY", "SELL"):
                    bot_state.log_activity(
                        "signal",
                        f"{action} signal on {short} — conf {conf:.1%} | consensus {consensus:+.3f}",
                        sym,
                    )
                    await telegram.send_signal(sym, signal, current_price)
                    if storage:
                        try:
                            storage.log_signal(signal)
                        except Exception as e:
                            logger.debug(f"Signal log failed: {e}")

                    if bot_state.paused:
                        logger.info(f"  {short}: {action} skipped — PAUSED")
                        bot_state.log_activity("skip", f"{action} skipped — bot paused", sym)
                    elif not cb_ok:
                        logger.warning(f"  {short}: {action} skipped — circuit breaker ({cb_reason})")
                        bot_state.log_activity("skip", f"{action} skipped — CB: {cb_reason}", sym)
                    else:
                        # PPO sizer: compute size multiplier from current market state
                        ppo_state = {
                            "confidence":       conf,
                            "consensus_score":  consensus,
                            "rsi":              ind.get("rsi") or 50.0,
                            "adx":              adx_val,
                            "atr_pct":          atr / current_price if current_price else 0.01,
                            "vol_ratio":        ind.get("vol_ratio") or 1.0,
                            "daily_pnl_pct":    trader.daily_pnl_pct,
                            "drawdown_from_peak": trader.drawdown_from_peak,
                            "open_pos_ratio":   len(trader.positions) / max(risk.max_open, 1),
                            "intraday_pnl_pct": trader.intraday_pnl_pct,
                        }
                        size_mult = ppo_sizer.get_size_multiplier(ppo_state)
                        signal["ppo_size_mult"] = size_mult
                        logger.info(f"  {short}: PPO size multiplier = {size_mult:.2f}×")

                        pos = await trader.open_position(sym, signal, current_price, atr, storage=storage)
                        if pos:
                            logger.info(
                                f"  {short}: position OPENED @ {current_price:.4f} | "
                                f"qty={pos.quantity:.4f} | stop={pos.stop_loss:.4f} | "
                                f"ppo_mult={size_mult:.2f}×"
                            )
                            await telegram.send_trade_open(pos)
                            bot_state.log_activity(
                                "open",
                                f"{pos.side} {short} opened @ {current_price:.4f} | stop={pos.stop_loss:.4f}",
                                sym,
                            )
                        else:
                            open_count = len(trader.positions)
                            max_pos = risk.max_open
                            if sym in trader.positions:
                                skip_reason = "already have a position"
                            elif open_count >= max_pos:
                                skip_reason = f"max positions reached ({open_count}/{max_pos})"
                            elif trader.balance < current_price * 0.001:
                                skip_reason = "insufficient balance"
                            else:
                                skip_reason = "risk sizing returned 0 qty"
                            logger.info(f"  {short}: {action} NOT opened — {skip_reason}")
                            bot_state.log_activity("skip", f"{action} not opened — {skip_reason}", sym)
                else:
                    logger.info(f"  {short}: HOLD — waiting for stronger consensus")

            # Broadcast WebSocket snapshot
            if ws_manager.has_clients:
                try:
                    await ws_manager.broadcast(_build_snapshot(bot_state))
                except Exception as e:
                    logger.debug(f"WS broadcast failed: {e}")

            # Periodic summary
            if loop_count % SUMMARY_EVERY_N == 0:
                summary = trader.summary()
                logger.info(
                    f"Portfolio | balance={summary['balance']:.2f} | "
                    f"pnl={summary['total_pnl']:+.2f} | "
                    f"win={summary['win_rate']:.1%} | trades={summary['total_trades']}"
                )
                await telegram.send_portfolio_summary(summary)
                if storage:
                    try:
                        storage.snapshot_portfolio(
                            summary["balance"], summary["equity"],
                            summary["open_positions"], summary["daily_pnl_pct"], summary["total_pnl"]
                        )
                    except Exception as e:
                        logger.debug(f"Snapshot failed: {e}")

            logger.info(f"Loop {loop_count} done — sleeping {loop_interval}s")
            await asyncio.sleep(loop_interval)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        web_server.should_exit = True
        if cmd_bot:
            cmd_bot.stop()
        if scheduler:
            scheduler.shutdown(wait=False)
        await fetcher.close()
        summary = trader.summary()
        await telegram.send_portfolio_summary(summary)
        await telegram.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
