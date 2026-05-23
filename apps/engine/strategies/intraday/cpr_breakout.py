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
        # TC and BC can invert depending on the math
        daily_data['TC_Actual'] = daily_data[['TC', 'BC']].max(axis=1)
        daily_data['BC_Actual'] = daily_data[['TC', 'BC']].min(axis=1)

        # Map back to intraday dataframe
        df = df.merge(daily_data[['Pivot', 'TC_Actual', 'BC_Actual']], left_on='Date', right_index=True, how='left')
        df.index = df.index # Restore index if merge messed it up (merge might drop datetime index)
        # Wait, merge resets index if right_index=True and left is not index.
        # Better way:
        
        df['TC'] = pd.Series(index=df.index, dtype=float)
        df['BC'] = pd.Series(index=df.index, dtype=float)
        
        for date, row in daily_data.iterrows():
            mask = df['Date'] == date
            df.loc[mask, 'TC'] = row['TC_Actual']
            df.loc[mask, 'BC'] = row['BC_Actual']

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(1, len(df)):
            tc = df['TC'].iloc[i]
            bc = df['BC'].iloc[i]
            
            if pd.isna(tc) or pd.isna(bc):
                continue
                
            close = df['Close'].iloc[i]
            prev_close = df['Close'].iloc[i-1]
            high = df['High'].iloc[i]
            low = df['Low'].iloc[i]

            # Long breakout: previous close was below TC, current close is above TC
            if prev_close <= tc and close > tc:
                df.at[df.index[i], 'signal'] = 1
                df.at[df.index[i], 'stop_loss'] = bc # Stop loss below bottom central pivot
                df.at[df.index[i], 'target'] = close + (close - bc) * 1.5

            # Short breakout: previous close was above BC, current close is below BC
            elif prev_close >= bc and close < bc:
                df.at[df.index[i], 'signal'] = -1
                df.at[df.index[i], 'stop_loss'] = tc # Stop loss above top central pivot
                df.at[df.index[i], 'target'] = close - (tc - close) * 1.5

        df.drop(columns=['Date', 'TC', 'BC'], inplace=True)
        return df
