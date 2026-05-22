"""Strategy 3: 9/15 EMA Crossover + RSI Filter"""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy


class EMARSIStrategy(BaseStrategy):
    name = "EMA_RSI"
    timeframe = "5m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df['ema9'] = ta.ema(df['Close'], length=9)
        df['ema15'] = ta.ema(df['Close'], length=15)
        df['rsi14'] = ta.rsi(df['Close'], length=14)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(2, len(df)):
            prev = df.iloc[i - 1]
            curr = df.iloc[i]

            if any(pd.isna([curr['ema9'], curr['ema15'], curr['rsi14']])):
                continue

            # Bullish crossover: 9 EMA crosses above 15 EMA AND RSI > 50
            ema_cross_up = prev['ema9'] <= prev['ema15'] and curr['ema9'] > curr['ema15']
            if ema_cross_up and curr['rsi14'] > 50:
                # SL = previous 5-bar swing low
                swing_low = df.iloc[max(0, i-5):i]['Low'].min()
                rr = curr['Close'] - swing_low
                df.iloc[i, df.columns.get_loc('signal')] = 1
                df.iloc[i, df.columns.get_loc('stop_loss')] = swing_low
                df.iloc[i, df.columns.get_loc('target')] = curr['Close'] + 2 * rr

            # Bearish crossover: 9 EMA crosses below 15 EMA AND RSI < 50
            ema_cross_down = prev['ema9'] >= prev['ema15'] and curr['ema9'] < curr['ema15']
            if ema_cross_down and curr['rsi14'] < 50:
                swing_high = df.iloc[max(0, i-5):i]['High'].max()
                rr = swing_high - curr['Close']
                df.iloc[i, df.columns.get_loc('signal')] = -1
                df.iloc[i, df.columns.get_loc('stop_loss')] = swing_high
                df.iloc[i, df.columns.get_loc('target')] = curr['Close'] - 2 * rr

        return df
