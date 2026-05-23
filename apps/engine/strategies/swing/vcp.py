import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy

class VCPStrategy(BaseStrategy):
    """
    Volatility Contraction Pattern (VCP) Strategy
    Timeframe: 1D
    Logic:
    - Approximates VCP by looking for a period of low volatility (narrowing price range)
    - Volume drying up during the consolidation (10-day avg vol < 50-day avg vol)
    - Breakout above 20-day high on heavy volume (volume > 1.5x 50-day avg).
    """
    name = "VCP"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or len(df) < 50:
            return df

        # Calculate metrics
        df['Vol_10'] = ta.sma(df['Volume'], length=10)
        df['Vol_50'] = ta.sma(df['Volume'], length=50)
        
        # Volatility contraction: 20-day ATR as a percentage of price should be dropping or low
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=20)
        df['ATR_Pct'] = df['ATR'] / df['Close']
        
        # 20-day Rolling High for Breakout
        df['High_20'] = df['High'].rolling(window=20).max().shift(1)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(50, len(df)):
            close = df['Close'].iloc[i]
            high = df['High'].iloc[i]
            low = df['Low'].iloc[i]
            vol = df['Volume'].iloc[i]
            
            vol_10 = df['Vol_10'].iloc[i-1] # Volume leading up to breakout
            vol_50 = df['Vol_50'].iloc[i-1]
            
            atr_pct = df['ATR_Pct'].iloc[i-1]
            high_20 = df['High_20'].iloc[i]

            if pd.isna(vol_50) or pd.isna(high_20):
                continue

            # 1. Volume drying up before breakout
            vol_dry = vol_10 < vol_50
            
            # 2. Volatility is relatively low (e.g. ATR is less than 3% of price)
            low_volatility = atr_pct < 0.03
            
            # 3. Breakout on heavy volume
            breakout = close > high_20
            heavy_volume = vol > (vol_50 * 1.5)

            if vol_dry and low_volatility and breakout and heavy_volume:
                df.at[df.index[i], 'signal'] = 1
                # Stop loss below the breakout candle's low or 5% max
                sl = max(low - (close * 0.01), close * 0.95)
                df.at[df.index[i], 'stop_loss'] = sl
                # Target 1:2 to 1:3 RR
                df.at[df.index[i], 'target'] = close + (close - sl) * 2.5

        return df
