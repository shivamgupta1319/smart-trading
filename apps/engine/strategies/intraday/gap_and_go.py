from datetime import time as dtime

import pandas as pd
from strategies.base import BaseStrategy

# The live scanner takes no new setups before 09:30, and it only sees COMPLETED
# candles. The first candle it can act on is therefore 09:25–09:30. The old version
# signalled on the 09:15 candle, which live could never see — the strategy had
# backtest results but could not fire a single live trade.
CONFIRM_BAR_TIME = dtime(9, 25)
GAP_THRESHOLD = 0.005  # 0.5%


class GapAndGoStrategy(BaseStrategy):
    """
    Gap and Go Strategy
    Timeframe: 5m
    Logic (one possible trade per day, decided on the 09:25 candle):
    - The day opens with a gap of at least 0.5% from the previous close.
    - The first 5-minute candle closes in the direction of the gap.
    - After the first 15 minutes price is still beyond the day's open in that
      direction (the gap has held).
    - Stop: the low (long) or high (short) of the day so far. Target: 2R.
    """
    name = "Gap_And_Go"
    timeframe = "5m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if df.empty or len(df) < 10:
            return df

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        if not pd.api.types.is_datetime64_any_dtype(df.index):
            df.index = pd.to_datetime(df.index)

        day = pd.Series(df.index.date, index=df.index)
        by_day = df.groupby(day)

        prev_close = day.map(by_day['Close'].last().shift(1))
        day_open = by_day['Open'].transform('first')
        first_close = by_day['Close'].transform('first')
        low_so_far = by_day['Low'].cummin()
        high_so_far = by_day['High'].cummax()

        gap_pct = (day_open - prev_close) / prev_close
        is_confirm_bar = pd.Series(df.index.time == CONFIRM_BAR_TIME, index=df.index)

        bullish = (
            is_confirm_bar & (gap_pct >= GAP_THRESHOLD)
            & (first_close > day_open) & (df['Close'] > day_open)
            & (df['Close'] > low_so_far)
        )
        bearish = (
            is_confirm_bar & (gap_pct <= -GAP_THRESHOLD)
            & (first_close < day_open) & (df['Close'] < day_open)
            & (df['Close'] < high_so_far)
        )

        df.loc[bullish, 'signal'] = 1
        df.loc[bullish, 'stop_loss'] = low_so_far[bullish]
        df.loc[bullish, 'target'] = df['Close'][bullish] + 2 * (df['Close'][bullish] - low_so_far[bullish])

        df.loc[bearish, 'signal'] = -1
        df.loc[bearish, 'stop_loss'] = high_so_far[bearish]
        df.loc[bearish, 'target'] = df['Close'][bearish] - 2 * (high_so_far[bearish] - df['Close'][bearish])

        return df
