"""Phase 1 integration smoke test — no API keys required."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config.settings import Settings
from data.fetcher import BlofinDataFetcher
from data.processor import DataProcessor
from strategies.momentum import MomentumStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.trend_following import TrendFollowingStrategy
from strategies.ensemble import EnsembleStrategy
from trading_engine.risk_calculator import RiskCalculator
from trading_engine.paper_trader import PaperTrader


async def run():
    settings = Settings()
    assert settings.paper_trading, "Should be in paper mode"

    # Fetch real data
    fetcher = BlofinDataFetcher(settings)
    print("Fetching BTC/USDT:USDT 15m candles...")
    df = await fetcher.fetch_ohlcv("BTC/USDT:USDT", "15m", limit=250)
    print(f"  Got {len(df)} candles. Latest close: {df['close'].iloc[-1]:.2f}")

    # Process indicators
    proc = DataProcessor()
    df = proc.add_indicators(df)
    print(f"  After indicators: {len(df)} rows, {len(df.columns)} columns")

    latest = df.iloc[-1]
    print(f"  RSI={latest['rsi']:.1f} | MACD_hist={latest['macd_hist']:.4f} | ADX={latest['adx']:.1f}")

    # Run ensemble
    ensemble = EnsembleStrategy()
    ensemble.register(MomentumStrategy())
    ensemble.register(MeanReversionStrategy())
    ensemble.register(TrendFollowingStrategy())

    signal = ensemble.generate_signal(df, "BTC/USDT:USDT")
    print(f"\nEnsemble signal: {signal['action']} | conf={signal['confidence']:.3f} | consensus={signal['consensus_score']:+.4f}")
    print(f"  Components: {signal['component_signals']}")

    # Test paper trader
    risk = RiskCalculator()
    paper = PaperTrader(settings, risk)
    print(f"\nPaper trader balance: {paper.balance:.2f} USDT")

    if signal["action"] in ("BUY", "SELL"):
        atr = latest["atr"]
        pos = paper.open_position("BTC/USDT:USDT", signal, latest["close"], atr)
        if pos:
            print(f"  Opened {pos.side} position: qty={pos.quantity:.6f} entry={pos.entry_price:.2f} stop={pos.stop_loss:.2f}")
            print(f"  Remaining balance: {paper.balance:.2f}")
    else:
        print("  HOLD — no position opened")

    summary = paper.summary()
    print(f"\nSummary: {summary}")

    await fetcher.close()
    print("\nPhase 1 smoke test PASSED")


if __name__ == "__main__":
    asyncio.run(run())
