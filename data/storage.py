from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from loguru import logger
from datetime import datetime, timezone
from config.settings import Settings


class Storage:
    def __init__(self, settings: Settings):
        self.engine = create_engine(settings.database_url, pool_pre_ping=True)
        self.Session = sessionmaker(bind=self.engine)
        # Verify the connection is actually reachable at startup.
        # Raises OperationalError if the DB is down — main.py catches this
        # and sets storage = None, avoiding repeated per-loop warnings.
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    def log_trade(self, trade: dict):
        try:
            sql = text("""
                INSERT INTO trades
                    (symbol, side, entry_price, quantity, strategy, signal_confidence, paper, opened_at)
                VALUES
                    (:symbol, :side, :entry_price, :quantity, :strategy, :confidence, :paper, :opened_at)
                RETURNING id
            """)
            with self.Session() as s:
                result = s.execute(sql, {
                    "symbol": trade["symbol"],
                    "side": trade["side"],
                    "entry_price": trade["entry_price"],
                    "quantity": trade["quantity"],
                    "strategy": trade.get("strategy", "ensemble"),
                    "confidence": trade.get("confidence", 0),
                    "paper": trade.get("paper", True),
                    "opened_at": datetime.now(timezone.utc),
                })
                s.commit()
                return result.scalar()
        except Exception as e:
            logger.warning(f"log_trade failed (DB unavailable): {e}")
            return None

    def close_trade(self, trade_id: int, exit_price: float, pnl: float, pnl_pct: float):
        try:
            sql = text("""
                UPDATE trades
                SET exit_price = :exit_price, pnl = :pnl, pnl_pct = :pnl_pct, closed_at = :closed_at
                WHERE id = :id
            """)
            with self.Session() as s:
                s.execute(sql, {
                    "exit_price": exit_price,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "closed_at": datetime.now(timezone.utc),
                    "id": trade_id,
                })
                s.commit()
        except Exception as e:
            logger.warning(f"close_trade failed (DB unavailable): {e}")

    def log_signal(self, signal: dict):
        try:
            sql = text("""
                INSERT INTO signals (symbol, action, confidence, consensus, strategy, timeframe)
                VALUES (:symbol, :action, :confidence, :consensus, :strategy, :timeframe)
            """)
            with self.Session() as s:
                s.execute(sql, {
                    "symbol": signal["symbol"],
                    "action": signal["action"],
                    "confidence": signal["confidence"],
                    "consensus": signal.get("consensus_score", 0),
                    "strategy": signal.get("strategy", "ensemble"),
                    "timeframe": signal.get("timeframe", "15m"),
                })
                s.commit()
        except Exception as e:
            logger.warning(f"log_signal failed (DB unavailable): {e}")

    def log_model_version(self, version: str, cv_accuracy: float, sharpe: float,
                          win_rate: float, max_drawdown: float, n_samples: int,
                          model_path: str, scaler_path: str,
                          is_champion: bool = False, notes: str = "") -> int:
        try:
            sql = text("""
                INSERT INTO model_versions
                    (version, cv_accuracy, sharpe, win_rate, max_drawdown, n_samples,
                     model_path, scaler_path, is_champion, notes)
                VALUES
                    (:version, :cv_accuracy, :sharpe, :win_rate, :max_drawdown, :n_samples,
                     :model_path, :scaler_path, :is_champion, :notes)
                RETURNING id
            """)
            with self.Session() as s:
                result = s.execute(sql, {
                    "version": version, "cv_accuracy": cv_accuracy, "sharpe": sharpe,
                    "win_rate": win_rate, "max_drawdown": max_drawdown, "n_samples": n_samples,
                    "model_path": model_path, "scaler_path": scaler_path,
                    "is_champion": is_champion, "notes": notes,
                })
                s.commit()
                return result.scalar()
        except Exception as e:
            logger.warning(f"log_model_version failed (DB unavailable): {e}")
            return None

    def get_champion_metrics(self) -> dict | None:
        try:
            sql = text("""
                SELECT sharpe, win_rate, max_drawdown, cv_accuracy, version, model_path, scaler_path
                FROM model_versions
                WHERE is_champion = TRUE
                ORDER BY trained_at DESC
                LIMIT 1
            """)
            with self.Session() as s:
                row = s.execute(sql).mappings().first()
                return dict(row) if row else None
        except Exception as e:
            logger.warning(f"get_champion_metrics failed (DB unavailable): {e}")
            return None

    def set_champion(self, model_id: int):
        try:
            with self.Session() as s:
                s.execute(text("UPDATE model_versions SET is_champion = FALSE WHERE is_champion = TRUE"))
                s.execute(text("UPDATE model_versions SET is_champion = TRUE WHERE id = :id"), {"id": model_id})
                s.commit()
        except Exception as e:
            logger.warning(f"set_champion failed (DB unavailable): {e}")

    def snapshot_portfolio(self, balance: float, equity: float, open_pos: int,
                           daily_pnl: float, total_pnl: float):
        try:
            sql = text("""
                INSERT INTO portfolio_snapshots (balance, equity, open_positions, daily_pnl, total_pnl)
                VALUES (:balance, :equity, :open_positions, :daily_pnl, :total_pnl)
            """)
            with self.Session() as s:
                s.execute(sql, {
                    "balance": balance,
                    "equity": equity,
                    "open_positions": open_pos,
                    "daily_pnl": daily_pnl,
                    "total_pnl": total_pnl,
                })
                s.commit()
        except Exception as e:
            logger.warning(f"snapshot_portfolio failed (DB unavailable): {e}")

    # ── Query methods (for frontend API) ──────────────────────────────────────

    def get_trades(self, limit: int = 100, symbol: str | None = None) -> list[dict]:
        try:
            where = "WHERE closed_at IS NOT NULL"
            params: dict = {"limit": limit}
            if symbol:
                where += " AND symbol = :symbol"
                params["symbol"] = symbol
            sql = text(f"""
                SELECT id, symbol, side, entry_price, exit_price, quantity,
                       pnl, pnl_pct, strategy, signal_confidence, paper,
                       opened_at, closed_at
                FROM trades {where}
                ORDER BY closed_at DESC
                LIMIT :limit
            """)
            with self.Session() as s:
                rows = s.execute(sql, params).mappings().all()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"get_trades failed: {e}")
            return []

    def get_portfolio_snapshots(self, hours: int = 168) -> list[dict]:
        try:
            sql = text("""
                SELECT balance, equity, open_positions, daily_pnl, total_pnl, snapped_at
                FROM portfolio_snapshots
                WHERE snapped_at > NOW() - INTERVAL '1 hour' * :hours
                ORDER BY snapped_at ASC
            """)
            with self.Session() as s:
                rows = s.execute(sql, {"hours": hours}).mappings().all()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"get_portfolio_snapshots failed: {e}")
            return []

    def get_model_versions(self, limit: int = 20) -> list[dict]:
        try:
            sql = text("""
                SELECT id, version, trained_at, cv_accuracy, sharpe, win_rate,
                       max_drawdown, n_samples, is_champion, notes
                FROM model_versions
                ORDER BY trained_at DESC
                LIMIT :limit
            """)
            with self.Session() as s:
                rows = s.execute(sql, {"limit": limit}).mappings().all()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"get_model_versions failed: {e}")
            return []

    def get_strategy_pnl(self) -> list[dict]:
        try:
            sql = text("""
                SELECT
                    strategy,
                    SUM(pnl) AS total_pnl,
                    COUNT(*) AS trades,
                    AVG(pnl_pct) AS avg_pnl_pct,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::float / COUNT(*) AS win_rate
                FROM trades
                WHERE closed_at IS NOT NULL
                GROUP BY strategy
                ORDER BY total_pnl DESC
            """)
            with self.Session() as s:
                rows = s.execute(sql).mappings().all()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"get_strategy_pnl failed: {e}")
            return []

    def get_recent_signals(self, limit: int = 100) -> list[dict]:
        try:
            sql = text("""
                SELECT id, symbol, action, confidence, consensus, strategy, timeframe, created_at
                FROM signals
                ORDER BY created_at DESC
                LIMIT :limit
            """)
            with self.Session() as s:
                rows = s.execute(sql, {"limit": limit}).mappings().all()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"get_recent_signals failed: {e}")
            return []
