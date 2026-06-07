import pandas as pd
import numpy as np
from strategies.base import BaseStrategy

class RVOLORBStrategy(BaseStrategy):
    """
    Relative Volume (RVOL) Filtered Opening Range Breakout
    Timeframe: 15m
    Logic:
    - Calculates the Opening Range (first 15m candle) for the day.
    - Breakout happens when price closes above the OR high or below OR low.
    - Filter: The breakout candle MUST have Relative Volume (RVOL) > 1.5x.
      (Volume > 1.5 * average volume of the last 20 periods)
    """
    name = "RVOL_ORB"
    timeframe = "15m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if df.empty or len(df) < 20:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df

        if not pd.api.types.is_datetime64_any_dtype(df.index):
            df.index = pd.to_datetime(df.index)

        df['Date'] = df.index.date
        df['Vol_SMA_20'] = df['Volume'].rolling(window=20).mean().shift(1)
        df['RVOL'] = df['Volume'] / df['Vol_SMA_20']

        # Group by date to find the first candle's high and low
        first_candles = df.groupby('Date').head(1)
        or_high = first_candles.set_index('Date')['High'].rename('OR_High')
        or_low = first_candles.set_index('Date')['Low'].rename('OR_Low')

        # Map back to intraday dataframe
        df = df.join(or_high, on='Date')
        df = df.join(or_low, on='Date')

        # To avoid re-entering multiple times, we'll only take the FIRST breakout of the day.
        # We can do this using cumulative sum of breakouts per day.
        df['bullish_break'] = (df['Close'] > df['OR_High']) & (df['RVOL'] > 1.5)
        df['bearish_break'] = (df['Close'] < df['OR_Low']) & (df['RVOL'] > 1.5)

        # Ensure it's not the first candle itself breaking out (since OR is formed by first candle)
        is_first_candle = df.groupby('Date').cumcount() == 0
        df.loc[is_first_candle, 'bullish_break'] = False
        df.loc[is_first_candle, 'bearish_break'] = False

        # Get first breakout per day
        df['bull_cum'] = df.groupby('Date')['bullish_break'].cumsum()
        df['bear_cum'] = df.groupby('Date')['bearish_break'].cumsum()

        valid_bull = (df['bullish_break']) & (df['bull_cum'] == 1) & (df['bear_cum'] == 0)
        valid_bear = (df['bearish_break']) & (df['bear_cum'] == 1) & (df['bull_cum'] == 0)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        df.loc[valid_bull, 'signal'] = 1
        df.loc[valid_bull, 'stop_loss'] = df['OR_Low'][valid_bull]
        df.loc[valid_bull, 'target'] = df['Close'][valid_bull] + (df['Close'][valid_bull] - df['OR_Low'][valid_bull]) * 2

        df.loc[valid_bear, 'signal'] = -1
        df.loc[valid_bear, 'stop_loss'] = df['OR_High'][valid_bear]
        df.loc[valid_bear, 'target'] = df['Close'][valid_bear] - (df['OR_High'][valid_bear] - df['Close'][valid_bear]) * 2

        # Clean up
        df.drop(columns=['Date', 'Vol_SMA_20', 'RVOL', 'OR_High', 'OR_Low', 'bullish_break', 'bearish_break', 'bull_cum', 'bear_cum'], inplace=True, errors='ignore')

        return df
