"""Strategy 10: 50/200 Golden Cross (Swing)"""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy


class GoldenCrossStrategy(BaseStrategy):
    name = "Golden_Cross"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['sma50'] = ta.sma(df['Close'], length=50)
        df['sma200'] = ta.sma(df['Close'], length=200)
        df['atr14'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(1, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i - 1]

            if any(pd.isna([curr['sma50'], curr['sma200'], curr['atr14']])):
                continue

            # Golden Cross: 50 SMA crosses above 200 SMA
            golden = prev['sma50'] <= prev['sma200'] and curr['sma50'] > curr['sma200']
            if golden:
                sl = curr['sma50'] - 1.5 * curr['atr14']
                rr = curr['Close'] - sl
                df.iloc[i, df.columns.get_loc('signal')] = 1
                df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                df.iloc[i, df.columns.get_loc('target')] = curr['Close'] + 2 * rr

            # Death Cross: 50 SMA crosses below 200 SMA
            death = prev['sma50'] >= prev['sma200'] and curr['sma50'] < curr['sma200']
            if death:
                sl = curr['sma50'] + 1.5 * curr['atr14']
                rr = sl - curr['Close']
                df.iloc[i, df.columns.get_loc('signal')] = -1
                df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                df.iloc[i, df.columns.get_loc('target')] = curr['Close'] - 2 * rr

        return df
