import pandas as pd
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
        if df.empty or len(df) < 30:
            return df

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0
        
        # Calculate rolling 30-day high and low
        df['High_30'] = df['High'].rolling(window=30).max().shift(1)
        df['Low_30'] = df['Low'].rolling(window=30).min().shift(1)

        for i in range(30, len(df)):
            close = df['Close'].iloc[i]
            open_p = df['Open'].iloc[i]
            low = df['Low'].iloc[i]
            
            high_30 = df['High_30'].iloc[i]
            low_30 = df['Low_30'].iloc[i]

            if pd.isna(high_30) or pd.isna(low_30):
                continue

            # Ensure there is a substantial trend (at least 10% move from low to high)
            trend_size = (high_30 - low_30) / low_30
            if trend_size < 0.10:
                continue

            # Calculate Fibonacci levels
            diff = high_30 - low_30
            fib_50 = high_30 - (diff * 0.50)
            fib_618 = high_30 - (diff * 0.618)
            
            # The Golden Zone is between fib_618 and fib_50
            # Wait for price to drop into this zone
            if low <= fib_50 and low >= fib_618 * 0.98: # Allow slight undercut of 61.8
                # Enter if it's a bullish candle
                if close > open_p:
                    df.at[df.index[i], 'signal'] = 1
                    # Stop loss below the 61.8% or 78.6% level
                    fib_786 = high_30 - (diff * 0.786)
                    df.at[df.index[i], 'stop_loss'] = min(low * 0.98, fib_786)
                    # Target the recent high
                    df.at[df.index[i], 'target'] = high_30

        return df
