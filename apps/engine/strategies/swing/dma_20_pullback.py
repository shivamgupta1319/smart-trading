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
        if df.empty or len(df) < 50:
            return df

        df['SMA_20'] = ta.sma(df['Close'], length=20)
        df['SMA_50'] = ta.sma(df['Close'], length=50)
        df['Vol_SMA'] = ta.sma(df['Volume'], length=20)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(1, len(df)):
            close = df['Close'].iloc[i]
            open_p = df['Open'].iloc[i]
            low = df['Low'].iloc[i]
            vol = df['Volume'].iloc[i]
            
            sma20 = df['SMA_20'].iloc[i]
            sma50 = df['SMA_50'].iloc[i]
            vol_sma = df['Vol_SMA'].iloc[i]

            if pd.isna(sma50):
                continue

            # Uptrend condition
            if sma20 > sma50 and close > sma50:
                # Pullback to 20 DMA
                if low <= sma20 and close > sma20 and close > open_p:
                    # Lower than average volume
                    if vol < vol_sma * 1.2:
                        df.at[df.index[i], 'signal'] = 1
                        df.at[df.index[i], 'stop_loss'] = low * 0.98 # 2% below the low
                        df.at[df.index[i], 'target'] = close + (close - df.at[df.index[i], 'stop_loss']) * 2

        return df
