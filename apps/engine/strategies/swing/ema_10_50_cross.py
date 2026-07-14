import pandas as pd
import pandas_ta as ta
import numpy as np
from strategies.base import BaseStrategy

class EMA1050CrossStrategy(BaseStrategy):
    """
    The 10/50 EMA Crossover Strategy
    Timeframe: 1D
    Logic:
    - Long when 10 EMA crosses above 50 EMA.
    - Short when 10 EMA crosses below 50 EMA.
    """
    name = "EMA_10_50_Cross"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if df.empty or len(df) < 50:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df

        df['EMA_10'] = ta.ema(df['Close'], length=10)
        df['EMA_50'] = ta.ema(df['Close'], length=50)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        prev_ema_10 = df['EMA_10'].shift(1)
        prev_ema_50 = df['EMA_50'].shift(1)

        bullish_cond = (prev_ema_10 <= prev_ema_50) & (df['EMA_10'] > df['EMA_50'])
        bearish_cond = (prev_ema_10 >= prev_ema_50) & (df['EMA_10'] < df['EMA_50'])

        recent_low = df['Low'].rolling(window=6, min_periods=1).min()
        recent_high = df['High'].rolling(window=6, min_periods=1).max()

        sl_bull = np.minimum(recent_low, df['Close'] * 0.95)
        sl_bear = np.maximum(recent_high, df['Close'] * 1.05)

        df.loc[bullish_cond, 'signal'] = 1
        df.loc[bullish_cond, 'stop_loss'] = sl_bull[bullish_cond]
        df.loc[bullish_cond, 'target'] = df['Close'][bullish_cond] + (df['Close'][bullish_cond] - sl_bull[bullish_cond]) * 2

        df.loc[bearish_cond, 'signal'] = -1
        df.loc[bearish_cond, 'stop_loss'] = sl_bear[bearish_cond]
        df.loc[bearish_cond, 'target'] = df['Close'][bearish_cond] - (sl_bear[bearish_cond] - df['Close'][bearish_cond]) * 2

        return df
