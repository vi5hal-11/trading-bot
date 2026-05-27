from pydantic_settings import BaseSettings
from pydantic import Field
import yaml
import os


class Settings(BaseSettings):
    # Binance USDT-M Futures
    binance_api_key: str = Field(default="", alias="BINANCE_API_KEY")
    binance_secret_key: str = Field(default="", alias="BINANCE_SECRET_KEY")
    binance_testnet: bool = Field(default=True, alias="BINANCE_TESTNET")

    # Paper trading (uses internal simulation — no exchange connection)
    paper_trading: bool = Field(default=True, alias="PAPER_TRADING")
    paper_initial_balance: float = Field(default=10000.0, alias="PAPER_INITIAL_BALANCE")

    # Infrastructure
    database_url: str = Field(
        default="postgresql://bot_user:secure_password@localhost:5433/trading_bot",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # Telegram
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    # Sentiment
    cryptopanic_api_key: str = Field(default="", alias="CRYPTOPANIC_API_KEY")

    # Web dashboard
    web_host: str = Field(default="0.0.0.0", alias="WEB_HOST")
    web_port: int = Field(default=8080, alias="WEB_PORT")

    # ML retraining
    model_retraining_enabled: bool = Field(default=True, alias="MODEL_RETRAINING_ENABLED")
    retrain_day_of_week: str = Field(default="sun", alias="RETRAIN_DAY_OF_WEEK")
    retrain_hour: int = Field(default=2, alias="RETRAIN_HOUR")
    promotion_sharpe_delta: float = Field(default=0.10, alias="PROMOTION_SHARPE_DELTA")
    validation_days: int = Field(default=14, alias="VALIDATION_DAYS")

    model_config = {"env_file": ".env", "populate_by_name": True}


def load_trading_params() -> dict:
    params_path = os.path.join(os.path.dirname(__file__), "trading_params.yaml")
    with open(params_path) as f:
        return yaml.safe_load(f)
