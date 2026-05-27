import time
import requests
import feedparser
import pandas as pd
from datetime import datetime, timezone, timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from loguru import logger
from strategies.base import BaseStrategy
from config.settings import Settings

_FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"
_CACHE_TTL = 900  # 15 minutes

# Free RSS feeds — no API keys required
_RSS_FEEDS = {
    "BTC":  [
        "https://news.google.com/rss/search?q=Bitcoin+BTC+crypto&hl=en-US&gl=US&ceid=US:en",
        "https://cointelegraph.com/rss/tag/bitcoin",
    ],
    "ETH":  [
        "https://news.google.com/rss/search?q=Ethereum+ETH+crypto&hl=en-US&gl=US&ceid=US:en",
        "https://cointelegraph.com/rss/tag/ethereum",
    ],
    "SOL":  [
        "https://news.google.com/rss/search?q=Solana+SOL+crypto&hl=en-US&gl=US&ceid=US:en",
        "https://cointelegraph.com/rss/tag/solana",
    ],
    "_generic": [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
    ],
}
_CUTOFF_HOURS = 24  # only score headlines from last 24h


class SentimentStrategy(BaseStrategy):
    name = "sentiment"

    def __init__(self, settings: Settings = None):
        self._vader = SentimentIntensityAnalyzer()
        self._fg_cache: tuple[float, float] | None = None          # (ts, score)
        self._rss_cache: dict[str, tuple[float, float]] = {}       # symbol → (ts, score)

    # ── Fear & Greed ──────────────────────────────────────────────────────────

    def _fetch_fear_greed(self) -> float:
        """Contrarian score: fear → positive (buy), greed → negative (sell). Range -1 to +1."""
        now = time.time()
        if self._fg_cache and (now - self._fg_cache[0]) < _CACHE_TTL:
            return self._fg_cache[1]
        try:
            resp = requests.get(_FEAR_GREED_URL, timeout=5)
            value = int(resp.json()["data"][0]["value"])
            score = -(value - 50) / 50.0   # 0→+1 (extreme fear=buy), 100→-1 (extreme greed=sell)
            self._fg_cache = (now, score)
            logger.debug(f"Fear & Greed index: {value} → score={score:+.3f}")
            return score
        except Exception as e:
            logger.debug(f"Fear & Greed fetch failed: {e}")
            return 0.0

    # ── RSS + VADER ───────────────────────────────────────────────────────────

    def _fetch_rss_sentiment(self, symbol: str) -> float:
        """VADER sentiment on recent headlines from free RSS feeds. Range -1 to +1."""
        now = time.time()
        cached = self._rss_cache.get(symbol)
        if cached and (now - cached[0]) < _CACHE_TTL:
            return cached[1]

        currency = symbol.split("/")[0]  # BTC/USDT:USDT → BTC
        feeds = _RSS_FEEDS.get(currency, []) + _RSS_FEEDS["_generic"]

        cutoff = datetime.now(timezone.utc) - timedelta(hours=_CUTOFF_HOURS)
        scores = []

        for url in feeds:
            try:
                parsed = feedparser.parse(url)
                for entry in parsed.entries:
                    # Parse published date
                    pub = entry.get("published_parsed")
                    if pub:
                        pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
                        if pub_dt < cutoff:
                            continue

                    text = entry.get("title", "") + " " + entry.get("summary", "")
                    if not text.strip():
                        continue

                    vs = self._vader.polarity_scores(text)
                    scores.append(vs["compound"])  # compound: -1 to +1

            except Exception as e:
                logger.debug(f"RSS feed error ({url}): {e}")
                continue

        score = float(sum(scores) / len(scores)) if scores else 0.0
        self._rss_cache[symbol] = (now, score)
        logger.debug(f"RSS sentiment {currency}: {len(scores)} headlines → score={score:+.3f}")
        return score

    # ── Strategy interface ────────────────────────────────────────────────────

    def generate_signal(self, df: pd.DataFrame, symbol: str = "") -> dict:
        fg_score  = self._fetch_fear_greed()
        rss_score = self._fetch_rss_sentiment(symbol) if symbol else 0.0

        # 60% fear/greed (macro) + 40% news sentiment (symbol-specific)
        final_score = 0.6 * fg_score + 0.4 * rss_score
        final_score = max(-1.0, min(1.0, final_score))

        if final_score > 0.25:
            action = "BUY"
        elif final_score < -0.25:
            action = "SELL"
        else:
            action = "HOLD"

        confidence = round(abs(final_score), 4)
        logger.debug(f"Sentiment {symbol}: fg={fg_score:+.3f} rss={rss_score:+.3f} → {action} ({confidence:.3f})")
        return {"action": action, "confidence": confidence}
