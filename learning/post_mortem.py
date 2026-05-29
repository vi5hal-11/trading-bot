"""
Post-trade loss attribution — automatically tags every closed trade with the
primary reason it won or lost.

Loss buckets
────────────
  wrong_regime     — trend strategy fired in a ranging market (ADX < 20) or
                     mean-reversion fired in a strongly trending market (ADX > 30)
  stop_too_tight   — stop was < 0.5× ATR at entry; price oscillation alone
                     could have clipped it
  strategy_conflict — majority of sub-strategies disagreed with the entry
                     direction (< 50% agreement)
  low_liquidity    — trade opened outside the two main crypto sessions
                     (08:00–12:00 UTC  and  13:00–21:00 UTC)
  news_shock       — sentiment strategy was the primary BUY/SELL voter on a
                     losing trade; likely a headline-driven false positive
  time_stop        — position hit the time-based exit without hitting SL or TP
  normal_loss      — none of the above patterns detected
  win              — trade was profitable (no loss bucket assigned)

All tags are stored in the `trade_postmortem` DB table and in an in-memory
list (`PostMortem.history`) for the `/api/postmortem` endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

from loguru import logger


# ── Data carrier ─────────────────────────────────────────────────────────────

@dataclass
class TradeRecord:
    """Everything known about a trade at close time."""
    symbol: str
    side: str                   # BUY | SELL
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    reason: str                 # signal | sl_tp_exchange | time_stop | drawdown_halt | …
    strategy: str               # winning sub-strategy name
    confidence: float
    consensus_score: float

    # Market state at entry
    adx: float = 0.0
    atr: float = 0.0
    stop_distance: float = 0.0  # abs(entry - stop_loss)
    vol_ratio: float = 1.0      # current volume / 20-bar avg
    entry_hour_utc: int = 0

    # Sub-strategy votes at entry (name → "BUY" | "SELL" | "HOLD")
    component_signals: dict = field(default_factory=dict)

    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    db_id: Optional[int] = None


@dataclass
class PostMortemResult:
    symbol: str
    side: str
    pnl: float
    pnl_pct: float
    loss_reason: str            # one of the buckets above
    details: str                # human-readable explanation
    opened_at: Optional[datetime]
    closed_at: Optional[datetime]
    db_id: Optional[int]


# ── Tagger ────────────────────────────────────────────────────────────────────

_LIQUID_WINDOWS = [(8, 12), (13, 21)]   # UTC hour ranges
_ADX_RANGING    = 20.0
_ADX_TRENDING   = 30.0
_STOP_ATR_MIN   = 0.5           # stop < 0.5× ATR → "too tight"
_CONFLICT_THRESHOLD = 0.5       # fraction of strategies that must agree


def _in_liquid_window(hour_utc: int) -> bool:
    return any(lo <= hour_utc < hi for lo, hi in _LIQUID_WINDOWS)


def _agreement_ratio(side: str, component_signals: dict) -> float:
    if not component_signals:
        return 1.0
    votes = list(component_signals.values())
    agreeing = sum(1 for v in votes if v == side)
    return agreeing / len(votes)


def tag_trade(trade: TradeRecord) -> PostMortemResult:
    """Assign a loss bucket and produce a human-readable explanation."""
    is_win = trade.pnl >= 0

    if is_win:
        return PostMortemResult(
            symbol=trade.symbol,
            side=trade.side,
            pnl=trade.pnl,
            pnl_pct=trade.pnl_pct,
            loss_reason="win",
            details=f"Profitable trade (+{trade.pnl:.2f} USDT, +{trade.pnl_pct:.2%}). "
                    f"Exit reason: {trade.reason}.",
            opened_at=trade.opened_at,
            closed_at=trade.closed_at,
            db_id=trade.db_id,
        )

    # ── Loss buckets (checked in priority order) ──────────────────────────────

    reason = "normal_loss"
    details_parts = []

    # 1. Strategy conflict — majority disagreed
    agreement = _agreement_ratio(trade.side, trade.component_signals)
    if agreement < _CONFLICT_THRESHOLD and trade.component_signals:
        reason = "strategy_conflict"
        disagree_pct = 1 - agreement
        details_parts.append(
            f"{disagree_pct:.0%} of sub-strategies voted against {trade.side} "
            f"but ensemble threshold was crossed."
        )

    # 2. Stop too tight relative to ATR
    elif trade.atr > 0 and trade.stop_distance < _STOP_ATR_MIN * trade.atr:
        reason = "stop_too_tight"
        ratio = trade.stop_distance / trade.atr if trade.atr else 0
        details_parts.append(
            f"Stop distance ({trade.stop_distance:.4f}) was only {ratio:.2f}× ATR "
            f"({trade.atr:.4f}). Minimum recommended: {_STOP_ATR_MIN}× ATR. "
            f"Normal price oscillation likely clipped the stop."
        )

    # 3. Wrong regime — trend strategy in ranging market
    elif trade.strategy in ("trend_following", "momentum") and trade.adx < _ADX_RANGING:
        reason = "wrong_regime"
        details_parts.append(
            f"Trend/momentum strategy fired with ADX={trade.adx:.1f} (< {_ADX_RANGING}). "
            f"Market was ranging — these strategies need a trending market (ADX > {_ADX_TRENDING})."
        )

    # 4. Wrong regime — mean reversion in strongly trending market
    elif trade.strategy == "mean_reversion" and trade.adx > _ADX_TRENDING:
        reason = "wrong_regime"
        details_parts.append(
            f"Mean reversion strategy fired with ADX={trade.adx:.1f} (> {_ADX_TRENDING}). "
            f"Market was strongly trending — mean reversion works in ranging markets."
        )

    # 5. Low liquidity window
    elif not _in_liquid_window(trade.entry_hour_utc):
        reason = "low_liquidity"
        details_parts.append(
            f"Trade opened at {trade.entry_hour_utc:02d}:xx UTC — outside main liquidity "
            f"windows (08-12 UTC and 13-21 UTC). Spread and slippage tend to be higher."
        )

    # 6. News shock — sentiment was the primary voter
    elif trade.strategy == "sentiment":
        reason = "news_shock"
        details_parts.append(
            f"Sentiment strategy was the primary voter. Headline-driven signals "
            f"often reverse quickly; the move may have been a fake-out."
        )

    # 7. Time stop
    elif trade.reason == "time_stop":
        reason = "time_stop"
        details_parts.append(
            f"Trade hit the time-based exit without reaching SL or TP. "
            f"Price drifted sideways — consider a tighter time stop or "
            f"re-evaluating the entry setup."
        )

    # Fallback
    else:
        details_parts.append(
            f"No dominant failure pattern detected. PnL={trade.pnl:+.2f} USDT "
            f"({trade.pnl_pct:+.2%}). Review chart manually."
        )

    # Always append context
    details_parts.append(
        f"[ADX={trade.adx:.1f} | ATR={trade.atr:.4f} | "
        f"confidence={trade.confidence:.2f} | consensus={trade.consensus_score:+.3f} | "
        f"vol_ratio={trade.vol_ratio:.2f}]"
    )

    return PostMortemResult(
        symbol=trade.symbol,
        side=trade.side,
        pnl=trade.pnl,
        pnl_pct=trade.pnl_pct,
        loss_reason=reason,
        details=" ".join(details_parts),
        opened_at=trade.opened_at,
        closed_at=trade.closed_at,
        db_id=trade.db_id,
    )


# ── PostMortem manager ────────────────────────────────────────────────────────

class PostMortem:
    """Runs trade attribution after every close and persists results."""

    MAX_HISTORY = 200

    def __init__(self):
        self.history: list[dict] = []   # most-recent first

    def analyse(self, trade: TradeRecord, storage=None) -> PostMortemResult:
        result = tag_trade(trade)
        entry = {
            **asdict(result),
            "strategy": trade.strategy,
            "confidence": trade.confidence,
            "adx": trade.adx,
            "atr": trade.atr,
            "vol_ratio": trade.vol_ratio,
            "component_signals": trade.component_signals,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self.history.insert(0, entry)
        if len(self.history) > self.MAX_HISTORY:
            self.history.pop()

        if storage:
            self._persist(entry, storage)

        emoji = "✅" if result.loss_reason == "win" else "❌"
        logger.info(
            f"[PostMortem] {emoji} {result.symbol} {result.side} "
            f"PnL={result.pnl:+.2f} | reason={result.loss_reason} | {result.details[:80]}"
        )
        return result

    def summary(self) -> dict:
        """Aggregate loss bucket counts for the dashboard."""
        from collections import Counter
        counts = Counter(e["loss_reason"] for e in self.history)
        total = len(self.history)
        wins  = counts.get("win", 0)
        return {
            "total": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate": wins / total if total else 0.0,
            "buckets": dict(counts),
            "top_loss_reason": counts.most_common(2)[1][0] if len(counts) >= 2 else "n/a",
        }

    @staticmethod
    def _persist(entry: dict, storage) -> None:
        try:
            from sqlalchemy import text
            sql = text("""
                INSERT INTO trade_postmortem
                    (trade_id, symbol, side, pnl, pnl_pct, loss_reason, details,
                     adx, atr, vol_ratio, strategy, confidence, consensus_score,
                     component_signals, entry_hour_utc, closed_at)
                VALUES
                    (:trade_id, :symbol, :side, :pnl, :pnl_pct, :loss_reason, :details,
                     :adx, :atr, :vol_ratio, :strategy, :confidence, :consensus_score,
                     :component_signals, :entry_hour_utc, :closed_at)
            """)
            import json
            with storage.Session() as sess:
                sess.execute(sql, {
                    "trade_id":        entry.get("db_id"),
                    "symbol":          entry["symbol"],
                    "side":            entry["side"],
                    "pnl":             entry["pnl"],
                    "pnl_pct":         entry["pnl_pct"],
                    "loss_reason":     entry["loss_reason"],
                    "details":         entry["details"],
                    "adx":             entry.get("adx", 0),
                    "atr":             entry.get("atr", 0),
                    "vol_ratio":       entry.get("vol_ratio", 1),
                    "strategy":        entry.get("strategy", ""),
                    "confidence":      entry.get("confidence", 0),
                    "consensus_score": entry.get("consensus_score", 0),
                    "component_signals": json.dumps(entry.get("component_signals", {})),
                    "entry_hour_utc":  entry.get("entry_hour_utc", 0),
                    "closed_at":       entry.get("closed_at"),
                })
                sess.commit()
        except Exception as e:
            logger.debug(f"PostMortem persist failed: {e}")
