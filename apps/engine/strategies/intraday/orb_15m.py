"""Strategy 1: 15-Minute Opening Range Breakout (ORB)"""
import pandas as pd
from strategies.base import BaseStrategy

class ORB15mStrategy(BaseStrategy):
    name = "15m_ORB"
    timeframe = "15m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        df['date'] = df.index.date

        # Get first candle of each day
        first_candles = df.groupby('date').first()
        
        # Map ORB back to all rows
        df['orb_high'] = df['date'].map(first_candles['High'])
        df['orb_low'] = df['date'].map(first_candles['Low'])
        df['orb_mid'] = (df['orb_high'] + df['orb_low']) / 2
        
        # We only consider rows that are NOT the first candle of the day
        is_not_first = df.groupby('date').cumcount() > 0

        # Conditions
        bullish_cond = is_not_first & (df['Close'] > df['orb_high'])
        bearish_cond = is_not_first & (df['Close'] < df['orb_low'])

        # We only want the FIRST signal of the day
        # cumulative max of boolean condition will be true from the first time it happens
        # We want exactly the row where it transitions from False to True
        any_signal = bullish_cond | bearish_cond
        first_signal_mask = any_signal & (~any_signal.groupby(df['date']).shift(1, fill_value=False).groupby(df['date']).cummax())
        
        final_bullish = bullish_cond & first_signal_mask
        final_bearish = bearish_cond & first_signal_mask

        df.loc[final_bullish, 'signal'] = 1
        df.loc[final_bullish, 'stop_loss'] = df['orb_mid'][final_bullish]
        df.loc[final_bullish, 'target'] = df['Close'][final_bullish] + 2 * (df['Close'][final_bullish] - df['orb_mid'][final_bullish])

        df.loc[final_bearish, 'signal'] = -1
        df.loc[final_bearish, 'stop_loss'] = df['orb_mid'][final_bearish]
        df.loc[final_bearish, 'target'] = df['Close'][final_bearish] - 2 * (df['orb_mid'][final_bearish] - df['Close'][final_bearish])

        return df.drop(columns=['date', 'orb_high', 'orb_low', 'orb_mid'])
