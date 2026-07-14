"""Strategy 5: Inside Bar Breakout"""
import pandas as pd
from strategies.base import BaseStrategy


class InsideBarStrategy(BaseStrategy):
    name = "Inside_Bar"
    timeframe = "15m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        prev_high = df['High'].shift(1)
        prev_low = df['Low'].shift(1)
        mother_high = df['High'].shift(2)
        mother_low = df['Low'].shift(2)

        # Identify inside bar: prev bar is contained within mother bar
        is_inside = (prev_high < mother_high) & (prev_low > mother_low)

        # Entry Long: current close breaks above mother bar high
        bullish_cond = is_inside & (df['Close'] > mother_high)
        
        # Entry Short: current close breaks below mother bar low
        bearish_cond = is_inside & (df['Close'] < mother_low)

        df.loc[bullish_cond, 'signal'] = 1
        df.loc[bullish_cond, 'stop_loss'] = prev_low[bullish_cond]
        df.loc[bullish_cond, 'target'] = df['Close'][bullish_cond] + 2 * (df['Close'][bullish_cond] - prev_low[bullish_cond])

        df.loc[bearish_cond, 'signal'] = -1
        df.loc[bearish_cond, 'stop_loss'] = prev_high[bearish_cond]
        df.loc[bearish_cond, 'target'] = df['Close'][bearish_cond] - 2 * (prev_high[bearish_cond] - df['Close'][bearish_cond])

        return df
