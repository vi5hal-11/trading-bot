"""
FastAPI web control panel for the trading bot.
Runs in the same asyncio event loop as main.py via uvicorn.Server.
"""
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from web.state import BotState

PARAMS_PATH = Path(__file__).parent.parent / "config" / "trading_params.yaml"

EDITABLE_RISK_KEYS = {
    "max_loss_pct_per_trade", "max_open_positions",
    "daily_loss_circuit_breaker", "trailing_stop_atr_multiplier",
    "max_portfolio_drawdown", "max_total_exposure_pct",
}

# ── WebSocket connection manager ──────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in list(self._connections):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def has_clients(self) -> bool:
        return bool(self._connections)


ws_manager = ConnectionManager()


def _serialize_positions(state: BotState) -> list[dict]:
    if state.paper_trader is None:
        return []
    out = []
    for symbol, pos in state.paper_trader.positions.items():
        price = state.current_prices.get(symbol, pos.entry_price)
        upnl = pos.unrealized_pnl(price)
        upnl_pct = pos.unrealized_pnl_pct(price)
        age_min = int((datetime.now(timezone.utc) - pos.opened_at).total_seconds() / 60)
        out.append({
            "symbol": symbol,
            "side": pos.side,
            "entry_price": round(pos.entry_price, 4),
            "current_price": round(price, 4),
            "quantity": round(pos.quantity, 6),
            "unrealized_pnl": round(upnl, 2),
            "unrealized_pnl_pct": round(upnl_pct, 4),
            "stop_loss": round(pos.stop_loss, 4),
            "take_profit": round(pos.take_profit, 4),
            "strategy": pos.strategy,
            "confidence": round(pos.confidence, 3),
            "age_minutes": age_min,
            "tp1_done": pos.partial_tp1_done,
            "tp2_done": pos.partial_tp2_done,
        })
    return out


def _build_snapshot(state: BotState) -> dict:
    paper = state.paper_trader
    uptime_s = int((datetime.now(timezone.utc) - state.started_at).total_seconds())
    return {
        "type": "snapshot",
        "prices": state.current_prices,
        "signals": state.last_signals,
        "positions": _serialize_positions(state),
        "summary": paper.summary() if paper else {},
        "activity": list(reversed(state.activity_log))[:20],
        "logs": list(state.log_buffer)[-100:],
        "indicators": state.last_indicators,
        "status": {
            "mode": state.mode,
            "paused": state.paused,
            "running": state.running,
            "loop_count": state.loop_count,
            "circuit_breaker_active": state.circuit_breaker_active,
            "uptime_seconds": uptime_s,
            "strategy_enabled": state.strategy_enabled,
            "symbols": state.symbols,
            "risk_overrides": state.risk_overrides,
        },
    }


app = FastAPI(title="Trading Bot", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


def _get_state(request: Request) -> BotState:
    return request.app.state.bot_state


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    state = websocket.app.state.bot_state
    try:
        await websocket.send_json(_build_snapshot(state))
        while True:
            # Keep alive — client sends pings, we reply pong
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


# ── Root — redirect hint for the Next.js frontend ────────────────────────────

@app.get("/")
async def root():
    return JSONResponse({"status": "ok", "ui": "http://localhost:3000"})


# ── API: status ───────────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status(request: Request):
    state = _get_state(request)
    uptime_s = int((datetime.now(timezone.utc) - state.started_at).total_seconds())
    return {
        "mode": state.mode,
        "paused": state.paused,
        "running": state.running,
        "loop_count": state.loop_count,
        "circuit_breaker_active": state.circuit_breaker_active,
        "uptime_seconds": uptime_s,
        "strategy_enabled": state.strategy_enabled,
        "symbols": state.symbols,
        "risk_overrides": state.risk_overrides,
    }


@app.post("/api/bot/pause")
async def pause_bot(request: Request):
    state = _get_state(request)
    state.paused = True
    await ws_manager.broadcast(_build_snapshot(state))
    return {"paused": True}


@app.post("/api/bot/resume")
async def resume_bot(request: Request):
    state = _get_state(request)
    state.paused = False
    await ws_manager.broadcast(_build_snapshot(state))
    return {"paused": False}


@app.post("/api/bot/start")
async def start_bot(request: Request):
    state = _get_state(request)
    state.running = True
    state.paused = False
    state.log_activity("system", "Bot started via web control")
    await ws_manager.broadcast(_build_snapshot(state))
    return {"running": True}


@app.post("/api/bot/stop")
async def stop_bot(request: Request):
    state = _get_state(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    close_all = body.get("close_positions", False)
    state.running = False
    closed = []
    if close_all and state.paper_trader is not None:
        for symbol in list(state.paper_trader.positions.keys()):
            price = state.current_prices.get(symbol)
            if price:
                trade = await state.paper_trader.close_position(symbol, price, "manual_stop")
                if trade:
                    closed.append(trade["symbol"])
    state.log_activity(
        "system",
        f"Bot stopped via web control" + (f" — closed: {', '.join(closed)}" if closed else ""),
    )
    await ws_manager.broadcast(_build_snapshot(state))
    return {"running": False, "positions_closed": closed}


# ── API: strategy toggles ─────────────────────────────────────────────────────

@app.post("/api/strategies/toggle")
async def toggle_strategy(request: Request):
    state = _get_state(request)
    body = await request.json()
    name = body.get("name", "")
    enabled = body.get("enabled", True)
    if name not in state.strategy_enabled:
        raise HTTPException(status_code=404, detail=f"Unknown strategy: {name}")
    state.strategy_enabled[name] = enabled
    state.log_activity(
        "system",
        f"Strategy '{name}' {'enabled' if enabled else 'disabled'} via web control",
    )
    await ws_manager.broadcast(_build_snapshot(state))
    return {"strategy_enabled": state.strategy_enabled}


# ── API: hot-reload risk params ───────────────────────────────────────────────

RISK_HOT_FIELDS = {"atr_multiplier", "max_loss_pct", "tp1_pct", "tp2_pct", "tp1_size", "tp2_size"}


@app.patch("/api/risk")
async def patch_risk(request: Request):
    body = await request.json()
    state = _get_state(request)
    paper = state.paper_trader
    risk = paper.risk if paper else None
    updated = []

    for key, val in body.items():
        if key not in RISK_HOT_FIELDS:
            continue
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue
        state.risk_overrides[key] = val
        if paper and key == "tp1_pct":
            paper.tp1_pct = val
        elif paper and key == "tp2_pct":
            paper.tp2_pct = val
        elif paper and key == "tp1_size":
            paper.tp1_size = val
        elif paper and key == "tp2_size":
            paper.tp2_size = val
        elif risk and key == "atr_multiplier":
            risk.atr_mult = val
        elif risk and key == "max_loss_pct":
            risk.max_loss_pct = val
        updated.append(f"{key}={val}")

    if not updated:
        raise HTTPException(status_code=400, detail="No valid risk fields provided")
    state.log_activity("system", f"Risk params updated: {', '.join(updated)}")
    await ws_manager.broadcast(_build_snapshot(state))
    return {"updated": updated, "risk_overrides": state.risk_overrides}


# ── API: symbol watchlist ─────────────────────────────────────────────────────

@app.get("/api/symbols")
async def get_symbols(request: Request):
    return {"symbols": _get_state(request).symbols}


@app.post("/api/symbols")
async def add_symbol(request: Request):
    state = _get_state(request)
    body = await request.json()
    symbol = body.get("symbol", "").strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol required")
    if symbol in state.symbols:
        raise HTTPException(status_code=409, detail=f"{symbol} already in watchlist")
    state.symbols.append(symbol)
    state.log_activity("system", f"Symbol added: {symbol}")
    await ws_manager.broadcast(_build_snapshot(state))
    return {"symbols": state.symbols}


@app.delete("/api/symbols/{symbol:path}")
async def remove_symbol(symbol: str, request: Request):
    state = _get_state(request)
    if symbol not in state.symbols:
        raise HTTPException(status_code=404, detail=f"{symbol} not in watchlist")
    if len(state.symbols) <= 1:
        raise HTTPException(status_code=400, detail="Cannot remove last symbol")
    state.symbols.remove(symbol)
    paper = state.paper_trader
    if paper and symbol in paper.positions:
        price = state.current_prices.get(symbol, paper.positions[symbol].entry_price)
        await paper.close_position(symbol, price, "symbol_removed")
    state.log_activity("system", f"Symbol removed: {symbol}")
    await ws_manager.broadcast(_build_snapshot(state))
    return {"symbols": state.symbols}


# ── API: per-position stop / TP update ────────────────────────────────────────

@app.patch("/api/positions/{symbol:path}/stop")
async def update_position_stop(symbol: str, request: Request):
    state = _get_state(request)
    if state.paper_trader is None:
        raise HTTPException(status_code=503, detail="Bot not ready")
    body = await request.json()
    new_stop = body.get("stop_loss")
    if new_stop is None:
        raise HTTPException(status_code=400, detail="stop_loss required")
    ok = state.paper_trader.update_stop(symbol, float(new_stop))
    if not ok:
        raise HTTPException(status_code=404, detail=f"No open position for {symbol}")
    await ws_manager.broadcast(_build_snapshot(state))
    return {"symbol": symbol, "stop_loss": float(new_stop)}


@app.patch("/api/positions/{symbol:path}/tp")
async def update_position_tp(symbol: str, request: Request):
    state = _get_state(request)
    if state.paper_trader is None:
        raise HTTPException(status_code=503, detail="Bot not ready")
    body = await request.json()
    new_tp = body.get("take_profit")
    if new_tp is None:
        raise HTTPException(status_code=400, detail="take_profit required")
    ok = state.paper_trader.update_tp(symbol, float(new_tp))
    if not ok:
        raise HTTPException(status_code=404, detail=f"No open position for {symbol}")
    await ws_manager.broadcast(_build_snapshot(state))
    return {"symbol": symbol, "take_profit": float(new_tp)}


# ── API: portfolio ────────────────────────────────────────────────────────────

@app.get("/api/summary")
async def get_summary(request: Request):
    state = _get_state(request)
    if state.paper_trader is None:
        return {}
    return state.paper_trader.summary()


@app.get("/api/positions")
async def get_positions(request: Request):
    state = _get_state(request)
    if state.paper_trader is None:
        return {"positions": []}

    positions = []
    for symbol, pos in state.paper_trader.positions.items():
        price = state.current_prices.get(symbol, pos.entry_price)
        upnl = pos.unrealized_pnl(price)
        upnl_pct = pos.unrealized_pnl_pct(price)
        age_min = int((datetime.now(timezone.utc) - pos.opened_at).total_seconds() / 60)
        positions.append({
            "symbol": symbol,
            "side": pos.side,
            "entry_price": round(pos.entry_price, 4),
            "current_price": round(price, 4),
            "quantity": round(pos.quantity, 6),
            "unrealized_pnl": round(upnl, 2),
            "unrealized_pnl_pct": round(upnl_pct, 4),
            "stop_loss": round(pos.stop_loss, 4),
            "take_profit": round(pos.take_profit, 4),
            "strategy": pos.strategy,
            "confidence": round(pos.confidence, 3),
            "age_minutes": age_min,
            "tp1_done": pos.partial_tp1_done,
            "tp2_done": pos.partial_tp2_done,
        })
    return {"positions": positions}


@app.get("/api/signals")
async def get_signals(request: Request):
    state = _get_state(request)
    return {"signals": state.last_signals}


# ── API: manual close ─────────────────────────────────────────────────────────

@app.post("/api/trade/close/{symbol:path}")
async def close_position(symbol: str, request: Request):
    state = _get_state(request)
    if state.paper_trader is None:
        raise HTTPException(status_code=503, detail="Bot not ready")
    price = state.current_prices.get(symbol)
    if price is None:
        raise HTTPException(status_code=404, detail=f"No price for {symbol}")
    trade = await state.paper_trader.close_position(symbol, price, "manual")
    if trade is None:
        raise HTTPException(status_code=404, detail=f"No open position for {symbol}")
    await ws_manager.broadcast(_build_snapshot(state))
    return {"closed": trade}


# ── API: config ───────────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    with open(PARAMS_PATH) as f:
        params = yaml.safe_load(f)
    return {
        "risk": {k: v for k, v in params["risk"].items() if k in EDITABLE_RISK_KEYS},
        "ensemble": {"threshold": params["ensemble"]["threshold"]},
    }


@app.post("/api/config")
async def patch_config(request: Request):
    body = await request.json()
    with open(PARAMS_PATH) as f:
        params = yaml.safe_load(f)

    changed = []
    if "risk" in body:
        for key, val in body["risk"].items():
            if key in EDITABLE_RISK_KEYS:
                params["risk"][key] = val
                changed.append(f"risk.{key}={val}")

    if "ensemble" in body and "threshold" in body["ensemble"]:
        params["ensemble"]["threshold"] = body["ensemble"]["threshold"]
        changed.append(f"ensemble.threshold={body['ensemble']['threshold']}")

    if not changed:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    with open(PARAMS_PATH, "w") as f:
        yaml.dump(params, f, default_flow_style=False, allow_unicode=True)

    return {"updated": changed, "note": "Changes apply on next bot restart or RiskCalculator reload"}


# ── API: trade history ─────────────────────────────────────────────────────────

@app.get("/api/trades")
async def get_trades(request: Request, limit: int = 100, symbol: str | None = None):
    state = _get_state(request)
    storage = getattr(request.app.state, "storage", None)
    if storage:
        trades = storage.get_trades(limit=limit, symbol=symbol)
        if trades:
            return {"trades": trades}
    # Fall back to in-memory closed trades from current session
    if state.paper_trader is None:
        return {"trades": []}
    closed = list(reversed(state.paper_trader.closed_trades))
    if symbol:
        closed = [t for t in closed if t.get("symbol") == symbol]
    return {"trades": closed[:limit]}


# ── API: equity curve ──────────────────────────────────────────────────────────

@app.get("/api/equity-curve")
async def get_equity_curve(request: Request, hours: int = 168):
    storage = getattr(request.app.state, "storage", None)
    if storage:
        snapshots = storage.get_portfolio_snapshots(hours=hours)
        return {"snapshots": snapshots}
    return {"snapshots": []}


# ── API: model versions ────────────────────────────────────────────────────────

@app.get("/api/models")
async def get_models(request: Request, limit: int = 20):
    storage = getattr(request.app.state, "storage", None)
    if storage:
        models = storage.get_model_versions(limit=limit)
        return {"models": models}
    return {"models": []}


# ── API: activity log ──────────────────────────────────────────────────────────

@app.get("/api/activity")
async def get_activity(request: Request):
    state = _get_state(request)
    return {"log": list(reversed(state.activity_log))}


# ── API: trade explanation ─────────────────────────────────────────────────────

def _rule_based_explain(signal: dict, symbol: str, price: float) -> str:
    component_signals = signal.get("component_signals", {})
    component_confidences = signal.get("component_confidences", {})
    action = signal.get("action", "HOLD")
    consensus = signal.get("consensus_score", 0.0)
    confidence = signal.get("confidence", 0.0)

    votes_for = [s for s, a in component_signals.items() if a == action]
    votes_against = [s for s, a in component_signals.items() if a != action and a != "HOLD"]
    votes_neutral = [s for s, a in component_signals.items() if a == "HOLD"]

    def fmt_strat(name: str) -> str:
        conf = component_confidences.get(name, 0.0)
        return f"{name.replace('_', ' ').title()} ({conf:.2f})"

    parts = []
    if votes_for:
        parts.append(f"{', '.join(fmt_strat(s) for s in votes_for)} voted {action}.")
    if votes_against:
        parts.append(f"{', '.join(fmt_strat(s) for s in votes_against)} dissented.")
    if votes_neutral:
        parts.append(f"{', '.join(s.replace('_',' ').title() for s in votes_neutral)} held neutral.")

    parts.append(
        f"Ensemble consensus {consensus:+.3f} | confidence {confidence:.1%} | price {price:.4f}."
    )
    return " ".join(parts) if parts else f"{action} signal at {price:.4f}."


@app.get("/api/ifvg/status")
async def ifvg_status():
    """Return current IFVG module state: active zones and open trades per symbol."""
    from ifvg import _active_zones, _active_trades, _signal_cache
    return {
        "zones": {
            sym: {
                "direction": z.direction,
                "zone_high": float(z.zone_high),
                "zone_low": float(z.zone_low),
                "ce": float(z.ce),
                "expires_at": z.expires_at.isoformat(),
                "width_pct": round(z.width_pct * 100, 4),
            }
            for sym, z in _active_zones.items()
        },
        "trades": {
            sym: {
                "status": t.status,
                "entry_price": float(t.entry_price),
                "sl_price": float(t.sl_price),
                "tp1_price": float(t.tp1_price),
                "tp2_price": float(t.tp2_price),
                "dol_level": float(t.dol_level),
                "tp1_hit": t.tp1_hit,
                "pnl_r": t.pnl_r,
                "outcome": t.outcome,
            }
            for sym, t in _active_trades.items()
        },
        "signals": _signal_cache,
    }


@app.get("/api/ifvg/signals")
async def ifvg_signals():
    """Return cached IFVG signals for all active symbols."""
    from ifvg import _signal_cache
    return {"signals": _signal_cache}


@app.get("/api/ifvg/trade/{symbol:path}")
async def ifvg_trade(symbol: str):
    """Return the active IFVG trade state for a specific symbol."""
    from ifvg import _active_trades, _active_zones
    trade = _active_trades.get(symbol)
    zone = _active_zones.get(symbol)
    if trade is None and zone is None:
        raise HTTPException(status_code=404, detail="No active IFVG setup for this symbol")
    return {
        "symbol": symbol,
        "zone": {
            "direction": zone.direction,
            "zone_high": float(zone.zone_high),
            "zone_low": float(zone.zone_low),
            "ce": float(zone.ce),
            "expires_at": zone.expires_at.isoformat(),
        } if zone else None,
        "trade": {
            "status": trade.status,
            "entry_price": float(trade.entry_price),
            "sl_price": float(trade.sl_price),
            "tp1_price": float(trade.tp1_price),
            "tp2_price": float(trade.tp2_price),
            "dol_level": float(trade.dol_level),
            "position_size": float(trade.position_size),
            "risk_amount": float(trade.risk_amount),
            "tp1_hit": trade.tp1_hit,
            "entry_mode": trade.entry_mode,
            "candles_since_entry": trade.candles_since_entry,
            "pnl_r": trade.pnl_r,
            "outcome": trade.outcome,
        } if trade else None,
    }


@app.post("/api/ifvg/enable")
async def ifvg_enable(request: Request):
    """Enable the IFVG strategy in the ensemble."""
    state = _get_state(request)
    state.strategy_enabled["ifvg"] = True
    return {"ifvg_enabled": True}


@app.post("/api/ifvg/disable")
async def ifvg_disable(request: Request):
    """Disable the IFVG strategy in the ensemble."""
    state = _get_state(request)
    state.strategy_enabled["ifvg"] = False
    return {"ifvg_enabled": False}


@app.post("/api/explain")
async def explain_trade(request: Request):
    body = await request.json()
    signal = body.get("signal", {})
    symbol = body.get("symbol", "")
    price = body.get("price", 0.0)

    rule_based = _rule_based_explain(signal, symbol, price)

    ollama_available = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get("http://localhost:11434/api/tags")
            ollama_available = r.status_code == 200
    except Exception:
        pass

    return {"rule_based": rule_based, "ollama_available": ollama_available}
