import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy


class EMA200MACDStrategy(BaseStrategy):
    """Strategy 7: 200 EMA + MACD Golden Trend (Swing)"""
    name = "EMA200_MACD"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # Needs a full 200-period EMA; on shorter slices (e.g. a walk-forward
        # fold) pandas_ta returns None, so guard before touching it.
        if df.empty or len(df) < 200:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df

        df['ema200'] = ta.ema(df['Close'], length=200)
        df['atr14'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
        if macd is not None and not macd.empty:
            df['macd'] = macd['MACD_12_26_9']
            df['macd_sig'] = macd['MACDs_12_26_9']
        else:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        prev_macd = df['macd'].shift(1)
        prev_macd_sig = df['macd_sig'].shift(1)

        cross_up = (prev_macd <= prev_macd_sig) & (df['macd'] > df['macd_sig'])
        above_ema200 = df['Close'] > df['ema200']

        bullish_cond = cross_up & above_ema200

        swing_low = df['Low'].rolling(window=6, min_periods=1).min()
        sl = swing_low - df['atr14']

        df.loc[bullish_cond, 'signal'] = 1
        df.loc[bullish_cond, 'stop_loss'] = sl[bullish_cond]
        df.loc[bullish_cond, 'target'] = df['Close'][bullish_cond] + 2 * (df['Close'][bullish_cond] - sl[bullish_cond])

        return df
