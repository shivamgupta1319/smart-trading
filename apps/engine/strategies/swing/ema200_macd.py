"""Strategy 7: 200 EMA + MACD Golden Trend (Swing)"""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy


class EMA200MACDStrategy(BaseStrategy):
    name = "EMA200_MACD"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['ema200'] = ta.ema(df['Close'], length=200)
        df['atr14'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
        df['macd'] = macd['MACD_12_26_9']
        df['macd_sig'] = macd['MACDs_12_26_9']

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(1, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i - 1]

            if any(pd.isna([curr['ema200'], curr['macd'], curr['macd_sig'], curr['atr14']])):
                continue

            # Filter: price above 200 EMA
            if curr['Close'] <= curr['ema200']:
                continue

            # Entry: MACD bullish crossover
            cross_up = prev['macd'] <= prev['macd_sig'] and curr['macd'] > curr['macd_sig']
            if cross_up:
                swing_low = df.iloc[max(0, i-5):i]['Low'].min()
                sl = swing_low - curr['atr14']
                rr = curr['Close'] - sl
                df.iloc[i, df.columns.get_loc('signal')] = 1
                df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                df.iloc[i, df.columns.get_loc('target')] = curr['Close'] + 2 * rr

        return df
