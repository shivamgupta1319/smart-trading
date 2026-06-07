import pandas as pd
from strategies.base import BaseStrategy

class PDHPDLBreakoutStrategy(BaseStrategy):
    """
    Previous Day High/Low (PDH/PDL) Breakout Strategy
    Timeframe: 5m
    Logic:
    - Calculates PDH and PDL.
    - Long if price breaks above PDH.
    - Short if price breaks below PDL.
    """
    name = "PDH_PDL_Breakout"
    timeframe = "5m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if df.empty or len(df) < 10:
            return df

        if not pd.api.types.is_datetime64_any_dtype(df.index):
            df.index = pd.to_datetime(df.index)

        df['Date'] = df.index.date
        
        # Calculate daily aggregates
        daily_highs = df.groupby('Date')['High'].max().shift(1)
        daily_lows = df.groupby('Date')['Low'].min().shift(1)
        
        df['PDH'] = df['Date'].map(daily_highs)
        df['PDL'] = df['Date'].map(daily_lows)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        prev_close = df['Close'].shift(1)

        # Long breakout: previous close below PDH, current close above PDH
        bullish_cond = (prev_close <= df['PDH']) & (df['Close'] > df['PDH'])

        # Short breakout: previous close above PDL, current close below PDL
        bearish_cond = (prev_close >= df['PDL']) & (df['Close'] < df['PDL'])

        df.loc[bullish_cond, 'signal'] = 1
        sl_bull = df['Low'] - (df['Close'] * 0.002)
        df.loc[bullish_cond, 'stop_loss'] = sl_bull[bullish_cond]
        df.loc[bullish_cond, 'target'] = df['Close'][bullish_cond] + (df['Close'][bullish_cond] - sl_bull[bullish_cond]) * 2

        df.loc[bearish_cond, 'signal'] = -1
        sl_bear = df['High'] + (df['Close'] * 0.002)
        df.loc[bearish_cond, 'stop_loss'] = sl_bear[bearish_cond]
        df.loc[bearish_cond, 'target'] = df['Close'][bearish_cond] - (sl_bear[bearish_cond] - df['Close'][bearish_cond]) * 2

        df.drop(columns=['Date', 'PDH', 'PDL'], inplace=True)
        return df
