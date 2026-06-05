import pandas as pd
import numpy as np
from strategies.base import BaseStrategy

class FibonacciGoldenZoneStrategy(BaseStrategy):
    """
    Fibonacci "Golden Zone" Retracements Strategy
    Timeframe: 1D
    Logic:
    - Finds a 30-day swing low and swing high.
    - If price retraces to the 50% - 61.8% Fibonacci zone and prints a bullish candle, enter long.
    """
    name = "Fibonacci_Golden_Zone"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if df.empty or len(df) < 30:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0
        
        # Calculate rolling 30-day high and low
        df['High_30'] = df['High'].rolling(window=30).max().shift(1)
        df['Low_30'] = df['Low'].rolling(window=30).min().shift(1)

        trend_size = (df['High_30'] - df['Low_30']) / df['Low_30']
        valid_trend = trend_size >= 0.10

        diff = df['High_30'] - df['Low_30']
        fib_50 = df['High_30'] - (diff * 0.50)
        fib_618 = df['High_30'] - (diff * 0.618)
        fib_786 = df['High_30'] - (diff * 0.786)

        in_zone = (df['Low'] <= fib_50) & (df['Low'] >= fib_618 * 0.98)
        bullish_candle = df['Close'] > df['Open']

        bullish_cond = valid_trend & in_zone & bullish_candle

        # Edge-trigger
        prev_bullish = bullish_cond.shift(1, fill_value=False)
        valid_bull = bullish_cond & ~prev_bullish

        df.loc[valid_bull, 'signal'] = 1
        df.loc[valid_bull, 'stop_loss'] = np.minimum(df['Low'][valid_bull] * 0.98, fib_786[valid_bull])
        df.loc[valid_bull, 'target'] = df['High_30'][valid_bull]

        return df
