"""Strategy 4: MACD Zero-Line Cross"""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy


class MACDZeroStrategy(BaseStrategy):
    name = "MACD_Zero"
    timeframe = "15m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
        df['macd'] = macd['MACD_12_26_9']
        df['macd_signal'] = macd['MACDs_12_26_9']
        df['atr14'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(1, len(df)):
            prev = df.iloc[i - 1]
            curr = df.iloc[i]

            if any(pd.isna([curr['macd'], curr['macd_signal'], curr['atr14']])):
                continue

            # Bullish: MACD crosses above signal AND both are below zero
            cross_up = prev['macd'] <= prev['macd_signal'] and curr['macd'] > curr['macd_signal']
            if cross_up and curr['macd'] < 0 and curr['macd_signal'] < 0:
                sl = curr['Close'] - curr['atr14']
                rr = curr['Close'] - sl
                df.iloc[i, df.columns.get_loc('signal')] = 1
                df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                df.iloc[i, df.columns.get_loc('target')] = curr['Close'] + 2 * rr

            # Bearish: MACD crosses below signal AND both are above zero
            cross_down = prev['macd'] >= prev['macd_signal'] and curr['macd'] < curr['macd_signal']
            if cross_down and curr['macd'] > 0 and curr['macd_signal'] > 0:
                sl = curr['Close'] + curr['atr14']
                rr = sl - curr['Close']
                df.iloc[i, df.columns.get_loc('signal')] = -1
                df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                df.iloc[i, df.columns.get_loc('target')] = curr['Close'] - 2 * rr

        return df
