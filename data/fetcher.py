import asyncio
import ccxt
import pandas as pd
from loguru import logger
from functools import partial
from config.settings import Settings, load_trading_params


class BlofinDataFetcher:
    """
    Wraps synchronous CCXT in asyncio's thread pool to avoid aiodns issues on Windows.
    Async interface is preserved so the rest of the codebase stays async-clean.
    """

    def __init__(self, settings: Settings):
        params = load_trading_params()
        exc_cfg = params["exchange"]

        # OHLCV is a public endpoint — no API keys or demo mode needed
        kwargs = {
            "enableRateLimit": True,
            "options": {"defaultType": exc_cfg["default_type"]},
        }

        exchange_class = getattr(ccxt, exc_cfg["name"])
        self._exchange = exchange_class(kwargs)
        self._loop = None

    def _get_loop(self):
        if self._loop is None:
            self._loop = asyncio.get_event_loop()
        return self._loop

    async def _run(self, fn, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(fn, *args, **kwargs))

    async def close(self):
        pass  # sync CCXT needs no close

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "15m", limit: int = 200
    ) -> pd.DataFrame:
        try:
            raw = await self._run(
                self._exchange.fetch_ohlcv, symbol, timeframe, None, limit
            )
            df = pd.DataFrame(
                raw, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df = df.set_index("datetime").drop(columns=["timestamp"])
            return df.astype(float)
        except Exception as e:
            logger.error(f"fetch_ohlcv {symbol}: {e}")
            raise

    async def fetch_ticker(self, symbol: str) -> dict:
        try:
            return await self._run(self._exchange.fetch_ticker, symbol)
        except Exception as e:
            logger.error(f"fetch_ticker {symbol}: {e}")
            raise

    async def fetch_orderbook(self, symbol: str, limit: int = 20) -> dict:
        try:
            ob = await self._run(self._exchange.fetch_order_book, symbol, limit)
            return {"bids": ob["bids"][:limit], "asks": ob["asks"][:limit]}
        except Exception as e:
            logger.error(f"fetch_orderbook {symbol}: {e}")
            raise

    async def fetch_all_ohlcv(
        self, symbols: list[str], timeframe: str = "15m", limit: int = 200
    ) -> dict[str, pd.DataFrame]:
        tasks = {s: self.fetch_ohlcv(s, timeframe, limit) for s in symbols}
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        out = {}
        for symbol, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.warning(f"Skipping {symbol}: {result}")
            else:
                out[symbol] = result
        return out
