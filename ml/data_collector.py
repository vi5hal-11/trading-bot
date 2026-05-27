import asyncio
import os
import time
import ccxt
import pandas as pd
from functools import partial
from loguru import logger
from data.processor import DataProcessor

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# Binance has years of OHLCV history and 1000 candles per request (2× Blofin)
_BINANCE_EXCHANGE = ccxt.binance({"enableRateLimit": True})

# Map Blofin futures symbols → Binance spot symbols for data collection
_SYMBOL_MAP = {
    "BTC/USDT:USDT": "BTC/USDT",
    "ETH/USDT:USDT": "ETH/USDT",
    "SOL/USDT:USDT": "SOL/USDT",
}


class DataCollector:
    def __init__(self):
        self.processor = DataProcessor()
        os.makedirs(DATA_DIR, exist_ok=True)

    async def _fetch_symbol_history(
        self, binance_symbol: str, timeframe: str = "15m", months: int = 6
    ) -> pd.DataFrame:
        candles_needed = months * 30 * 24 * (60 // 15)  # ~17,280 for 6 months
        limit_per_call = 1000                            # Binance max
        ms_per_candle = 15 * 60 * 1000

        all_frames: list[pd.DataFrame] = []
        # Start from `months` ago and page forward
        since_ms = int(time.time() * 1000) - (months * 30 * 24 * 3600 * 1000)

        logger.info(f"Fetching ~{candles_needed} candles for {binance_symbol} from Binance...")

        while True:
            try:
                raw = await asyncio.get_event_loop().run_in_executor(
                    None,
                    partial(_BINANCE_EXCHANGE.fetch_ohlcv, binance_symbol, timeframe, since_ms, limit_per_call),
                )
            except Exception as e:
                logger.warning(f"Binance fetch error for {binance_symbol}: {e}")
                break

            if not raw:
                break

            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            all_frames.append(df)

            fetched = sum(len(f) for f in all_frames)
            logger.info(f"  {binance_symbol}: {fetched} candles fetched")

            if len(raw) < limit_per_call:
                break  # reached the end of available data

            since_ms = raw[-1][0] + ms_per_candle
            time.sleep(0.3)  # respect rate limit

        if not all_frames:
            return pd.DataFrame()

        combined = pd.concat(all_frames, ignore_index=True)
        combined.drop_duplicates(subset=["timestamp"], inplace=True)
        combined.sort_values("timestamp", inplace=True, ignore_index=True)
        combined["datetime"] = pd.to_datetime(combined["timestamp"], unit="ms", utc=True)
        combined = combined.set_index("datetime").drop(columns=["timestamp"]).astype(float)

        logger.info(f"  {binance_symbol}: {len(combined)} unique candles collected")
        return combined

    async def collect_all(
        self, symbols: list[str], timeframe: str = "15m", months: int = 6
    ) -> dict[str, pd.DataFrame]:
        results = {}

        for blofin_symbol in symbols:
            binance_symbol = _SYMBOL_MAP.get(blofin_symbol, blofin_symbol.split(":")[0])
            safe_name = blofin_symbol.replace("/", "_").replace(":", "_")
            cache_path = os.path.join(DATA_DIR, f"{safe_name}_{timeframe}.csv")

            # Reuse cache if < 24h old
            if os.path.exists(cache_path):
                age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
                if age_hours < 24:
                    logger.info(f"Loading cached data for {blofin_symbol} ({age_hours:.1f}h old)")
                    df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
                    df.index = pd.to_datetime(df.index, utc=True)
                    results[blofin_symbol] = df
                    continue

            raw_df = await self._fetch_symbol_history(binance_symbol, timeframe, months)
            if raw_df.empty:
                logger.warning(f"No data returned for {binance_symbol}, skipping")
                continue

            processed = self.processor.add_indicators(raw_df.copy())
            processed.to_csv(cache_path)
            results[blofin_symbol] = processed
            logger.info(f"Saved {len(processed)} rows for {blofin_symbol} → {cache_path}")

        return results
