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

        for i in range(2, len(df)):
            prev = df.iloc[i - 1]  # potential inside bar
            mother = df.iloc[i - 2]  # mother bar
            curr = df.iloc[i]  # current candle — check for breakout

            # Identify inside bar: prev bar is contained within mother bar
            is_inside = prev['High'] < mother['High'] and prev['Low'] > mother['Low']
            if not is_inside:
                continue

            # Entry Long: current close breaks above mother bar high
            if curr['Close'] > mother['High']:
                sl = prev['Low']
                rr = curr['Close'] - sl
                df.iloc[i, df.columns.get_loc('signal')] = 1
                df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                df.iloc[i, df.columns.get_loc('target')] = curr['Close'] + 2 * rr

            # Entry Short: current close breaks below mother bar low
            elif curr['Close'] < mother['Low']:
                sl = prev['High']
                rr = sl - curr['Close']
                df.iloc[i, df.columns.get_loc('signal')] = -1
                df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                df.iloc[i, df.columns.get_loc('target')] = curr['Close'] - 2 * rr

        return df
