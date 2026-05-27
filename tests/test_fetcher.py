import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from config.settings import Settings
from data.fetcher import BlofinDataFetcher


@pytest.fixture
def settings():
    return Settings(PAPER_TRADING=True)


@pytest.mark.asyncio
async def test_fetch_ohlcv_returns_dataframe(settings):
    fetcher = BlofinDataFetcher(settings)

    raw = [
        [1700000000000, 35000.0, 35500.0, 34800.0, 35200.0, 1000.0],
        [1700000060000, 35200.0, 35600.0, 35100.0, 35400.0, 1200.0],
    ]

    with patch.object(fetcher, "_get_exchange") as mock_get:
        mock_exchange = AsyncMock()
        mock_exchange.fetch_ohlcv = AsyncMock(return_value=raw)
        mock_get.return_value = mock_exchange

        df = await fetcher.fetch_ohlcv("BTC/USDT:USDT", "15m", limit=2)

    assert not df.empty
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 2
    await fetcher.close()


@pytest.mark.asyncio
async def test_fetch_all_ohlcv_skips_errors(settings):
    fetcher = BlofinDataFetcher(settings)

    async def mock_fetch(symbol, tf, limit):
        if symbol == "BAD/USDT:USDT":
            raise Exception("not found")
        raw = [[1700000000000, 1.0, 1.1, 0.9, 1.05, 500.0]]
        import pandas as pd
        import pandas as pd
        df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume"])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df.set_index("datetime").drop(columns=["timestamp"]).astype(float)

    with patch.object(fetcher, "fetch_ohlcv", side_effect=mock_fetch):
        result = await fetcher.fetch_all_ohlcv(["ETH/USDT:USDT", "BAD/USDT:USDT"])

    assert "ETH/USDT:USDT" in result
    assert "BAD/USDT:USDT" not in result
    await fetcher.close()
