import pandas as pd
from strategies.base import BaseStrategy

class ChannelOscillationStrategy(BaseStrategy):
    """
    Channel Oscillation Trading Strategy
    Timeframe: 1D
    Logic:
    - Identifies a 60-day sideways channel (min and max are relatively stable, >10% apart).
    - Long when price approaches the 60-day low (bottom of channel) and prints a bullish candle.
    - Target: Top of the channel.
    - Stop loss: 1-2% below the channel bottom.
    """
    name = "Channel_Oscillation"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or len(df) < 60:
            return df

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0
        
        # 60-day High and Low
        df['High_60'] = df['High'].rolling(window=60).max().shift(1)
        df['Low_60'] = df['Low'].rolling(window=60).min().shift(1)
        
        # To ensure the channel is "flat" or stable, we compare current 60-day limits with 20 days ago
        df['High_60_Prev'] = df['High_60'].shift(20)
        df['Low_60_Prev'] = df['Low_60'].shift(20)

        for i in range(80, len(df)):
            close = df['Close'].iloc[i]
            open_p = df['Open'].iloc[i]
            low = df['Low'].iloc[i]
            
            high_60 = df['High_60'].iloc[i]
            low_60 = df['Low_60'].iloc[i]
            high_60_prev = df['High_60_Prev'].iloc[i]
            low_60_prev = df['Low_60_Prev'].iloc[i]

            if pd.isna(high_60_prev) or pd.isna(low_60_prev):
                continue

            # 1. Check if channel is wide enough (> 10%)
            channel_width = (high_60 - low_60) / low_60
            if channel_width < 0.10:
                continue
                
            # 2. Check if channel is stable (limits haven't moved more than 5% in 20 days)
            high_drift = abs(high_60 - high_60_prev) / high_60_prev
            low_drift = abs(low_60 - low_60_prev) / low_60_prev
            
            if high_drift > 0.05 or low_drift > 0.05:
                continue

            # 3. Buy exactly at the established bottom trendline (within 2%)
            if low <= low_60 * 1.02 and low >= low_60 * 0.98:
                # Enter on bullish close
                if close > open_p:
                    df.at[df.index[i], 'signal'] = 1
                    # Stop loss 1.5% below channel bottom
                    df.at[df.index[i], 'stop_loss'] = low_60 * 0.985
                    # Target top of channel
                    df.at[df.index[i], 'target'] = high_60

        return df
