"""Strategy 6: 44 SMA Pullback (Swing)"""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy


class SMA44PullbackStrategy(BaseStrategy):
    name = "SMA44_Pullback"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['sma44'] = ta.sma(df['Close'], length=44)
        df['sma200'] = ta.sma(df['Close'], length=200)
        df['atr14'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(1, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i - 1]

            if any(pd.isna([curr['sma44'], curr['sma200'], curr['atr14']])):
                continue

            # Filter: price must be above 200 SMA
            if curr['Close'] <= curr['sma200']:
                continue

            # Entry: price touches 44 SMA and closes bullish
            touched_44 = prev['Low'] <= curr['sma44'] or curr['Low'] <= curr['sma44']
            bullish_candle = curr['Close'] > curr['Open']

            if touched_44 and bullish_candle:
                sl = curr['Low'] - 1.5 * curr['atr14']
                rr = curr['Close'] - sl
                df.iloc[i, df.columns.get_loc('signal')] = 1
                df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                df.iloc[i, df.columns.get_loc('target')] = curr['Close'] + 2 * rr

        return df
