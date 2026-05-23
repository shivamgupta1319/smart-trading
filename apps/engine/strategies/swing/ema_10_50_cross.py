import pandas as pd
import pandas_ta as ta
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
        if df.empty or len(df) < 50:
            return df

        df['EMA_10'] = ta.ema(df['Close'], length=10)
        df['EMA_50'] = ta.ema(df['Close'], length=50)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(1, len(df)):
            ema_10 = df['EMA_10'].iloc[i]
            ema_50 = df['EMA_50'].iloc[i]
            prev_ema_10 = df['EMA_10'].iloc[i-1]
            prev_ema_50 = df['EMA_50'].iloc[i-1]
            
            if pd.isna(ema_50) or pd.isna(prev_ema_50):
                continue
                
            close = df['Close'].iloc[i]
            low = df['Low'].iloc[i]
            high = df['High'].iloc[i]

            # Bullish Crossover
            if prev_ema_10 <= prev_ema_50 and ema_10 > ema_50:
                df.at[df.index[i], 'signal'] = 1
                # Stop loss below recent swing low (approximate with recent low)
                recent_low = df['Low'].iloc[max(0, i-5):i+1].min()
                sl = min(recent_low, close * 0.95)
                df.at[df.index[i], 'stop_loss'] = sl
                df.at[df.index[i], 'target'] = close + (close - sl) * 2

            # Bearish Crossover
            elif prev_ema_10 >= prev_ema_50 and ema_10 < ema_50:
                df.at[df.index[i], 'signal'] = -1
                recent_high = df['High'].iloc[max(0, i-5):i+1].max()
                sl = max(recent_high, close * 1.05)
                df.at[df.index[i], 'stop_loss'] = sl
                df.at[df.index[i], 'target'] = close - (sl - close) * 2

        return df
