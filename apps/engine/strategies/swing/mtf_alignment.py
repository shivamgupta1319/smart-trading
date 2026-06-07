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
            df = df.copy()
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
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
        weekly_df['SMA_50_W_Prev'] = weekly_df['SMA_50_W'].shift(1)

        weekly_mapping = weekly_df[['SMA_50_W_Prev']].copy()
        
        df_reset = df.reset_index()
        weekly_reset = weekly_mapping.reset_index()
        
        merged = pd.merge_asof(
            df_reset.sort_values('Date'),
            weekly_reset.sort_values('Date'),
            on='Date',
            direction='backward'
        )
        
        merged.set_index('Date', inplace=True)
        df['SMA_50_W'] = merged['SMA_50_W_Prev']

        df['High_20'] = df['High'].rolling(window=20).max().shift(1)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        bullish_cond = (df['Close'] > df['SMA_50_W']) & (df['Close'] > df['High_20'])
        
        # Edge trigger
        prev_bullish = bullish_cond.shift(1, fill_value=False)
        valid_bull = bullish_cond & ~prev_bullish

        df.loc[valid_bull, 'signal'] = 1
        df.loc[valid_bull, 'stop_loss'] = df['Low'][valid_bull] * 0.95
        df.loc[valid_bull, 'target'] = df['Close'][valid_bull] + (df['Close'][valid_bull] - df['stop_loss'][valid_bull]) * 3

        return df
