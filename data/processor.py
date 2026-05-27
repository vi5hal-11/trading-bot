import pandas as pd
import ta
from loguru import logger
from config.settings import load_trading_params


class DataProcessor:
    def __init__(self):
        p = load_trading_params()["indicators"]
        self.rsi_period = p["rsi_period"]
        self.macd_fast = p["macd_fast"]
        self.macd_slow = p["macd_slow"]
        self.macd_signal = p["macd_signal"]
        self.bb_period = p["bb_period"]
        self.bb_std = p["bb_std"]
        self.atr_period = p["atr_period"]
        self.adx_period = p["adx_period"]
        self.sma_fast = p["sma_fast"]
        self.sma_slow = p["sma_slow"]
        self.vol_ma = p["volume_ma_period"]

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < self.sma_slow + 1:
            logger.warning(f"Not enough candles ({len(df)}) to compute all indicators")

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # Momentum
        df["rsi"] = ta.momentum.RSIIndicator(close, self.rsi_period).rsi()
        macd = ta.trend.MACD(close, self.macd_slow, self.macd_fast, self.macd_signal)
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_hist"] = macd.macd_diff()

        # Volatility
        bb = ta.volatility.BollingerBands(close, self.bb_period, self.bb_std)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_mid"] = bb.bollinger_mavg()
        df["bb_pct"] = bb.bollinger_pband()   # 0 = lower, 1 = upper

        atr = ta.volatility.AverageTrueRange(high, low, close, self.atr_period)
        df["atr"] = atr.average_true_range()

        # Trend
        df["sma_fast"] = ta.trend.SMAIndicator(close, self.sma_fast).sma_indicator()
        df["sma_slow"] = ta.trend.SMAIndicator(close, self.sma_slow).sma_indicator()
        df["ema_12"] = ta.trend.EMAIndicator(close, 12).ema_indicator()
        df["ema_26"] = ta.trend.EMAIndicator(close, 26).ema_indicator()

        adx = ta.trend.ADXIndicator(high, low, close, self.adx_period)
        df["adx"] = adx.adx()

        # Volume
        df["obv"] = ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume()
        df["vol_ma"] = close.rolling(self.vol_ma).mean()  # volume MA proxy
        df["vol_ratio"] = volume / volume.rolling(self.vol_ma).mean()

        df.dropna(inplace=True)
        return df

    def latest(self, df: pd.DataFrame) -> pd.Series:
        return df.iloc[-1]
