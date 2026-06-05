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
        df = df.copy()
        if df.empty or len(df) < 10:
            return df

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        if not pd.api.types.is_datetime64_any_dtype(df.index):
            df.index = pd.to_datetime(df.index)

        df['Date'] = df.index.date
        
        first_candles = df.groupby('Date').first()
        last_closes = df.groupby('Date')['Close'].last().shift(1)
        
        # map last_closes to df index based on Date
        df['Prev_Close'] = df['Date'].map(last_closes)

        gap_threshold = 0.005 # 0.5%
        gap_pct = (df['Open'] - df['Prev_Close']) / df['Prev_Close']

        # We only consider the FIRST candle of the day
        is_first = df.groupby('Date').cumcount() == 0

        # Bullish Gap
        bullish_gap = (gap_pct >= gap_threshold) & is_first
        bullish_cond = bullish_gap & (df['Close'] > df['Open'])

        # Bearish Gap
        bearish_gap = (gap_pct <= -gap_threshold) & is_first
        bearish_cond = bearish_gap & (df['Close'] < df['Open'])

        df.loc[bullish_cond, 'signal'] = 1
        df.loc[bullish_cond, 'stop_loss'] = df['Low'][bullish_cond]
        df.loc[bullish_cond, 'target'] = df['Close'][bullish_cond] + 2 * (df['Close'][bullish_cond] - df['Low'][bullish_cond])

        df.loc[bearish_cond, 'signal'] = -1
        df.loc[bearish_cond, 'stop_loss'] = df['High'][bearish_cond]
        df.loc[bearish_cond, 'target'] = df['Close'][bearish_cond] - 2 * (df['High'][bearish_cond] - df['Close'][bearish_cond])

        df.drop(columns=['Date', 'Prev_Close'], inplace=True)
        return df
