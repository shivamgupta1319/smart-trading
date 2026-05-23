import pandas as pd
from strategies.base import BaseStrategy

class GapAndGoStrategy(BaseStrategy):
    """
    Gap and Go Strategy
    Timeframe: 5m
    Logic:
    - Target stocks opening with a significant gap (>= 0.5%).
    - If the first 5-minute candle closes in the direction of the gap without filling it, enter.
    """
    name = "Gap_And_Go"
    timeframe = "5m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or len(df) < 10:
            return df

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        # We need the previous day's close.
        # Ensure index is datetime
        if not pd.api.types.is_datetime64_any_dtype(df.index):
            df.index = pd.to_datetime(df.index)

        # Create a date column for grouping
        df['Date'] = df.index.date
        
        # Get the first candle of each day
        first_candles = df.groupby('Date').head(1).copy()
        
        # Get the last close of each day
        last_closes = df.groupby('Date').tail(1)['Close'].shift(1)
        # Re-map the previous close to the first candle of the current day using the dates
        # Wait, shift(1) moves the last close down by 1 day.
        last_closes.index = first_candles.index
        first_candles['Prev_Close'] = last_closes

        # Filter for gaps
        gap_threshold = 0.005 # 0.5%
        
        # Merge back to df so we can flag the first candle
        df['Prev_Close'] = pd.Series(index=df.index, dtype=float)
        df.loc[first_candles.index, 'Prev_Close'] = first_candles['Prev_Close']

        for i in range(1, len(df)):
            prev_close = df['Prev_Close'].iloc[i]
            
            # If it's not the first candle of the day (prev_close is NaN), skip
            if pd.isna(prev_close):
                continue
                
            open_price = df['Open'].iloc[i]
            close_price = df['Close'].iloc[i]
            high_price = df['High'].iloc[i]
            low_price = df['Low'].iloc[i]

            gap_pct = (open_price - prev_close) / prev_close

            # Bullish Gap
            if gap_pct >= gap_threshold:
                # If first candle closes bullish (closes above open)
                if close_price > open_price:
                    df.at[df.index[i], 'signal'] = 1
                    df.at[df.index[i], 'stop_loss'] = low_price # Stop loss below the first candle
                    risk = close_price - low_price
                    df.at[df.index[i], 'target'] = close_price + (risk * 2)

            # Bearish Gap
            elif gap_pct <= -gap_threshold:
                # If first candle closes bearish (closes below open)
                if close_price < open_price:
                    df.at[df.index[i], 'signal'] = -1
                    df.at[df.index[i], 'stop_loss'] = high_price
                    risk = high_price - close_price
                    df.at[df.index[i], 'target'] = close_price - (risk * 2)

        df.drop(columns=['Date', 'Prev_Close'], inplace=True)
        return df
