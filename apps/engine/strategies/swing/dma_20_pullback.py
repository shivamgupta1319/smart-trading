import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy

class DMA20PullbackStrategy(BaseStrategy):
    """
    The 20-DMA Pullback Strategy
    Timeframe: 1D
    Logic:
    - Trend: Close > 50 DMA
    - Pullback: Low touches or falls below 20 DMA, but closes above it (bullish reversal).
    - Volume: Lower than average volume on the pullback.
    """
    name = "DMA20_Pullback"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if df.empty or len(df) < 50:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df

        df['SMA_20'] = ta.sma(df['Close'], length=20)
        df['SMA_50'] = ta.sma(df['Close'], length=50)
        df['Vol_SMA'] = ta.sma(df['Volume'], length=20)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        # Uptrend condition
        uptrend = (df['SMA_20'] > df['SMA_50']) & (df['Close'] > df['SMA_50'])
        
        # Pullback to 20 DMA
        pullback = (df['Low'] <= df['SMA_20']) & (df['Close'] > df['SMA_20']) & (df['Close'] > df['Open'])
        
        # Lower than average volume
        low_vol = df['Volume'] < (df['Vol_SMA'] * 1.2)

        bullish_cond = uptrend & pullback & low_vol

        # Edge-trigger
        prev_bullish = bullish_cond.shift(1, fill_value=False)
        valid_bull = bullish_cond & ~prev_bullish

        df.loc[valid_bull, 'signal'] = 1
        df.loc[valid_bull, 'stop_loss'] = df['Low'][valid_bull] * 0.98
        df.loc[valid_bull, 'target'] = df['Close'][valid_bull] + (df['Close'][valid_bull] - df['stop_loss'][valid_bull]) * 2

        return df
