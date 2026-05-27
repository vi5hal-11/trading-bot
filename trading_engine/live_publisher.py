import json
import redis
from loguru import logger
from config.settings import Settings
from trading_engine.risk_calculator import RiskCalculator


class LivePublisher:
    def __init__(self, settings: Settings):
        self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        self._risk = RiskCalculator()

    def publish_order(
        self,
        symbol: str,
        signal: dict,
        current_price: float,
        atr: float,
        portfolio_balance: float,
    ) -> bool:
        side = signal["action"]  # "BUY" or "SELL"

        stop_loss = self._risk.stop_loss_price(current_price, side, atr)
        take_profit = current_price * (1.04 if side == "BUY" else 0.96)
        quantity = self._risk.position_size(
            portfolio_balance, current_price, stop_loss, signal["confidence"]
        )

        if quantity <= 0:
            logger.warning(f"Calculated zero quantity for {symbol}, skipping live order")
            return False

        order = {
            "symbol": symbol,
            "side": side,
            "entry_price": current_price,
            "quantity": quantity,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "confidence": signal["confidence"],
            "strategy": signal.get("strategy", "ensemble"),
        }

        self._redis.publish("orders", json.dumps(order))
        logger.info(
            f"Published live order: {symbol} {side} qty={quantity:.6f} "
            f"entry={current_price:.4f} sl={stop_loss:.4f} tp={take_profit:.4f}"
        )
        return True
