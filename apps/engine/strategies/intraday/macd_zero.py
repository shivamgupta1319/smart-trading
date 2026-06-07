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
        if macd is None or macd.empty:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df
            
        df['macd'] = macd['MACD_12_26_9']
        df['macd_signal'] = macd['MACDs_12_26_9']
        df['atr14'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        prev_macd = df['macd'].shift(1)
        prev_signal = df['macd_signal'].shift(1)

        # Bullish: MACD crosses above signal AND both are below zero
        cross_up = (prev_macd <= prev_signal) & (df['macd'] > df['macd_signal'])
        bullish_cond = cross_up & (df['macd'] < 0) & (df['macd_signal'] < 0)

        # Bearish: MACD crosses below signal AND both are above zero
        cross_down = (prev_macd >= prev_signal) & (df['macd'] < df['macd_signal'])
        bearish_cond = cross_down & (df['macd'] > 0) & (df['macd_signal'] > 0)

        df.loc[bullish_cond, 'signal'] = 1
        sl_bull = df['Close'] - df['atr14']
        df.loc[bullish_cond, 'stop_loss'] = sl_bull[bullish_cond]
        df.loc[bullish_cond, 'target'] = df['Close'][bullish_cond] + 2 * (df['Close'][bullish_cond] - sl_bull[bullish_cond])

        df.loc[bearish_cond, 'signal'] = -1
        sl_bear = df['Close'] + df['atr14']
        df.loc[bearish_cond, 'stop_loss'] = sl_bear[bearish_cond]
        df.loc[bearish_cond, 'target'] = df['Close'][bearish_cond] - 2 * (sl_bear[bearish_cond] - df['Close'][bearish_cond])

        return df
