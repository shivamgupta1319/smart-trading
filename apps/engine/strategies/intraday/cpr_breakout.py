import pandas as pd
from strategies.base import BaseStrategy

class CPRBreakoutStrategy(BaseStrategy):
    """
    Central Pivot Range (CPR) Breakout Strategy
    Timeframe: 5m
    Logic:
    - Calculates Daily Pivot, TC, BC from previous day's data.
    - Long if price breaks above TC.
    - Short if price breaks below BC.
    """
    name = "CPR_Breakout"
    timeframe = "5m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if df.empty or len(df) < 10:
            return df

        if not pd.api.types.is_datetime64_any_dtype(df.index):
            df.index = pd.to_datetime(df.index)

        df['Date'] = df.index.date
        
        # Calculate daily aggregates
        daily_data = df.groupby('Date').agg({
            'High': 'max',
            'Low': 'min',
            'Close': 'last'
        }).shift(1) # Shift 1 to get previous day's data for current day
        
        # Calculate CPR
        daily_data['Pivot'] = (daily_data['High'] + daily_data['Low'] + daily_data['Close']) / 3
        daily_data['BC'] = (daily_data['High'] + daily_data['Low']) / 2
        daily_data['TC'] = (daily_data['Pivot'] - daily_data['BC']) + daily_data['Pivot']
        
        # Ensure TC is always the higher value and BC is the lower
        daily_data['TC_Actual'] = daily_data[['TC', 'BC']].max(axis=1)
        daily_data['BC_Actual'] = daily_data[['TC', 'BC']].min(axis=1)

        df['TC'] = df['Date'].map(daily_data['TC_Actual'])
        df['BC'] = df['Date'].map(daily_data['BC_Actual'])

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        prev_close = df['Close'].shift(1)

        # Long breakout: previous close was below TC, current close is above TC
        bullish_cond = (prev_close <= df['TC']) & (df['Close'] > df['TC'])

        # Short breakout: previous close was above BC, current close is below BC
        bearish_cond = (prev_close >= df['BC']) & (df['Close'] < df['BC'])

        df.loc[bullish_cond, 'signal'] = 1
        df.loc[bullish_cond, 'stop_loss'] = df['BC'][bullish_cond]
        df.loc[bullish_cond, 'target'] = df['Close'][bullish_cond] + (df['Close'][bullish_cond] - df['BC'][bullish_cond]) * 1.5

        df.loc[bearish_cond, 'signal'] = -1
        df.loc[bearish_cond, 'stop_loss'] = df['TC'][bearish_cond]
        df.loc[bearish_cond, 'target'] = df['Close'][bearish_cond] - (df['TC'][bearish_cond] - df['Close'][bearish_cond]) * 1.5

        df.drop(columns=['Date', 'TC', 'BC'], inplace=True)
        return df
