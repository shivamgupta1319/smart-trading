import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy

class SMA44PullbackStrategy(BaseStrategy):
    """Strategy 6: 44 SMA Pullback (Swing)"""
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

        prev_low = df['Low'].shift(1)
        
        above_200 = df['Close'] > df['sma200']
        touched_44 = (prev_low <= df['sma44']) | (df['Low'] <= df['sma44'])
        bullish_candle = df['Close'] > df['Open']

        bullish_cond = above_200 & touched_44 & bullish_candle
        
        # Edge trigger
        prev_bullish = bullish_cond.shift(1, fill_value=False)
        valid_bull = bullish_cond & ~prev_bullish

        sl = df['Low'] - 1.5 * df['atr14']

        df.loc[valid_bull, 'signal'] = 1
        df.loc[valid_bull, 'stop_loss'] = sl[valid_bull]
        df.loc[valid_bull, 'target'] = df['Close'][valid_bull] + 2 * (df['Close'][valid_bull] - sl[valid_bull])

        return df
