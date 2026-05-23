import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy

class MTFAlignmentStrategy(BaseStrategy):
    """
    Multi-Timeframe Alignment Strategy
    Timeframe: 1D
    Logic:
    - Weekly Trend Filter: Weekly Close must be > 50-Week SMA.
    - Daily Entry: Breakout of the 20-Day High.
    """
    name = "MTF_Alignment"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or len(df) < 250: # Need 50 weeks of data (~250 days)
            return df

        if not pd.api.types.is_datetime64_any_dtype(df.index):
            df.index = pd.to_datetime(df.index)

        # 1. Resample to Weekly and calculate 50-Week SMA
        weekly_df = df.resample('W').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        })
        
        weekly_df['SMA_50_W'] = ta.sma(weekly_df['Close'], length=50)
        
        # Shift the weekly SMA so we use last week's SMA for this week's filter
        weekly_df['SMA_50_W_Prev'] = weekly_df['SMA_50_W'].shift(1)

        # Map the Weekly SMA back to the Daily timeframe
        # We can use merge_asof to match each day to the previous week's data
        weekly_mapping = weekly_df[['SMA_50_W_Prev']].copy()
        
        # Reset indexes to merge
        df_reset = df.reset_index()
        weekly_reset = weekly_mapping.reset_index()
        
        # Backward fill: match each day to the most recent weekly close BEFORE that day
        # e.g., Monday uses last Friday's weekly close/SMA
        merged = pd.merge_asof(
            df_reset.sort_values('Date'),
            weekly_reset.sort_values('Date'),
            on='Date',
            direction='backward'
        )
        
        # Restore index
        merged.set_index('Date', inplace=True)
        df['SMA_50_W'] = merged['SMA_50_W_Prev']

        # 2. Daily Entry Logic: Breakout of 20-Day High
        df['High_20'] = df['High'].rolling(window=20).max().shift(1)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(250, len(df)):
            close = df['Close'].iloc[i]
            low = df['Low'].iloc[i]
            
            sma_50_w = df['SMA_50_W'].iloc[i]
            high_20 = df['High_20'].iloc[i]

            if pd.isna(sma_50_w) or pd.isna(high_20):
                continue

            # Multi-Timeframe Alignment: Weekly is Bullish
            if close > sma_50_w:
                # Daily Setup: Breakout above 20-day high
                if close > high_20:
                    df.at[df.index[i], 'signal'] = 1
                    sl = low * 0.95 # 5% stop loss
                    df.at[df.index[i], 'stop_loss'] = sl
                    df.at[df.index[i], 'target'] = close + (close - sl) * 3

        return df
