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
        df = df.copy()
        if df.empty or len(df) < 60:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
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

        channel_width = (df['High_60'] - df['Low_60']) / df['Low_60']
        high_drift = (df['High_60'] - df['High_60_Prev']).abs() / df['High_60_Prev']
        low_drift = (df['Low_60'] - df['Low_60_Prev']).abs() / df['Low_60_Prev']

        cond_channel_wide = channel_width >= 0.10
        cond_channel_stable = (high_drift <= 0.05) & (low_drift <= 0.05)
        
        # Buy exactly at the established bottom trendline (within 2%)
        cond_bounce = (df['Low'] <= df['Low_60'] * 1.02) & (df['Low'] >= df['Low_60'] * 0.98) & (df['Close'] > df['Open'])

        bullish_cond = cond_channel_wide & cond_channel_stable & cond_bounce
        
        # Edge-trigger
        prev_bullish = bullish_cond.shift(1, fill_value=False)
        valid_bull = bullish_cond & ~prev_bullish

        df.loc[valid_bull, 'signal'] = 1
        df.loc[valid_bull, 'stop_loss'] = df['Low_60'][valid_bull] * 0.985
        df.loc[valid_bull, 'target'] = df['High_60'][valid_bull]

        return df
