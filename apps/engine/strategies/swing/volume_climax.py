import pandas as pd
from strategies.base import BaseStrategy

class VolumeClimaxStrategy(BaseStrategy):
    """
    Volume Climax Capitulation Strategy
    Timeframe: 1D
    Logic:
    - Finds a massive red candle with 1-year (250 day) high volume.
    - Waits for the price to close above the high of that panic candle within 5 days.
    """
    name = "Volume_Climax"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or len(df) < 250:
            return df

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0
        
        # 250-day Volume High
        df['Vol_High_250'] = df['Volume'].rolling(window=250).max().shift(1)
        
        active_climax_high = 0
        active_climax_low = 0
        days_since_climax = 0

        for i in range(250, len(df)):
            close = df['Close'].iloc[i]
            open_p = df['Open'].iloc[i]
            high = df['High'].iloc[i]
            low = df['Low'].iloc[i]
            vol = df['Volume'].iloc[i]
            
            vol_high = df['Vol_High_250'].iloc[i]

            if pd.isna(vol_high):
                continue

            # 1. Detect Volume Climax Capitulation
            # Massive red candle (Close < Open) with volume breaking the 1-year high
            if vol > vol_high and close < open_p and close < df['Close'].iloc[i-1]:
                active_climax_high = high
                active_climax_low = low
                days_since_climax = 0
                continue
                
            # 2. Wait for close above the climax high within 5 days
            if active_climax_high > 0:
                days_since_climax += 1
                
                if days_since_climax <= 5:
                    if close > active_climax_high:
                        df.at[df.index[i], 'signal'] = 1
                        # Stop loss at the low of the panic candle
                        sl = min(active_climax_low, low * 0.98)
                        df.at[df.index[i], 'stop_loss'] = sl
                        df.at[df.index[i], 'target'] = close + (close - sl) * 3
                        
                        # Reset
                        active_climax_high = 0
                else:
                    # Time limit exceeded
                    active_climax_high = 0

        return df
